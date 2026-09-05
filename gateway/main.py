"""
GlovesOn Gateway
==============
AssemblyAI Voice Agent API ile SAP arasindaki koprü.

Iki isi var:
  1. Agent'in HTTP tool'larini karsilar (stok sorgu, mal girisi, siparis durumu)
  2. Demo ekranina canli olay akisi (SSE) yayinlar

Alan adlari bilerek SAP sozlesmesine sadik (MATNR, WERKS, LGORT, LABST, BWART...).
Boylece mock'tan gercek SAP OData servisine gecis = sadece BASE URL degisikligi.

Calistirma:
    pip install -r requirements.txt
    uvicorn gateway.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import httpx
from dotenv import load_dotenv
from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "gateway" / "gloveson.db"
WEB_DIR = ROOT / "web"

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")
TOOL_SHARED_SECRET = os.getenv("TOOL_SHARED_SECRET", "degistir-beni-lutfen")
AGENT_ID = os.getenv("AGENT_ID", "")

app = FastAPI(title="GlovesOn Gateway", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# SAP alan adi yardimcilari
# --------------------------------------------------------------------------

def norm_matnr(raw: str | int) -> str:
    """
    SAP MATNR 18 karakterlik, sifirla soldan doldurulmus bir alandir.
    Kullanici sesle '4711' der; SAP '000000000000004711' bekler.
    Bu fonksiyon iki dunyayi birlestirir.
    """
    s = str(raw).strip().upper().replace(" ", "").replace("-", "")
    if s.isdigit():
        return s.zfill(18)
    return s


def pretty_matnr(matnr: str) -> str:
    """18 haneli MATNR'yi insana/sese uygun hale getirir."""
    return matnr.lstrip("0") or "0"


# --------------------------------------------------------------------------
# Veritabani
# --------------------------------------------------------------------------

SEED_MATERIALS = [
    # (MATNR, MAKTX aciklama, MEINS birim, WERKS, LGORT, LGPLA raf, LABST stok)
    ("4711", "Hex Bolt M8x40 Zinc Plated", "EA", "1000", "0001", "A-03-02", 240),
    ("4712", "Hex Nut M8 Stainless", "EA", "1000", "0001", "A-03-05", 1850),
    ("4713", "Hydraulic Hose 12mm 2m", "EA", "1000", "0001", "B-01-11", 36),
    ("5100", "Ball Bearing 6204-2RS", "EA", "1000", "0002", "C-07-01", 122),
    ("5101", "Timing Belt 8M-1200", "EA", "1000", "0002", "C-07-04", 18),
    ("6200", "Industrial Grease EP2 400g", "KG", "1000", "0002", "D-02-09", 74),
    ("6201", "Cutting Fluid Concentrate 20L", "L", "1000", "0002", "D-02-12", 9),
    ("7300", "Safety Gloves Cut Level 5 (L)", "PC", "1000", "0001", "E-05-03", 410),
]

