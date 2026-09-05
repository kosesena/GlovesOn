"""
Mock S/4HANA — gercek released OData API'lerinin sozlesmesini konusur.

Bunun gateway'in *icinde* degil *karsisinda* durmasi kasitli. Gateway ona
gercek bir HTTP istemcisi gibi baglaniyor: CSRF token aliyor, OData govdesi
gonderiyor, {"d": ...} cevabi ayristiriyor. Boylece "gercek SAP'ye gecis tek
bir base URL degisikligi" cumlesi mecaz degil, harfiyen dogru oluyor.

Taklit edilen released API'ler:
  API_MATERIAL_DOCUMENT_SRV      A_MaterialDocumentHeader   (mal hareketi yazma)
  API_MATERIAL_STOCK_SRV         A_MatlStkInAcctMod         (stok okuma)
  API_PRODUCT_SRV                A_ProductDescription       (malzeme aciklamasi)
  API_PURCHASEORDER_PROCESS_SRV  A_PurchaseOrder            (siparis durumu)

Gercek SAP'de de oyle: stok bir API'den, aciklama baskasindan gelir. Tek
cagriyla halledilmez ve bu, gecikme butcesini dogrudan etkiler.
"""

from __future__ import annotations

import random
import secrets
import time
from contextlib import closing
from datetime import datetime, timezone

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import JSONResponse

from . import store
from .store import norm_matnr, pretty_matnr

router = APIRouter()

# Gecerli CSRF token'lari. Gercek SAP bunu oturum cerezine bagli tutar.
_tokens: dict[str, float] = {}
TOKEN_TTL_SECONDS = 1800

# GoodsMovementCode -> hangi islem. SAP'nin kendi kodlari:
#   01 satinalma siparisine karsi mal girisi   (MIGO / MB01)
#   05 siparissiz diger mal girisleri          (MB1C)
#   06 siparise karsi mal cikisi
GMC_FOR_MOVEMENT = {"101": "01", "102": "01", "501": "05", "502": "05"}


def _odata_error(code: str, message: str, status: int = 400) -> JSONResponse:
    """SAP'nin OData v2 hata zarfi."""
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": {"lang": "en", "value": message}}},
    )


def _issue_token() -> str:
    tok = secrets.token_urlsafe(24)
    _tokens[tok] = time.time() + TOKEN_TTL_SECONDS
    # suresi gecmisleri temizle
    for t, exp in list(_tokens.items()):
        if exp < time.time():
            _tokens.pop(t, None)
    return tok


def _token_valid(tok: str | None) -> bool:
    return bool(tok) and _tokens.get(tok, 0) > time.time()


# ---------------------------------------------------------------------------
# CSRF el sikismasi
# ---------------------------------------------------------------------------

