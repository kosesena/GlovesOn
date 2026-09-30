"""
Mock S/4HANA — speaks the contract of the real released OData APIs.

That this stands *opposite* the gateway rather than *inside* it is
deliberate. The gateway connects to it like a real HTTP client: it fetches
a CSRF token, sends an OData body, parses the {"d": ...} response. That is
what makes "moving to real SAP is a single base-URL change" literal rather
than figurative.

The released APIs imitated:
  API_MATERIAL_DOCUMENT_SRV      A_MaterialDocumentHeader   (write material movements)
  API_MATERIAL_STOCK_SRV         A_MatlStkInAcctMod         (read stock)
  API_PRODUCT_SRV                A_ProductDescription       (material description)
  API_PURCHASEORDER_PROCESS_SRV  A_PurchaseOrder            (purchase order status)

Real SAP works the same way: stock comes from one API, the description from
another. There is no single call for it, and that feeds straight into the
latency budget.
"""

from __future__ import annotations

import random
import re
import secrets
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import JSONResponse

from . import store
from .store import norm_matnr, pretty_matnr

router = APIRouter()

# Valid CSRF tokens. Real SAP ties these to the session cookie.
_tokens: dict[str, float] = {}
TOKEN_TTL_SECONDS = 1800

# GoodsMovementCode -> which operation. SAP's own codes:
#   01 goods receipt against a purchase order   (MIGO / MB01)
#   05 other goods receipts, no purchase order  (MB1C)
#   06 goods issue against an order
GMC_FOR_MOVEMENT = {"101": "01", "102": "01", "501": "05", "502": "05"}


def _odata_error(code: str, message: str, status: int = 400) -> JSONResponse:
    """SAP's OData v2 error envelope."""
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": {"lang": "en", "value": message}}},
    )


# The filter grammar the gateway actually sends: `Field eq 'value'` clauses and
# `substringof('text',Field)`, joined by `and`. Real SAP reads a filter only from
# `$filter` and ignores any other query option it does not know — so
# `?Material=4711` returns the whole entity set there. The mock used to honour
# that plain parameter, which is exactly how a client that never sent a
# `$filter` passed every test here and then read 2,745 stock rows from SAP's
# sandbox for one material. It now reads `$filter` only, as SAP does.
_EQ = re.compile(r"^(\w+)\s+eq\s+'((?:[^']|'')*)'$")
_SUBSTRINGOF = re.compile(r"^substringof\(\s*'((?:[^']|'')*)'\s*,\s*(\w+)\s*\)$")


class _BadFilter(ValueError):
    pass


def _parse_filter(expr: str | None) -> tuple[dict[str, str], dict[str, str]]:
    """Return ({field: value} for eq, {field: text} for substringof)."""
    eq: dict[str, str] = {}
    contains: dict[str, str] = {}
    if not expr:
        return eq, contains
    # Split on `and` only outside quotes: "nuts and bolts" is one value.
    for clause in re.split(r"\s+and\s+(?=(?:[^']*'[^']*')*[^']*$)", expr.strip()):
        clause = clause.strip()
        if m := _EQ.match(clause):
            eq[m.group(1)] = m.group(2).replace("''", "'")
        elif m := _SUBSTRINGOF.match(clause):
            contains[m.group(2)] = m.group(1).replace("''", "'")
        else:
            raise _BadFilter(clause)
    return eq, contains


def _bad_filter(clause: str) -> JSONResponse:
    return _odata_error("/IWBEP/CM_MGW_RT/022",
                        f"Invalid filter expression: '{clause}'.", 400)


def _issue_token() -> str:
    tok = secrets.token_urlsafe(24)
    _tokens[tok] = time.time() + TOKEN_TTL_SECONDS
    # sweep the expired ones
    for t, exp in list(_tokens.items()):
        if exp < time.time():
            _tokens.pop(t, None)
    return tok


def _token_valid(tok: str | None) -> bool:
    return bool(tok) and _tokens.get(tok, 0) > time.time()


# ---------------------------------------------------------------------------
# The CSRF handshake
# ---------------------------------------------------------------------------