SEED_ORDERS = [
    # (EBELN siparis, LIFNR tedarikci, MATNR, MENGE, STATUS, ETA)
    ("4500001234", "Bosch Rexroth AG", "4713", 50, "Partially Delivered", "2026-09-11"),
    ("4500001235", "SKF Turkiye", "5100", 200, "Open", "2026-09-18"),
    ("4500001236", "Fuchs Lubricants", "6201", 40, "Delivered", "2026-09-02"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS mard (
    matnr TEXT NOT NULL,
    maktx TEXT NOT NULL,
    meins TEXT NOT NULL,
    werks TEXT NOT NULL,
    lgort TEXT NOT NULL,
    lgpla TEXT NOT NULL,
    labst INTEGER NOT NULL,
    PRIMARY KEY (matnr, werks, lgort)
);
CREATE TABLE IF NOT EXISTS mkpf (
    mblnr TEXT PRIMARY KEY,
    bwart TEXT NOT NULL,
    matnr TEXT NOT NULL,
    menge INTEGER NOT NULL,
    meins TEXT NOT NULL,
    werks TEXT NOT NULL,
    lgort TEXT NOT NULL,
    lgpla TEXT NOT NULL,
    budat TEXT NOT NULL,
    ebeln TEXT
);
CREATE TABLE IF NOT EXISTS ekko (
    ebeln TEXT PRIMARY KEY,
    lifnr TEXT NOT NULL,
    matnr TEXT NOT NULL,
    menge INTEGER NOT NULL,
    status TEXT NOT NULL,
    eta TEXT NOT NULL
);
"""


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(force: bool = False) -> None:
    if force and DB_PATH.exists():
        DB_PATH.unlink()
    with closing(db()) as conn:
        conn.executescript(SCHEMA)
        already = conn.execute("SELECT COUNT(*) c FROM mard").fetchone()["c"]
        if not already:
            conn.executemany(
                "INSERT INTO mard (matnr, maktx, meins, werks, lgort, lgpla, labst)"
                " VALUES (?,?,?,?,?,?,?)",
                [
                    (norm_matnr(m), desc, uom, werks, lgort, bin_, qty)
                    for m, desc, uom, werks, lgort, bin_, qty in SEED_MATERIALS
                ],
            )
            conn.executemany(
                "INSERT INTO ekko (ebeln, lifnr, matnr, menge, status, eta)"
                " VALUES (?,?,?,?,?,?)",
                [
                    (ebeln, lifnr, norm_matnr(m), qty, status, eta)
                    for ebeln, lifnr, m, qty, status, eta in SEED_ORDERS
                ],
            )
        conn.commit()


# --------------------------------------------------------------------------
# Canli olay akisi (demo ekrani icin)
# --------------------------------------------------------------------------

_subscribers: list[asyncio.Queue] = []


def publish(event_type: str, payload: dict[str, Any]) -> None:
    """Demo ekranindaki herkese olay yayinla. Sessizce basarisiz olur."""
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
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            if queue in _subscribers:
                _subscribers.remove(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------
# Tool kimlik dogrulama
# --------------------------------------------------------------------------

def require_tool_auth(secret: str | None) -> None:
    """
    AssemblyAI tool header'larini sifreli saklar ve her cagrida gonderir.
    Gateway public HTTPS'te durdugu icin bu kontrol sart.
    """
    if secret != TOOL_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Invalid tool secret")


# --------------------------------------------------------------------------
# TOOL 1 - Stok sorgula
# --------------------------------------------------------------------------

@app.get("/erp/stock")
def get_stock(
    material: str = Query(..., description="Malzeme numarasi, orn. 4711"),
    plant: str = Query("1000", description="Uretim yeri / WERKS"),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)
    matnr = norm_matnr(material)

    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM mard WHERE matnr = ? AND werks = ?", (matnr, plant)
        ).fetchall()

    if not rows:
        publish("tool", {"tool": "get_stock", "ok": False, "material": material})
        # Agent'in sese cevirebilecegi net bir hata - kod degil, cumle.
        return {
            "found": False,
            "message": f"Material {pretty_matnr(matnr)} not found in plant {plant}.",
        }

    locations = [
        {
            "LGORT": r["lgort"],
            "LGPLA": r["lgpla"],
            "LABST": r["labst"],
            "MEINS": r["meins"],
        }
        for r in rows
    ]
    total = sum(r["labst"] for r in rows)
    result = {
        "found": True,
        "MATNR": pretty_matnr(matnr),
        "MAKTX": rows[0]["maktx"],
        "MEINS": rows[0]["meins"],
        "WERKS": plant,
        "total_unrestricted": total,
        "locations": locations,
    }
    publish("tool", {"tool": "get_stock", "ok": True, "result": result})
    return result


# --------------------------------------------------------------------------
# TOOL 2 - Malzeme ara (sesle numara yerine isim soylendiginde)
# --------------------------------------------------------------------------

@app.get("/erp/material-search")
def material_search(
    query: str = Query(..., description="Malzeme aciklamasindan parca, orn. 'bearing'"),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT DISTINCT matnr, maktx, meins FROM mard"
            " WHERE LOWER(maktx) LIKE ? ORDER BY maktx LIMIT 5",
            (f"%{query.lower().strip()}%",),
        ).fetchall()

    matches = [
        {"MATNR": pretty_matnr(r["matnr"]), "MAKTX": r["maktx"], "MEINS": r["meins"]}
        for r in rows
    ]
    publish("tool", {"tool": "material_search", "ok": True, "count": len(matches)})
    return {"count": len(matches), "matches": matches}


# --------------------------------------------------------------------------
# TOOL 3 - Mal girisi kaydet (YAZMA islemi - execution_mode: hold)
# --------------------------------------------------------------------------

@app.post("/erp/goods-receipt")
def post_goods_receipt(
    body: dict = Body(...),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)

    material = body.get("material")
    quantity = body.get("quantity")
    plant = str(body.get("plant") or "1000")
    storage_location = str(body.get("storage_location") or "0001")
    purchase_order = body.get("purchase_order")

    if material is None or quantity is None:
        raise HTTPException(status_code=400, detail="material and quantity are required")

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return {"posted": False, "message": "Quantity must be a whole number."}

    if quantity <= 0:
        return {"posted": False, "message": "Quantity must be greater than zero."}

    matnr = norm_matnr(material)

    with closing(db()) as conn:
        row = conn.execute(
            "SELECT * FROM mard WHERE matnr = ? AND werks = ? AND lgort = ?",
            (matnr, plant, storage_location),
        ).fetchone()

        if row is None:
            return {
                "posted": False,
                "message": (
                    f"Material {pretty_matnr(matnr)} is not stocked in plant {plant}, "
                    f"storage location {storage_location}."
                ),
            }

        # BWART 101 = satinalma siparisine karsi mal girisi
        # BWART 501 = siparissiz mal girisi
        bwart = "101" if purchase_order else "501"
        mblnr = f"49{random.randint(10_000_000, 99_999_999)}"
        budat = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_qty = row["labst"] + quantity

        conn.execute(
            "UPDATE mard SET labst = ? WHERE matnr = ? AND werks = ? AND lgort = ?",
            (new_qty, matnr, plant, storage_location),
        )
        conn.execute(
            "INSERT INTO mkpf (mblnr, bwart, matnr, menge, meins, werks, lgort, lgpla,"
            " budat, ebeln) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                mblnr, bwart, matnr, quantity, row["meins"], plant,
                storage_location, row["lgpla"], budat, purchase_order,
            ),
        )
        conn.commit()

    result = {
        "posted": True,
        "MBLNR": mblnr,
        "BWART": bwart,
        "MATNR": pretty_matnr(matnr),
        "MAKTX": row["maktx"],
        "MENGE": quantity,
        "MEINS": row["meins"],
        "WERKS": plant,
        "LGORT": storage_location,
        "LGPLA": row["lgpla"],
        "BUDAT": budat,
        "new_stock_level": new_qty,
        "message": (
            f"Material document {mblnr} posted. {quantity} {row['meins']} of "
            f"{row['maktx']} received into bin {row['lgpla']}. "
            f"New stock level is {new_qty}."
        ),
    }
    publish("goods_receipt", result)
    return result


# --------------------------------------------------------------------------
# TOOL 4 - Satinalma siparisi durumu
# --------------------------------------------------------------------------

@app.get("/erp/purchase-order")
def purchase_order(
    order: str = Query(..., description="Siparis numarasi / EBELN"),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)
    ebeln = str(order).strip().replace(" ", "")

    with closing(db()) as conn:
        row = conn.execute("SELECT * FROM ekko WHERE ebeln = ?", (ebeln,)).fetchone()
        if row is None:
            publish("tool", {"tool": "purchase_order", "ok": False, "order": ebeln})
            return {"found": False, "message": f"Purchase order {ebeln} was not found."}
        mat = conn.execute(
            "SELECT maktx FROM mard WHERE matnr = ? LIMIT 1", (row["matnr"],)
        ).fetchone()

    result = {
        "found": True,
        "EBELN": row["ebeln"],
        "LIFNR": row["lifnr"],
        "MATNR": pretty_matnr(row["matnr"]),
        "MAKTX": mat["maktx"] if mat else "",
        "MENGE": row["menge"],
        "status": row["status"],
        "expected_delivery": row["eta"],
    }
    publish("tool", {"tool": "purchase_order", "ok": True, "result": result})
    return result


# --------------------------------------------------------------------------
# Demo ekrani destek uclari (tool degil - sadece arayuz icin)
# --------------------------------------------------------------------------

@app.get("/api/voice-token")
async def voice_token() -> dict[str, Any]:
    """Tarayiciya kisa omurlu token uretir. API anahtari asla tarayiciya gitmez."""
    if not ASSEMBLYAI_API_KEY:
        raise HTTPException(status_code=500, detail="ASSEMBLYAI_API_KEY is not set")

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            "https://agents.assemblyai.com/v1/token",
            params={"expires_in_seconds": 300, "max_session_duration_seconds": 600},
            headers={"Authorization": f"Bearer {ASSEMBLYAI_API_KEY}"},
        )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Token error: {response.text}")

    return {"token": response.json()["token"], "agent_id": AGENT_ID}


@app.get("/api/inventory")
def inventory() -> dict[str, Any]:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM mard ORDER BY matnr, lgort"
        ).fetchall()
        docs = conn.execute(
            "SELECT * FROM mkpf ORDER BY rowid DESC LIMIT 10"
        ).fetchall()
    return {
        "stock": [
            {
                "MATNR": pretty_matnr(r["matnr"]),
                "MAKTX": r["maktx"],
                "WERKS": r["werks"],
                "LGORT": r["lgort"],
                "LGPLA": r["lgpla"],
                "LABST": r["labst"],
                "MEINS": r["meins"],
            }
            for r in rows
        ],
        "documents": [
            {
                "MBLNR": d["mblnr"],
                "BWART": d["bwart"],
                "MATNR": pretty_matnr(d["matnr"]),
                "MENGE": d["menge"],
                "MEINS": d["meins"],
                "LGPLA": d["lgpla"],
                "BUDAT": d["budat"],
            }
            for d in docs
        ],
    }


@app.post("/api/reset")
def reset() -> dict[str, str]:
    """Demo cekimi oncesi temiz baslangic."""
    init_db(force=True)
    publish("reset", {})
    return {"status": "reset"}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "agent_id": AGENT_ID or None}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


init_db()