@router.api_route("/API_MATERIAL_DOCUMENT_SRV/", methods=["GET", "HEAD"])
async def service_root(
    response: Response,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    """
    SAP'ye yazmadan once buraya 'X-CSRF-Token: Fetch' ile gelinir, token
    alinir, sonra POST'ta geri gonderilir. Bunu atlayan her yazma 403 alir.
    """
    if (x_csrf_token or "").lower() == "fetch":
        token = _issue_token()
        response.headers["X-CSRF-Token"] = token
        response.headers["Set-Cookie"] = f"SAP_SESSIONID_GLV_100={secrets.token_hex(8)}; Path=/"
    return {"d": {"EntitySets": ["A_MaterialDocumentHeader", "A_MaterialDocumentItem"]}}


# ---------------------------------------------------------------------------
# Mal hareketi yazma
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
    # Baslik alanlari. Gercek S/4HANA taniomadigi alanlari sessizce dusurmez,
    # bunlari tanir ve saklar; ayni sadakat burada da.
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

    with closing(store.db()) as conn:
        row = conn.execute(
            "SELECT * FROM mard WHERE matnr=? AND werks=? AND lgort=?", (matnr, werks, lgort)
        ).fetchone()
        if row is None:
            return _odata_error(
                "M7_042",
                f"Material {pretty_matnr(matnr)} is not maintained in plant {werks}, "
                f"storage location {lgort}.",
            )

        # Ters kayit (102): asil belgeyi bul ve stoktan dus
        if bwart in ("102", "502"):
            orig = conn.execute(
                "SELECT * FROM mkpf WHERE mblnr=?", (str(reversed_of or ""),)
            ).fetchone()
            if orig is None:
                return _odata_error("M7_054", f"Material document {reversed_of} does not exist.")
            if orig["bwart"] in ("102", "502"):
                return _odata_error("M7_055", f"Material document {reversed_of} is itself a reversal.")
            already = conn.execute(
                "SELECT mblnr FROM mkpf WHERE reversed_of=?", (str(reversed_of),)
            ).fetchone()
            if already:
                return _odata_error(
                    "M7_056",
                    f"Material document {reversed_of} was already reversed by {already['mblnr']}.",
                )
            delta = -orig["menge"]
            menge = orig["menge"]
        else:
            # Not: gercek S/4HANA ayni mal girisini iki kez seve seve kabul eder.
            # Tekrar korumasi bilerek burada degil, gateway'de - cunku o koruma
            # SAP'ye degil bize ait. Bkz. docs/adr/0002.
            delta = menge

        mblnr = f"49{random.randint(10_000_000, 99_999_999)}"
        mjahr = datetime.now(timezone.utc).strftime("%Y")
        budat = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        conn.execute(
            "UPDATE mard SET labst = labst + ? WHERE matnr=? AND werks=? AND lgort=?",
            (delta, matnr, werks, lgort),
        )
        conn.execute(
            "INSERT INTO mkpf (mblnr, mjahr, bwart, matnr, menge, meins, werks, lgort,"
            " lgpla, budat, ebeln, reversed_of, created_at, bktxt, xblnr)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mblnr, mjahr, bwart, matnr, menge, row["meins"], werks, lgort,
             row["lgpla"], budat, ebeln, reversed_of, time.time(), bktxt, xblnr),
        )
        new_level = conn.execute(
            "SELECT labst FROM mard WHERE matnr=? AND werks=? AND lgort=?", (matnr, werks, lgort)
        ).fetchone()["labst"]
        conn.commit()

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
# Okuma uclari
# ---------------------------------------------------------------------------

@router.get("/API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod")
async def material_stock(material: str = Query(..., alias="Material"),
                         plant: str = Query("1000", alias="Plant")):
    matnr = norm_matnr(material)
    with closing(store.db()) as conn:
        rows = conn.execute(
            "SELECT * FROM mard WHERE matnr=? AND werks=? ORDER BY lgort", (matnr, plant)
        ).fetchall()
    return {"d": {"results": [{
        "Material": r["matnr"], "Plant": r["werks"], "StorageLocation": r["lgort"],
        "StorageBin": r["lgpla"], "MatlWrhsStkQtyInMatlBaseUnit": str(r["labst"]),
        "MaterialBaseUnit": r["meins"],
    } for r in rows]}}


@router.get("/API_PRODUCT_SRV/A_ProductDescription")
async def product_description(product: str | None = Query(None, alias="Product"),
                              search: str | None = Query(None, alias="search")):
    with closing(store.db()) as conn:
        if product:
            rows = conn.execute(
                "SELECT DISTINCT matnr, maktx, meins FROM mard WHERE matnr=?",
                (norm_matnr(product),)).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT matnr, maktx, meins FROM mard WHERE LOWER(maktx) LIKE ?"
                " ORDER BY maktx LIMIT 5", (f"%{(search or '').lower().strip()}%",)).fetchall()
    return {"d": {"results": [{
        "Product": r["matnr"], "Language": "EN", "ProductDescription": r["maktx"],
        "BaseUnit": r["meins"],
    } for r in rows]}}


@router.get("/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder")
async def purchase_order(order: str = Query(..., alias="PurchaseOrder")):
    ebeln = str(order).strip().replace(" ", "")
    with closing(store.db()) as conn:
        row = conn.execute("SELECT * FROM ekko WHERE ebeln=?", (ebeln,)).fetchone()
        if row is None:
            return {"d": {"results": []}}
        mat = conn.execute("SELECT maktx FROM mard WHERE matnr=? LIMIT 1", (row["matnr"],)).fetchone()
    return {"d": {"results": [{
        "PurchaseOrder": row["ebeln"], "Supplier": row["lifnr"], "Material": row["matnr"],
        "ProductDescription": mat["maktx"] if mat else "",
        "OrderQuantity": str(row["menge"]), "PurchasingDocumentStatus": row["status"],
        "ScheduleLineDeliveryDate": row["eta"],
    }]}}


@router.get("/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader")
async def list_documents(top: int = Query(10, alias="$top")):
    with closing(store.db()) as conn:
        rows = conn.execute("SELECT * FROM mkpf ORDER BY rowid DESC LIMIT ?", (top,)).fetchall()
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
