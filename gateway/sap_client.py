"""
SAP OData istemcisi.

Gateway ile SAP arasindaki tek nokta. Icerideki her sey OData konusur;
disariya konusan tek sey bu dosya. Gercek bir S/4HANA'ya gecis, SAP_BASE_URL
degiskenini degistirmekten ibaret — cunku burada SAP'ye ozgu olan her sey
(CSRF el sikismasi, {"d": ...} zarfi, hata kodlari, 18 hane MATNR) zaten var.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

SAP_BASE_URL = os.getenv("SAP_BASE_URL", "").rstrip("/")
SAP_TIMEOUT = float(os.getenv("SAP_TIMEOUT_SECONDS", "8"))

MATERIAL_DOC = "/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV"
MATERIAL_STOCK = "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV"
PRODUCT = "/sap/opu/odata/sap/API_PRODUCT_SRV"
PURCHASE_ORDER = "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV"


class SapError(Exception):
    """SAP'nin dondugu is hatasi. message zaten sesli okunabilir bir cumle."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class SapClient:
    """
    Tek bir HTTP oturumu tutar. CSRF token'i ve oturum cerezini saklar,
    403 CSRF hatasinda bir kez yeniler ve tekrar dener — gercek SAP
    entegrasyonlarinda yapilan sey birebir budur.
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or SAP_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(timeout=SAP_TIMEOUT, follow_redirects=False)
        self._csrf: str | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- CSRF ---------------------------------------------------------------

    async def _fetch_csrf(self) -> str:
        """
        SAP'ye yazmadan once zorunlu adim: servis kokune 'X-CSRF-Token: Fetch'
        ile gidilir, donen token sonraki POST'ta gonderilir. Cerez de ayni
        oturumda tasinmali; ikisi birlikte gecerli olur.
        """
        r = await self._client.get(
            f"{self.base_url}{MATERIAL_DOC}/", headers={"X-CSRF-Token": "Fetch"}
        )
        token = r.headers.get("X-CSRF-Token")
        if not token:
            raise SapError("CSRF_FETCH_FAILED", "Could not obtain a CSRF token from SAP.", 502)
        self._csrf = token
        return token

    # -- Yazma --------------------------------------------------------------

    async def post_material_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._csrf:
            await self._fetch_csrf()

        async def _send() -> httpx.Response:
            return await self._client.post(
                f"{self.base_url}{MATERIAL_DOC}/A_MaterialDocumentHeader",
                json=payload,
                headers={"X-CSRF-Token": self._csrf or "", "Content-Type": "application/json"},
            )

        r = await _send()
        if r.status_code == 403:
            # Token suresi gecmis olabilir: bir kez yenile ve tekrar dene.
            await self._fetch_csrf()
            r = await _send()

        if r.status_code >= 400:
            code, msg = _parse_odata_error(r)
            raise SapError(code, msg, r.status_code)

        return r.json().get("d", {})

    # -- Okuma --------------------------------------------------------------

    async def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        r = await self._client.get(f"{self.base_url}{path}", params=params)
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


def _parse_odata_error(r: httpx.Response) -> tuple[str, str]:
    """SAP'nin hata zarfindan kod ve okunabilir mesaji cikarir."""
    try:
        err = r.json().get("error", {})
        return err.get("code", "SAP_ERROR"), err.get("message", {}).get("value", r.text[:200])
    except Exception:
        return "SAP_ERROR", r.text[:200] or f"SAP returned {r.status_code}."


# ---------------------------------------------------------------------------
# Govde kurucular — SAP'nin bekledigi sekli tek yerde tut
# ---------------------------------------------------------------------------

# GoodsMovementCode: 01 siparise karsi mal girisi, 05 siparissiz mal girisi.
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
        item["GoodsMovementRefDocType"] = "B"   # B = satinalma siparisi
    return _with_voice_origin({
        "PostingDate": datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00"),
        "GoodsMovementCode": "01" if purchase_order else "05",
        "to_MaterialDocumentItem": [item],
    }, session_ref)


def reversal_payload(material: str, plant: str, storage_location: str, unit: str,
                     original_document: str, original_movement_type: str,
                     session_ref: str | None = None) -> dict[str, Any]:
    """
    SAP'de yanlis belge silinmez, ters kayit atilir. 101'in tersi 102,
    501'in tersi 502. Stok geri iner ama iki belge de tarihte kalir.
    """
    reverse_of = {"101": "102", "501": "502"}.get(original_movement_type)
    if reverse_of is None:
        raise SapError("NOT_REVERSIBLE",
                       f"Movement type {original_movement_type} cannot be reversed here.")
    return _with_voice_origin({
        "PostingDate": datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00"),
        "GoodsMovementCode": "01" if reverse_of == "102" else "05",
        "to_MaterialDocumentItem": [{
            "Material": material,
            "Plant": plant,
            "StorageLocation": storage_location,
            "GoodsMovementType": reverse_of,
            "EntryUnit": unit,
            "QuantityInEntryUnit": "1",     # mock asil belgeden alir
            "ReferenceDocument": original_document,
        }],
    }, session_ref)


def _with_voice_origin(payload: dict[str, Any], session_ref: str | None) -> dict[str, Any]:
    """
    Belgeye kokenini yazar - kimligini DEGIL. MaterialDocumentHeaderText (BKTXT,
    25 karakter) sesle acildigini soyler; basliktaki ReferenceDocument (XBLNR)
    oturum referansini tasir, gateway'deki denetim izine oradan gidilir.
    (Basliktaki XBLNR ile ters kayitta KALEM seviyesinde kullanilan
    ReferenceDocument ayni ad, ayri alanlardir - SAP'de de oyle.)

    Bilerek bir isim yazilmiyor. "Ben Sena" demek kimlik degildir; soylenen bir
    ismi belgeye koymak, dogrulanmis alanlarin yanina dogrulanmamis bir alan
    koymaktir ve okuyan ikisini ayirt edemez. Belgeyi bir insana baglayacak tek
    durust yol principal propagation, ve o docs/clean-core.md'de acik bir
    eksik olarak durur.
    """
    payload["MaterialDocumentHeaderText"] = "GLOVESON VOICE"
    if session_ref:
        payload["ReferenceDocument"] = f"VOICE:{session_ref[:10]}"   # XBLNR 16 kr
    return payload
