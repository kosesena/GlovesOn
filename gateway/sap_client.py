"""
The SAP OData client.

The single point of contact between the gateway and SAP. Everything inside
speaks OData; the only thing that speaks to the outside is this file. Moving to
a real S/4HANA is a matter of configuration rather than code — SAP_BASE_URL for
where, SAP_API_KEY for what to prove — because everything SAP-specific (the CSRF
handshake, the {"d": ...} envelope, error codes, 18-digit MATNR) is already here.

It used to say "one environment variable". That was true of routing and false of
the whole, because the mock demands no credential and so this client sent none.
Two variables is still configuration, but the sentence had to stop rounding down.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx


def env(name: str, default: str = "") -> str:
    """
    An empty variable must behave like an UNDEFINED one.

    os.getenv's second argument only kicks in when the variable is absent;
    when it "exists but is empty" you get the empty string back. That is
    exactly what happens when a deployment dashboard reads .env.example and
    creates every name with an empty value — and float("") then crashes the
    app at import time.
    """
    return os.getenv(name, "").strip() or default


SAP_BASE_URL = env("SAP_BASE_URL").rstrip("/")
SAP_TIMEOUT = float(env("SAP_TIMEOUT_SECONDS", "8"))
SAP_API_KEY = env("SAP_API_KEY")


def credentials(api_key: str | None = None) -> dict[str, str]:
    """
    The header SAP's own API gateway wants, and the correction to a claim.

    The mock needs no credential, so until now this client sent none at all —
    which quietly made "moving to a real tenant is one environment variable"
    untrue. It is two: where to go, and what to prove. `SAP_API_KEY` sends
    `APIKey`, which is what the Business Accelerator Hub sandbox and SAP API
    Management both expect.

    This is not the answer for a productive tenant. There the call should carry
    the *worker's* identity through BTP's Destination and Connectivity services,
    not a single service credential — the gap `docs/clean-core.md` is about.
    An API key gets us as far as a real SAP endpoint answering, and no further.
    """
    key = SAP_API_KEY if api_key is None else api_key
    return {"APIKey": key} if key else {}

MATERIAL_DOC = "/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV"
MATERIAL_STOCK = "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV"
PRODUCT = "/sap/opu/odata/sap/API_PRODUCT_SRV"
PURCHASE_ORDER = "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV"


class SapError(Exception):
    """A business error returned by SAP. message is already a speakable sentence."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class SapClient:
    """
    Holds a single HTTP session. It keeps the CSRF token and the session
    cookie, and on a 403 CSRF failure refreshes once and retries — which is
    exactly what real SAP integrations do.
    """

    def __init__(self, base_url: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 api_key: str | None = None):
        self.base_url = (base_url or SAP_BASE_URL).rstrip("/")
        # With a transport, the request reaches the mock's ASGI app without
        # touching a socket. What is spoken does not change — same OData
        # path, same CSRF handshake, same {"d": ...} envelope — only the
        # carrier does. The environment forces this: a serverless function
        # has no listening port, so there is no such thing as loopback.
        # The credential goes on the session, not on each call, so the CSRF fetch
        # carries it too. Behind SAP's API gateway an unauthenticated fetch is
        # rejected before it can hand back a token, and the failure surfaces as
        # "could not obtain a CSRF token" — which reads like a protocol fault and
        # is an authentication one.
        self._client = httpx.AsyncClient(timeout=SAP_TIMEOUT, follow_redirects=False,
                                         transport=transport,
                                         headers=credentials(api_key))
        self._csrf: str | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- CSRF ---------------------------------------------------------------

    async def _fetch_csrf(self) -> str:
        """
        The mandatory step before writing to SAP: hit the service root with
        'X-CSRF-Token: Fetch' and send the returned token on the next POST.
        The cookie must travel in the same session; only together are they
        valid.
        """
        try:
            r = await self._client.get(
                f"{self.base_url}{MATERIAL_DOC}/", headers={"X-CSRF-Token": "Fetch"}
            )
        except httpx.TimeoutException as e:
            raise SapError("SAP_TIMEOUT", _timeout_message("the CSRF handshake"), 504) from e
        except httpx.RequestError as e:
            raise SapError("SAP_UNREACHABLE", f"SAP could not be reached: {e.__class__.__name__}.", 502) from e
        token = r.headers.get("X-CSRF-Token")
        if not token:
            raise SapError("CSRF_FETCH_FAILED", "Could not obtain a CSRF token from SAP.", 502)
        self._csrf = token
        return token

    # -- Writes -------------------------------------------------------------

    async def post_material_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._csrf:
            await self._fetch_csrf()

        async def _send() -> httpx.Response:
            return await self._client.post(
                f"{self.base_url}{MATERIAL_DOC}/A_MaterialDocumentHeader",
                json=payload,
                headers={"X-CSRF-Token": self._csrf or "", "Content-Type": "application/json"},
            )

        # A transport failure on the write is the one error the agent must not
        # answer with a retry: the document may have been created and the
        # answer lost. The message says so and names the recovery — read the
        # recent documents, where the duplicate guard also looks — and the
        # gateway passes it to the agent as a refusal, not as a 500.
        try:
            r = await _send()
            if r.status_code == 403:
                # The token may have expired: refresh once and retry.
                await self._fetch_csrf()
                r = await _send()
        except httpx.TimeoutException as e:
            raise SapError("SAP_TIMEOUT", _timeout_message("the posting"), 504) from e
        except httpx.RequestError as e:
            raise SapError("SAP_UNREACHABLE",
                           f"SAP could not be reached while posting ({e.__class__.__name__}). "
                           f"Nothing is known about the document. Do not repeat the posting; "
                           f"check the recent documents first.", 502) from e

        if r.status_code >= 400:
            code, msg = _parse_odata_error(r)
            raise SapError(code, msg, r.status_code)

        return r.json().get("d", {})

    # -- Reads --------------------------------------------------------------

    async def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            r = await self._client.get(f"{self.base_url}{path}", params=params)
        except httpx.TimeoutException as e:
            raise SapError("SAP_TIMEOUT", _timeout_message("a read"), 504) from e
        except httpx.RequestError as e:
            raise SapError("SAP_UNREACHABLE", f"SAP could not be reached: {e.__class__.__name__}.", 502) from e
        if r.status_code >= 400:
            code, msg = _parse_odata_error(r)
            raise SapError(code, msg, r.status_code)
        return r.json().get("d", {}).get("results", [])

    async def get_stock(self, material: str, plant: str = "1000") -> list[dict[str, Any]]:
        return await self._get(f"{MATERIAL_STOCK}/A_MatlStkInAcctMod",
                               {"Material": material, "Plant": plant})

    async def get_description(self, material: str) -> dict[str, Any] | None:
        rows = await self._get(f"{PRODUCT}/A_ProductDescription", {"Product": material})
        return rows[0] if rows else None

    async def search_descriptions(self, query: str) -> list[dict[str, Any]]:
        return await self._get(f"{PRODUCT}/A_ProductDescription", {"search": query})

    async def get_purchase_order(self, order: str) -> dict[str, Any] | None:
        rows = await self._get(f"{PURCHASE_ORDER}/A_PurchaseOrder", {"PurchaseOrder": order})
        return rows[0] if rows else None

    async def list_documents(self, top: int = 10) -> list[dict[str, Any]]:
        return await self._get(f"{MATERIAL_DOC}/A_MaterialDocumentHeader", {"$top": top})


