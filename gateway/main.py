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
import hmac
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from . import audit, live, sap_client, sap_mock, store
from .sap_client import SapClient, SapError, env
from .store import norm_matnr, pretty_matnr

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

ASSEMBLYAI_API_KEY = env("ASSEMBLYAI_API_KEY")
TOOL_SHARED_SECRET = env("TOOL_SHARED_SECRET")
AGENT_ID = env("AGENT_ID")

# Yerelde uvicorn'a verdigimiz port. Mock'a artik bu port uzerinden
# gidilmiyor (bkz. asagisi), sadece serve.sh ile ayni sayida anlasmak icin.
PORT = int(env("PORT", "8000"))

# Demo ekranindaki "sifirla" dugmesi mock veritabanini bastan kurar ve kimlik
# sormaz. Varsayilan artik KAPALI: acik bir varsayilan, adresi bilen herkesin
# demoyu jurinin altindan silebilecegi anlamina geliyordu - canli adreste
# denendi ve calisti. Provada acmak icin GLOVESON_ENABLE_RESET=1.
ENABLE_RESET = env("GLOVESON_ENABLE_RESET", "0") in ("1", "true", "yes")

# Paylasilan sir eskiden .env.example'daki metne dusuyordu. Yerelde zararsizdi;
# public bir adreste, dokumante edilmis bir varsayilan sir demek sirsizlik
# demek. Eksikse acilista duruyoruz - sessizce korumasiz calismaktansa
# hic calismamak.
if not TOOL_SHARED_SECRET or TOOL_SHARED_SECRET == "degistir-beni-lutfen":
    raise RuntimeError(
        "TOOL_SHARED_SECRET is unset or still the placeholder from .env.example. "
        "Set it to a value of your own (locally in .env, on Vercel in the project's "
        "environment variables) and make sure ./publish.sh runs with the same value."
    )