@router.api_route("/API_MATERIAL_DOCUMENT_SRV/", methods=["GET", "HEAD"])
async def service_root(
    response: Response,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    """
    Before writing to SAP one comes here with 'X-CSRF-Token: Fetch', takes
    the token, and sends it back on the POST. Every write that skips this
    gets a 403.
    """
    if (x_csrf_token or "").lower() == "fetch":
        token = _issue_token()
        response.headers["X-CSRF-Token"] = token
        response.headers["Set-Cookie"] = f"SAP_SESSIONID_GLV_100={secrets.token_hex(8)}; Path=/"
    return {"d": {"EntitySets": ["A_MaterialDocumentHeader", "A_MaterialDocumentItem"]}}


# ---------------------------------------------------------------------------
# Writing material movements
# ---------------------------------------------------------------------------

@router.post("/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader")
async def create_material_document(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    if not _token_valid(x_csrf_token):
        return _odata_error(
            "CSRF_TOKEN_INVALID",
            "CSRF token validation failed. Fetch a token from the service root first.",
            status=403,
        )

    body = await request.json()
    items = body.get("to_MaterialDocumentItem") or []
    if not items:
        return _odata_error("INVALID_PAYLOAD", "to_MaterialDocumentItem must contain at least one item.")

    item = items[0]
    matnr = norm_matnr(item.get("Material", ""))
    werks = str(item.get("Plant") or "1000")
    lgort = str(item.get("StorageLocation") or "0001")
    bwart = str(item.get("GoodsMovementType") or "")
    ebeln = item.get("PurchaseOrder") or None
    reversed_of = item.get("ReferenceDocument") or None
    # Header fields. A real S/4HANA would not drop these as unrecognized —
    # it knows them and stores them; the mock keeps the same fidelity.
    bktxt = str(body.get("MaterialDocumentHeaderText") or "")[:25]
    xblnr = str(body.get("ReferenceDocument") or "")[:16]

    try:
        menge = int(float(item.get("QuantityInEntryUnit")))
    except (TypeError, ValueError):
        return _odata_error("INVALID_QUANTITY", "QuantityInEntryUnit must be numeric.")

    if menge <= 0:
        return _odata_error("INVALID_QUANTITY", "QuantityInEntryUnit must be greater than zero.")

    if bwart not in GMC_FOR_MOVEMENT:
        return _odata_error("UNSUPPORTED_MOVEMENT_TYPE", f"Movement type {bwart} is not supported here.")

    expected_gmc = GMC_FOR_MOVEMENT[bwart]
    if str(body.get("GoodsMovementCode") or "") != expected_gmc:
        return _odata_error(
            "GOODS_MOVEMENT_CODE_MISMATCH",
            f"Movement type {bwart} requires GoodsMovementCode {expected_gmc}.",
        )

    with store.db() as conn:
        row = conn.execute(
            "SELECT * FROM mard WHERE matnr=%s AND werks=%s AND lgort=%s", (matnr, werks, lgort)
        ).fetchone()
        if row is None:
            return _odata_error(
                "M7_042",
                f"Material {pretty_matnr(matnr)} is not maintained in plant {werks}, "
                f"storage location {lgort}.",
            )

        # Reversal (102): find the original document and take the stock back out
        if bwart in ("102", "502"):
            orig = conn.execute(
                "SELECT * FROM mkpf WHERE mblnr=%s", (str(reversed_of or ""),)
            ).fetchone()
            if orig is None:
                return _odata_error("M7_054", f"Material document {reversed_of} does not exist.")
            if orig["bwart"] in ("102", "502"):
                return _odata_error("M7_055", f"Material document {reversed_of} is itself a reversal.")
            already = conn.execute(
                "SELECT mblnr FROM mkpf WHERE reversed_of=%s", (str(reversed_of),)
            ).fetchone()
            if already:
                return _odata_error(
                    "M7_056",
                    f"Material document {reversed_of} was already reversed by {already['mblnr']}.",
                )
            delta = -orig["menge"]
            menge = orig["menge"]
        else:
            # Note: a real S/4HANA happily accepts the same goods receipt
            # twice. The duplicate guard is deliberately NOT here but in the
            # gateway — that protection belongs to us, not to SAP.
            # See docs/adr/0002.
            delta = menge

        mblnr = f"49{random.randint(10_000_000, 99_999_999)}"
        mjahr = datetime.now(UTC).strftime("%Y")
        budat = datetime.now(UTC).strftime("%Y-%m-%d")

        conn.execute(
            "UPDATE mard SET labst = labst + %s WHERE matnr=%s AND werks=%s AND lgort=%s",
            (delta, matnr, werks, lgort),
        )
        conn.execute(
            "INSERT INTO mkpf (mblnr, mjahr, bwart, matnr, menge, meins, werks, lgort,"
            " lgpla, budat, ebeln, reversed_of, created_at, bktxt, xblnr)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (mblnr, mjahr, bwart, matnr, menge, row["meins"], werks, lgort,
             row["lgpla"], budat, ebeln, reversed_of, time.time(), bktxt, xblnr),
        )
        new_level = conn.execute(
            "SELECT labst FROM mard WHERE matnr=%s AND werks=%s AND lgort=%s", (matnr, werks, lgort)
        ).fetchone()["labst"]

    return JSONResponse(
        status_code=201,
        content={"d": {
            "MaterialDocument": mblnr,
            "MaterialDocumentYear": mjahr,
            "PostingDate": budat,
            "GoodsMovementCode": expected_gmc,
            "MaterialDocumentHeaderText": bktxt,
            "ReferenceDocument": xblnr,
            "to_MaterialDocumentItem": {"results": [{
                "MaterialDocument": mblnr, "MaterialDocumentYear": mjahr,
                "MaterialDocumentItem": "0001", "Material": matnr,
                "Plant": werks, "StorageLocation": lgort, "GoodsMovementType": bwart,
                "QuantityInEntryUnit": str(menge), "EntryUnit": row["meins"],
                "StorageBin": row["lgpla"], "PurchaseOrder": ebeln,
                "ReferenceDocument": reversed_of,
                "MaterialBaseUnitStockQuantity": str(new_level),
            }]},
        }},
    )


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@router.get("/API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod")
async def material_stock(filter_: str | None = Query(None, alias="$filter")):
    try:
        eq, _ = _parse_filter(filter_)
    except _BadFilter as e:
        return _bad_filter(str(e))
    where, args = [], []
    if "Material" in eq:
        where.append("matnr=%s")
        args.append(norm_matnr(eq["Material"]))
    if "Plant" in eq:
        where.append("werks=%s")
        args.append(eq["Plant"])
    sql = "SELECT * FROM mard" + (" WHERE " + " AND ".join(where) if where else "")
    with store.db() as conn:
        rows = conn.execute(sql + " ORDER BY matnr, lgort", args).fetchall()
    return {"d": {"results": [{
        "Material": r["matnr"], "Plant": r["werks"], "StorageLocation": r["lgort"],
        "StorageBin": r["lgpla"], "MatlWrhsStkQtyInMatlBaseUnit": str(r["labst"]),
        "MaterialBaseUnit": r["meins"],
    } for r in rows]}}


@router.get("/API_PRODUCT_SRV/A_ProductDescription")
async def product_description(filter_: str | None = Query(None, alias="$filter")):
    try:
        eq, contains = _parse_filter(filter_)
    except _BadFilter as e:
        return _bad_filter(str(e))
    with store.db() as conn:
        if "Product" in eq:
            rows = conn.execute(
                "SELECT DISTINCT matnr, maktx, meins FROM mard WHERE matnr=%s",
                (norm_matnr(eq["Product"]),)).fetchall()
        else:
            # SAP's substringof is case-sensitive; the mock folds case so that a
            # spoken "bolt" still finds "Hex bolt". The gateway sends the same
            # filter either way — the leniency is the mock's, not the client's.
            text = contains.get("ProductDescription", "")
            rows = conn.execute(
                "SELECT DISTINCT matnr, maktx, meins FROM mard WHERE LOWER(maktx) LIKE %s"
                " ORDER BY maktx LIMIT 5", (f"%{text.lower().strip()}%",)).fetchall()
    return {"d": {"results": [{
        "Product": r["matnr"], "Language": "EN", "ProductDescription": r["maktx"],
        "BaseUnit": r["meins"],
    } for r in rows]}}


@router.get("/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder")
async def purchase_order(filter_: str | None = Query(None, alias="$filter")):
    try:
        eq, _ = _parse_filter(filter_)
    except _BadFilter as e:
        return _bad_filter(str(e))
    ebeln = str(eq.get("PurchaseOrder", "")).strip().replace(" ", "")
    with store.db() as conn:
        row = conn.execute("SELECT * FROM ekko WHERE ebeln=%s", (ebeln,)).fetchone()
        if row is None:
            return {"d": {"results": []}}
        mat = conn.execute("SELECT maktx FROM mard WHERE matnr=%s LIMIT 1", (row["matnr"],)).fetchone()
    return {"d": {"results": [{
        "PurchaseOrder": row["ebeln"], "Supplier": row["lifnr"], "Material": row["matnr"],
        "ProductDescription": mat["maktx"] if mat else "",
        "OrderQuantity": str(row["menge"]), "PurchasingDocumentStatus": row["status"],
        "ScheduleLineDeliveryDate": row["eta"],
    }]}}


@router.get("/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader")
async def list_documents(top: int = Query(10, alias="$top")):
    with store.db() as conn:
        rows = conn.execute("SELECT * FROM mkpf ORDER BY seq DESC LIMIT %s", (top,)).fetchall()
    return {"d": {"results": [{
        "MaterialDocument": r["mblnr"], "MaterialDocumentYear": r["mjahr"],
        "PostingDate": r["budat"], "GoodsMovementType": r["bwart"],
        "Material": r["matnr"], "QuantityInEntryUnit": str(r["menge"]),
        "EntryUnit": r["meins"], "StorageBin": r["lgpla"],
        "ReferenceDocument": r["reversed_of"],
        "Plant": r["werks"], "StorageLocation": r["lgort"], "PurchaseOrder": r["ebeln"],
        "CreationDateTime": r["created_at"],
        "MaterialDocumentHeaderText": r["bktxt"],
    } for r in rows]}}