def _timeout_message(step: str) -> str:
    # Reads and the handshake are safe to repeat; the posting is not. The
    # sentence the agent will speak has to carry that difference.
    if step == "the posting":
        return (f"SAP did not answer within {SAP_TIMEOUT:g} seconds while posting. The document "
                f"may or may not exist. Do not repeat the posting; check the recent documents "
                f"first, and only prepare a new draft if it is not there.")
    return f"SAP did not answer within {SAP_TIMEOUT:g} seconds during {step}. Nothing was written; try again."


def _parse_odata_error(r: httpx.Response) -> tuple[str, str]:
    """Extracts the code and the readable message from SAP's error envelope."""
    try:
        err = r.json().get("error", {})
        return err.get("code", "SAP_ERROR"), err.get("message", {}).get("value", r.text[:200])
    except Exception:
        return "SAP_ERROR", r.text[:200] or f"SAP returned {r.status_code}."


# ---------------------------------------------------------------------------
# Payload builders — keep the shape SAP expects in one place
# ---------------------------------------------------------------------------

# GoodsMovementCode: 01 = receipt against an order, 05 = receipt without one.
def goods_receipt_payload(material: str, quantity: int, plant: str, storage_location: str,
                          unit: str, purchase_order: str | None,
                          session_ref: str | None = None) -> dict[str, Any]:
    movement_type = "101" if purchase_order else "501"
    item: dict[str, Any] = {
        "Material": material,
        "Plant": plant,
        "StorageLocation": storage_location,
        "GoodsMovementType": movement_type,
        "EntryUnit": unit,
        "QuantityInEntryUnit": str(quantity),
    }
    if purchase_order:
        item["PurchaseOrder"] = purchase_order
        item["PurchaseOrderItem"] = "00010"
        item["GoodsMovementRefDocType"] = "B"   # B = purchase order
    return _with_voice_origin({
        "PostingDate": datetime.now(UTC).strftime("%Y-%m-%dT00:00:00"),
        "GoodsMovementCode": "01" if purchase_order else "05",
        "to_MaterialDocumentItem": [item],
    }, session_ref)