@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Acilis ve kapanis. Kapanista _sap'i None'a cekmek bir ayrinti degil:
    onceden sadece aclose() cagriliyordu, yani singleton kapali bir HTTP
    istemcisiyle ayakta kaliyordu ve uygulama ayni surecte ikinci kez
    baslatilamiyordu. Uretimde surec basina tek omur oldugu icin hic
    gorunmedi; testler ilk kosuda ortaya cikardi.
    """
    global _sap
    store.init_db()
    audit.init()
    live.init()
    try:
        yield
    finally:
        _shutting_down.set()
        if _sap is not None:
            await _sap.aclose()
            _sap = None


app = FastAPI(title="GlovesOn Gateway", version="0.2.0", lifespan=lifespan)

# Mock S/4HANA KENDI uygulamasinda. Bu bir duzen tercihi degil, bir guvenlik
# duzeltmesi: mock public uygulamaya bagliyken herkes CSRF token'ini alip
# dogrudan A_MaterialDocumentHeader'a POST edebiliyordu - paylasilan sir yok,
# sesli onay yok, tekrar korumasi yok, denetim izi yok. Yani "her yazma
# onaylanir" iddiasi internetten tek komutla curutulebiliyordu.
#
# Gateway ona yine HTTP ile, disaridan bir sistemmis gibi baglaniyor; degisen
# tek sey isteklerin bu ikinci uygulamaya gitmesi ve disaridan hicbir yolun
# oraya cikmamasi. SAP'ye giden tek kapi /erp/* uclari, onlar da sirli.
mock_app = FastAPI(title="Mock S/4HANA", version="0.2.0")
mock_app.include_router(sap_mock.router, prefix="/sap/opu/odata/sap", tags=["mock-s4hana"])

_sap: SapClient | None = None

# Mock S/4HANA'ya nasil gidilecegi. Uc olasilik, tek kod yolu:
#   SAP_BASE_URL      -> gercek bir tenant, normal HTTP
#   MOCK_SAP_BASE_URL -> mock ayri bir surecte, normal HTTP
#   ikisi de yoksa    -> mock ayni uygulamada, ASGI tasiyicisiyla
#
# Ucuncusu sunucusuz ortamin dayattigi sey: dinleyen bir port olmadigi icin
# loopback yok, kendi public adresimize gitmek ise istegi veri merkezinden
# cikarip geri sokar - her ERP cagrisinda bir tur ag gecikmesi ve iki kat
# fonksiyon cagrisi. ADR-0003'un sarti "mock disaridan bir sistem gibi
# cagrilsin" idi; OData yolu, CSRF el sikismasi ve hata zarfi aynen duruyor,
# degisen tek sey baytlarin sokete cikip cikmadigi.
MOCK_SAP_BASE_URL = env("MOCK_SAP_BASE_URL").rstrip("/")


def sap() -> SapClient:
    global _sap
    if _sap is None:
        if sap_client.SAP_BASE_URL:
            _sap = SapClient(sap_client.SAP_BASE_URL)
        elif MOCK_SAP_BASE_URL:
            _sap = SapClient(MOCK_SAP_BASE_URL)
        else:
            _sap = SapClient("http://mock-s4hana.internal",
                             transport=httpx.ASGITransport(app=mock_app))
    return _sap


def sap_target() -> str:
    if sap_client.SAP_BASE_URL:
        return sap_client.SAP_BASE_URL
    if MOCK_SAP_BASE_URL:
        return f"{MOCK_SAP_BASE_URL} (mock S/4HANA, over HTTP)"
    return "in-process ASGI (mock S/4HANA)"


# ---------------------------------------------------------------------------
# Canli olay akisi (demo ekrani)
# ---------------------------------------------------------------------------

_shutting_down = asyncio.Event()
SSE_MAX_LIFETIME_SECONDS = 50
EVENT_POLL_SECONDS = 0.4


def publish(event_type: str, payload: dict[str, Any]) -> None:
    live.publish(event_type, payload)


@app.get("/events")
async def events() -> StreamingResponse:
    # Akis, olaylari veritabanindan okuyor: ekrani tutan ornek ile yazmayi
    # yapan ornek ayni olmayabilir. Bkz. live.py.
    last_id = await asyncio.to_thread(live.latest_id)

    async def stream():
        nonlocal last_id
        deadline = time.monotonic() + SSE_MAX_LIFETIME_SECONDS
        idle = 0.0
        yield "retry: 2000\n\n"
        while not _shutting_down.is_set() and time.monotonic() < deadline:
            rows = await asyncio.to_thread(live.since, last_id)
            if rows:
                idle = 0.0
                for event_id, payload in rows:
                    last_id = event_id
                    yield f"data: {payload}\n\n"
            else:
                idle += EVENT_POLL_SECONDS
                if idle >= 5:
                    idle = 0.0
                    yield ": keep-alive\n\n"
            await asyncio.sleep(EVENT_POLL_SECONDS)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def require_tool_auth(secret: str | None) -> None:
    # compare_digest: esitligi karakter karakter kisa devre yapmadan olcer.
    if not secret or not hmac.compare_digest(secret, TOOL_SHARED_SECRET):
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
        "total_unrestricted": sum(loc["LABST"] for loc in locations),
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
    # Denetim izi icin: isciye okunup onaylanan cumle ve oturum referansi.
    # Yoklugu yazmayi DURDURMAZ - izi zenginlestirir, sart kosmaz. Bir yazma
    # kimlik dogrulamaya degil onaya dayanir; bkz. docs/adr/0002.
    utterance = str(body.get("confirmed_utterance") or "")
    session_id = str(body.get("session_id") or "") or live.current_session()

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
        matnr, quantity, plant, lgort, unit, body.get("purchase_order"),
        session_ref=session_id or None)

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
        "posted_at": time.time(),
        "message": (f"Material document {d['MaterialDocument']} posted. {quantity} {unit} of "
                    f"{maktx} received into bin {bin_}. New stock level is {new_level}."),
    }
    audit.record(d["MaterialDocument"], "goods_receipt", utterance, session_id)
    publish("goods_receipt", {**result, "session_id": session_id})
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
# TOOL 4 — son belgeler
# ---------------------------------------------------------------------------

@app.get("/erp/recent-documents")
async def recent_documents(
    limit: int = Query(5),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)
    try:
        docs = await sap().list_documents(min(limit, 10))
    except SapError as e:
        return {"count": 0, "documents": [], "message": e.message}

    out = []
    for d in docs:
        reversal = d.get("GoodsMovementType") in ("102", "502")
        out.append({
            "MBLNR": d["MaterialDocument"],
            "BWART": d["GoodsMovementType"],
            "MATNR": pretty_matnr(d["Material"]),
            "MENGE": int(float(d["QuantityInEntryUnit"])),
            "MEINS": d["EntryUnit"],
            "LGPLA": d["StorageBin"],
            "BUDAT": d["PostingDate"],
            "is_reversal": reversal,
            "reverses": d.get("ReferenceDocument"),
        })
    publish("tool", {"tool": "recent_documents", "ok": True, "count": len(out)})
    return {"count": len(out), "documents": out}


# ---------------------------------------------------------------------------
# TOOL 5 — mal girisini iptal et (YAZMA)
#
# SAP'de yanlis bir belge SILINMEZ. Ters kayit atilir: 101'in tersi 102,
# 501'in tersi 502. Stok geri iner ama iki belge de tarihte durur ve
# denetlenebilir kalir. Bu yuzden "iptal" de tam anlamiyla bir yazma islemi
# ve mal girisiyle ayni korumalarin arkasinda.
# ---------------------------------------------------------------------------

@app.post("/erp/reverse-goods-receipt")
async def reverse_goods_receipt(
    body: dict = Body(...),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)

    document = str(body.get("document") or "").strip()
    if not document:
        raise HTTPException(status_code=400, detail="document is required")
    utterance = str(body.get("confirmed_utterance") or "")
    session_id = str(body.get("session_id") or "")

    try:
        docs = await sap().list_documents(10)
    except SapError as e:
        return {"reversed": False, "message": e.message}

    original = next((d for d in docs if d["MaterialDocument"] == document), None)
    if original is None:
        return {"reversed": False,
                "message": f"Material document {document} is not among the recent postings. "
                           f"Ask the worker to read the number again."}

    if original["GoodsMovementType"] in ("102", "502"):
        return {"reversed": False,
                "message": f"Material document {document} is itself a reversal. "
                           f"It cannot be reversed again."}

    if any(d.get("ReferenceDocument") == document for d in docs):
        already = next(d["MaterialDocument"] for d in docs if d.get("ReferenceDocument") == document)
        return {"reversed": False,
                "message": f"Material document {document} was already reversed by {already}. "
                           f"The stock has already been corrected."}

    try:
        desc = await sap().get_description(original["Material"])
        payload = sap_client.reversal_payload(
            original["Material"], original["Plant"], original["StorageLocation"],
            original["EntryUnit"], document, original["GoodsMovementType"],
            session_ref=session_id or None)
        d = await sap().post_material_document(payload)
    except SapError as e:
        return {"reversed": False, "message": e.message}

    item = d["to_MaterialDocumentItem"]["results"][0]
    new_level = int(float(item["MaterialBaseUnitStockQuantity"]))
    maktx = desc["ProductDescription"] if desc else ""
    qty = int(float(item["QuantityInEntryUnit"]))

    result = {
        "reversed": True,
        "MBLNR": d["MaterialDocument"],
        "reverses": document,
        "BWART": item["GoodsMovementType"],
        "MATNR": pretty_matnr(original["Material"]),
        "MAKTX": maktx,
        "MENGE": qty,
        "MEINS": original["EntryUnit"],
        "LGORT": original["StorageLocation"],
        "LGPLA": original["StorageBin"],
        "new_stock_level": new_level,
        "posted_at": time.time(),
        "message": (f"Material document {d['MaterialDocument']} reverses {document}. "
                    f"{qty} {original['EntryUnit']} of {maktx} taken back out of bin "
                    f"{original['StorageBin']}. New stock level is {new_level}. "
                    f"Both documents stay in the system."),
    }
    audit.record(d["MaterialDocument"], "reversal", utterance, session_id)
    publish("goods_receipt", {**result, "reversal": True, "session_id": session_id})
    return result


# ---------------------------------------------------------------------------
# TOOL 6 — satinalma siparisi durumu
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

# Bir ses oturumu saniye basina faturalanir ve bu uc, anahtari sunucuda
# tutabilmek icin bilerek kimliksiz: tarayici anahtari hic gormesin diye
# token'i biz basiyoruz. Tunel adresi her seferinde degisirken bunu bulan
# olmazdi. Sabit bir adreste bulunur, ve bulan kisi bizim faturamiza oturum
# acar. Bedeli: mesru bir demo da ust sinira carpabilir, o yuzden pencere
# genis tutuldu ve sinir asildiginda 429 ile acikca soyluyoruz.
VOICE_TOKEN_MAX = int(env("VOICE_TOKEN_MAX_PER_HOUR", "40"))


@app.get("/api/voice-token")
async def voice_token() -> dict[str, Any]:
    if not ASSEMBLYAI_API_KEY:
        raise HTTPException(status_code=500, detail="ASSEMBLYAI_API_KEY is not set")
    if await asyncio.to_thread(live.voice_budget_left, VOICE_TOKEN_MAX) <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"This gateway has handed out {VOICE_TOKEN_MAX} voice sessions in the "
                   f"last hour and is holding off. Try again shortly, or raise "
                   f"VOICE_TOKEN_MAX_PER_HOUR.")
    await asyncio.to_thread(live.mint_session, secrets.token_hex(4))
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://agents.assemblyai.com/v1/token",
                             # Kisa omur, calinan ya da kotuye kullanilan bir
                             # token'in ise yaradigi pencereyi daraltir. Bir
                             # demo oturumu bes dakikayi gecmiyor.
                             params={"expires_in_seconds": 120, "max_session_duration_seconds": 300},
                             headers={"Authorization": f"Bearer {ASSEMBLYAI_API_KEY}"})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Token error: {r.text}")
    return {"token": r.json()["token"], "agent_id": AGENT_ID}


@app.get("/api/inventory")
def inventory() -> dict[str, Any]:
    with store.db() as conn:
        rows = conn.execute("SELECT * FROM mard ORDER BY matnr, lgort").fetchall()
        docs = conn.execute("SELECT * FROM mkpf ORDER BY seq DESC LIMIT 10").fetchall()
    return {
        "stock": [{"MATNR": pretty_matnr(r["matnr"]), "MAKTX": r["maktx"], "WERKS": r["werks"],
                   "LGORT": r["lgort"], "LGPLA": r["lgpla"], "LABST": r["labst"],
                   "MEINS": r["meins"]} for r in rows],
        "documents": [{"MBLNR": d["mblnr"], "BWART": d["bwart"], "MATNR": pretty_matnr(d["matnr"]),
                       "MENGE": d["menge"], "MEINS": d["meins"], "LGPLA": d["lgpla"],
                       "BUDAT": d["budat"], "created_at": d["created_at"]} for d in docs],
    }


@app.get("/api/provenance/{mblnr}")
def provenance(mblnr: str) -> dict[str, Any]:
    """
    "Bu belge neden var?" — ekranin sordugu ve cevabini gosterdigi soru.

    Sirsiz, cunku tarayici sirri hicbir zaman gormemeli ve burasi yalniz
    okuyor. Gosterdigi sey mock verisi; gercek bir dagitimda bu ucun onunde
    kimlik dogrulama olurdu, tipki ekranin kendisinde olacagi gibi.
    """
    row = audit.provenance(mblnr.strip())
    if row is None:
        raise HTTPException(status_code=404, detail=f"No material document {mblnr}.")
    return row


@app.post("/api/reset")
def reset(x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret")) -> dict[str, str]:
    # Bayrak yetki degildir. Onceden burasi kimlik sormuyordu ve varsayilan
    # aciklti: adresi bilen herkes demoyu silebiliyordu - canli adreste
    # denendi, 200 dondu. Ustelik ozel baslik tasimayan bir POST oldugu icin
    # tarayici bunu on-kontrolsuz gonderir; bakimciyi kotu bir sayfaya
    # dusurmek yetiyordu. Simdi hem bayrak hem sir gerekiyor.
    if not ENABLE_RESET:
        raise HTTPException(status_code=403, detail="Reset is disabled on this deployment.")
    require_tool_auth(x_tool_secret)
    store.init_db(force=True)
    audit.init()
    live.init()
    publish("reset", {})
    return {"status": "reset"}


@app.get("/health")
def health() -> dict[str, Any]:
    # agent_id burada durmuyor artik: ses oturumu acmak icin gereken ikinci
    # parca oydu ve bu ucu herkes cagirabiliyor. Tarayici zaten onu
    # /api/voice-token cevabindan aliyor.
    return {"ok": True, "agent_configured": bool(AGENT_ID),
            "sap_base_url": sap_target()}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/assets/warehouse-hero.png", include_in_schema=False)
def warehouse_hero() -> FileResponse:
    return FileResponse(WEB_DIR / "assets" / "warehouse-hero.png",
                        headers={"Cache-Control": "public, max-age=86400"})
