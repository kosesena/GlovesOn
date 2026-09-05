"""
GlovesOn Gateway
================
Sesli ajan ile SAP arasindaki koprü.

Ajan burayla konusur, burasi SAP ile. Ajan hicbir zaman SAP sekli gormez:
tool cevaplari sesli okunabilir cumlelerdir, OData zarfi degil. SAP'ye ozgu
her sey (CSRF, {"d": ...}, 18 hane MATNR, hareket turleri) sap_client.py'de.

Gercek bir S/4HANA'ya gecis = SAP_BASE_URL degiskeni. Baska hicbir sey.

Calistirma:
    uvicorn gateway.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from . import sap_client, sap_mock, store
from .sap_client import SapClient, SapError
from .store import norm_matnr, pretty_matnr

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")
TOOL_SHARED_SECRET = os.getenv("TOOL_SHARED_SECRET", "degistir-beni-lutfen")
AGENT_ID = os.getenv("AGENT_ID", "")

app = FastAPI(title="GlovesOn Gateway", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Mock S/4HANA'yi ayni surecte servis et. Gateway ona yine de HTTP ile,
# disaridan bir sistemmis gibi baglanir - kisayol yok.
app.include_router(sap_mock.router, prefix="/sap/opu/odata/sap", tags=["mock-s4hana"])

_sap: SapClient | None = None
_self_base: str | None = None


@app.middleware("http")
async def _remember_own_address(request, call_next):
    # SAP_BASE_URL verilmediginde gateway kendi icindeki mock S/4HANA'ya
    # baglanir. Kendi adresini ilk istekten ogrenir; boylece port neyse
    # (yerelde 8000, Replit'te baska) yapilandirma gerekmez.
    global _self_base
    if _self_base is None:
        _self_base = str(request.base_url).rstrip("/")
    return await call_next(request)


def sap() -> SapClient:
    global _sap
    if _sap is None:
        base = sap_client.SAP_BASE_URL or _self_base or "http://127.0.0.1:8000"
        _sap = SapClient(base)
    return _sap


# ---------------------------------------------------------------------------
# Canli olay akisi (demo ekrani)
# ---------------------------------------------------------------------------

_subscribers: list[asyncio.Queue] = []
_shutting_down = asyncio.Event()
SSE_MAX_LIFETIME_SECONDS = 50


@app.on_event("startup")
async def _on_startup() -> None:
    store.init_db()


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    _shutting_down.set()
    if _sap is not None:
        await _sap.aclose()


def publish(event_type: str, payload: dict[str, Any]) -> None:
    message = json.dumps({"type": event_type, "ts": time.time(), "data": payload})
    for queue in list(_subscribers):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass


@app.get("/events")
async def events() -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.append(queue)

    async def stream():
        deadline = time.monotonic() + SSE_MAX_LIFETIME_SECONDS
        try:
            yield "retry: 2000\n\n"
            while not _shutting_down.is_set() and time.monotonic() < deadline:
                try:
                    yield f"data: {await asyncio.wait_for(queue.get(), timeout=5)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            if queue in _subscribers:
                _subscribers.remove(queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def require_tool_auth(secret: str | None) -> None:
    if secret != TOOL_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Invalid tool secret")


# ---------------------------------------------------------------------------
# TOOL 1 — stok sorgula
# ---------------------------------------------------------------------------

@app.get("/erp/stock")
async def get_stock(
    material: str = Query(...),
    plant: str = Query("1000"),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)
    matnr = norm_matnr(material)

    try:
        # Gercek SAP'de de boyle: stok bir API'den, aciklama baskasindan.
        rows = await sap().get_stock(matnr, plant)
        desc = await sap().get_description(matnr)
    except SapError as e:
        publish("tool", {"tool": "get_stock", "ok": False, "code": e.code})
        return {"found": False, "message": e.message}

    if not rows:
        publish("tool", {"tool": "get_stock", "ok": False, "material": material})
        return {"found": False,
                "message": f"Material {pretty_matnr(matnr)} not found in plant {plant}."}

    locations = [{
        "LGORT": r["StorageLocation"], "LGPLA": r["StorageBin"],
        "LABST": int(float(r["MatlWrhsStkQtyInMatlBaseUnit"])), "MEINS": r["MaterialBaseUnit"],
    } for r in rows]

    result = {
        "found": True,
        "MATNR": pretty_matnr(matnr),
        "MAKTX": desc["ProductDescription"] if desc else "",
        "MEINS": rows[0]["MaterialBaseUnit"],
        "WERKS": plant,
        "total_unrestricted": sum(l["LABST"] for l in locations),
        "locations": locations,
    }
    publish("tool", {"tool": "get_stock", "ok": True, "result": result})
    return result


# ---------------------------------------------------------------------------
# TOOL 2 — malzeme ara
# ---------------------------------------------------------------------------

@app.get("/erp/material-search")
async def material_search(
    query: str = Query(...),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)
    try:
        rows = await sap().search_descriptions(query)
    except SapError as e:
        return {"count": 0, "matches": [], "message": e.message}

    matches = [{"MATNR": pretty_matnr(r["Product"]), "MAKTX": r["ProductDescription"],
                "MEINS": r["BaseUnit"]} for r in rows]
    publish("tool", {"tool": "material_search", "ok": True, "count": len(matches)})
    return {"count": len(matches), "matches": matches}


# ---------------------------------------------------------------------------
# TOOL 3 — mal girisi (YAZMA)
# ---------------------------------------------------------------------------

@app.post("/erp/goods-receipt")
async def post_goods_receipt(
    body: dict = Body(...),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)

    material, quantity = body.get("material"), body.get("quantity")
    if material is None or quantity is None:
        raise HTTPException(status_code=400, detail="material and quantity are required")
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return {"posted": False, "message": "Quantity must be a whole number."}
    if quantity <= 0:
        return {"posted": False, "message": "Quantity must be greater than zero."}

    plant = str(body.get("plant") or "1000")
    lgort = str(body.get("storage_location") or "0001")
    allow_duplicate = bool(body.get("allow_duplicate"))
    matnr = norm_matnr(material)

    try:
        rows = await sap().get_stock(matnr, plant)
        desc = await sap().get_description(matnr)
    except SapError as e:
        return {"posted": False, "message": e.message}
    if not rows:
        return {"posted": False,
                "message": f"Material {pretty_matnr(matnr)} is not stocked in plant {plant}."}

    unit = rows[0]["MaterialBaseUnit"]
    bin_ = next((r["StorageBin"] for r in rows if r["StorageLocation"] == lgort), rows[0]["StorageBin"])
    maktx = desc["ProductDescription"] if desc else ""

    # --- Ayni niyet iki kere kaydedilmesin ---------------------------------
    # Zaman asimina ugrayan bir yazma belirsizdir: belge dusmus ama cevap
    # donmemis olabilir. Isci cumleyi tekrar eder, stok iki kat artar.
    # Bu kontrol bilerek burada: gercek SAP ikinci girisi reddetmez, biz ederiz.
    if not allow_duplicate:
        dup = await _recent_identical(matnr, quantity, plant, lgort, body.get("purchase_order"))
        if dup is not None:
            seconds = int(time.time() - float(dup["CreationDateTime"]))
            publish("duplicate_blocked", {"MBLNR": dup["MaterialDocument"]})
            return {
                "posted": False, "duplicate": True,
                "MBLNR": dup["MaterialDocument"], "seconds_ago": seconds,
                "message": (
                    f"This exact posting already went through {seconds} seconds ago as "
                    f"material document {dup['MaterialDocument']}: {quantity} {unit} of "
                    f"{maktx} into bin {bin_}. Nothing was posted this time. Ask the worker "
                    f"whether this is a second, separate delivery. If it is, call again with "
                    f"allow_duplicate set to true."),
            }

    payload = sap_client.goods_receipt_payload(
        matnr, quantity, plant, lgort, unit, body.get("purchase_order"))

    try:
        d = await sap().post_material_document(payload)
    except SapError as e:
        return {"posted": False, "message": e.message}

    item = d["to_MaterialDocumentItem"]["results"][0]
    new_level = int(float(item["MaterialBaseUnitStockQuantity"]))
    result = {
        "posted": True, "MBLNR": d["MaterialDocument"], "MJAHR": d["MaterialDocumentYear"],
        "BWART": item["GoodsMovementType"], "MATNR": pretty_matnr(matnr), "MAKTX": maktx,
        "MENGE": quantity, "MEINS": unit, "WERKS": plant, "LGORT": lgort, "LGPLA": bin_,
        "BUDAT": d["PostingDate"], "new_stock_level": new_level,
        "message": (f"Material document {d['MaterialDocument']} posted. {quantity} {unit} of "
                    f"{maktx} received into bin {bin_}. New stock level is {new_level}."),
    }
    publish("goods_receipt", result)
    return result


DUPLICATE_WINDOW_SECONDS = 120


async def _recent_identical(matnr: str, quantity: int, plant: str, lgort: str,
                            ebeln: str | None) -> dict[str, Any] | None:
    """
    Son belgeleri SAP'den okuyup ayni niyetin kisa sure once kaydedilip
    kaydedilmedigine bakar. Gateway durumsuz kalir: hafizada bir sey tutmaz,
    dogruyu her zaman kayit sisteminden sorar.
    """
    try:
        docs = await sap().list_documents(10)
    except SapError:
        return None   # okuyamiyorsak yazmayi engellemeyiz; asil koruma sesli onay
    cutoff = time.time() - DUPLICATE_WINDOW_SECONDS
    for d in docs:
        if (d.get("GoodsMovementType") in ("101", "501")
                and d.get("Material") == matnr
                and int(float(d.get("QuantityInEntryUnit", 0))) == quantity
                and d.get("Plant") == plant
                and d.get("StorageLocation") == lgort
                and (d.get("PurchaseOrder") or None) == (ebeln or None)
                and float(d.get("CreationDateTime") or 0) >= cutoff):
            return d
    return None


# ---------------------------------------------------------------------------
# TOOL 4 — satinalma siparisi durumu
# ---------------------------------------------------------------------------

@app.get("/erp/purchase-order")
async def purchase_order(
    order: str = Query(...),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)
    try:
        row = await sap().get_purchase_order(str(order).strip().replace(" ", ""))
    except SapError as e:
        return {"found": False, "message": e.message}
    if row is None:
        return {"found": False, "message": f"Purchase order {order} was not found."}

    result = {"found": True, "EBELN": row["PurchaseOrder"], "LIFNR": row["Supplier"],
              "MATNR": pretty_matnr(row["Material"]), "MAKTX": row["ProductDescription"],
              "MENGE": int(float(row["OrderQuantity"])),
              "status": row["PurchasingDocumentStatus"],
              "expected_delivery": row["ScheduleLineDeliveryDate"]}
    publish("tool", {"tool": "purchase_order", "ok": True, "result": result})
    return result


# ---------------------------------------------------------------------------
# Demo ekrani destek uclari
# ---------------------------------------------------------------------------

@app.get("/api/voice-token")
async def voice_token() -> dict[str, Any]:
    if not ASSEMBLYAI_API_KEY:
        raise HTTPException(status_code=500, detail="ASSEMBLYAI_API_KEY is not set")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://agents.assemblyai.com/v1/token",
                             params={"expires_in_seconds": 300, "max_session_duration_seconds": 600},
                             headers={"Authorization": f"Bearer {ASSEMBLYAI_API_KEY}"})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Token error: {r.text}")
    return {"token": r.json()["token"], "agent_id": AGENT_ID}


@app.get("/api/inventory")
def inventory() -> dict[str, Any]:
    with closing(store.db()) as conn:
        rows = conn.execute("SELECT * FROM mard ORDER BY matnr, lgort").fetchall()
        docs = conn.execute("SELECT * FROM mkpf ORDER BY rowid DESC LIMIT 10").fetchall()
    return {
        "stock": [{"MATNR": pretty_matnr(r["matnr"]), "MAKTX": r["maktx"], "WERKS": r["werks"],
                   "LGORT": r["lgort"], "LGPLA": r["lgpla"], "LABST": r["labst"],
                   "MEINS": r["meins"]} for r in rows],
        "documents": [{"MBLNR": d["mblnr"], "BWART": d["bwart"], "MATNR": pretty_matnr(d["matnr"]),
                       "MENGE": d["menge"], "MEINS": d["meins"], "LGPLA": d["lgpla"],
                       "BUDAT": d["budat"]} for d in docs],
    }


@app.post("/api/reset")
def reset() -> dict[str, str]:
    store.init_db(force=True)
    publish("reset", {})
    return {"status": "reset"}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "agent_id": AGENT_ID or None,
            "sap_base_url": sap_client.SAP_BASE_URL or f"{_self_base} (mock S/4HANA)"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