def reversal_payload(material: str, plant: str, storage_location: str, unit: str,
                     original_document: str, original_movement_type: str,
                     quantity: int, session_ref: str | None = None) -> dict[str, Any]:
    """
    In SAP a wrong document is not deleted; a reversal is posted. A 102
    against a 101, a 502 against a 501. Stock comes back down, but both
    documents stay in the history.
    """
    reverse_of = {"101": "102", "501": "502"}.get(original_movement_type)
    if reverse_of is None:
        raise SapError("NOT_REVERSIBLE",
                       f"Movement type {original_movement_type} cannot be reversed here.")
    return _with_voice_origin({
        "PostingDate": datetime.now(UTC).strftime("%Y-%m-%dT00:00:00"),
        "GoodsMovementCode": "01" if reverse_of == "102" else "05",
        "to_MaterialDocumentItem": [{
            "Material": material,
            "Plant": plant,
            "StorageLocation": storage_location,
            "GoodsMovementType": reverse_of,
            "EntryUnit": unit,
            # The original document's quantity. This used to be a hardcoded
            # "1", and because the mock silently substituted the right value
            # nothing looked broken; a real S/4HANA would close a receipt of
            # 20 with a reversal of 1 and leave stock 19 too high. The mock's
            # correction was a convenience — exactly what ADR-0003 forbids.
            "QuantityInEntryUnit": str(quantity),
            "ReferenceDocument": original_document,
        }],
    }, session_ref)


def _with_voice_origin(payload: dict[str, Any], session_ref: str | None) -> dict[str, Any]:
    """
    Writes the document's origin — NOT an identity. MaterialDocumentHeaderText
    (BKTXT, 25 chars) says it was opened by voice; the header-level
    ReferenceDocument (XBLNR) carries the session reference, which leads to
    the audit trail in the gateway. (The header XBLNR and the ITEM-level
    ReferenceDocument used in reversals share a name but are separate
    fields — as they are in SAP.)

    Deliberately no name is written. Saying "I am Sena" is not identity;
    putting a spoken name on the document plants an unverified field next to
    verified ones, and a reader cannot tell the two apart. The only honest
    way to bind the document to a person is principal propagation, and that
    stands in docs/clean-core.md as an open gap.
    """
    payload["MaterialDocumentHeaderText"] = "GLOVESON VOICE"
    if session_ref:
        payload["ReferenceDocument"] = f"VOICE:{session_ref[:10]}"   # XBLNR is 16 chars
    return payload
