"""
GlovesOn Gateway
================
The bridge between the voice agent and SAP.

The agent talks to this service, and this service talks to SAP. The agent
never sees SAP's shape: tool responses are sentences fit to be read aloud,
not OData envelopes. Everything SAP-specific (CSRF, {"d": ...}, 18-digit
MATNR, movement types) lives in sap_client.py.

Moving to a real S/4HANA = setting SAP_BASE_URL. Nothing else.

Run:
    uvicorn gateway.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import time
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import httpx
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from . import (
    audit,
    communications,
    confirmation,
    live,
    mm_knowledge,
    sap_client,
    sap_mock,
    scoped_agent,
    session_scope,
    store,
    voice_diagnostic,
    voice_tools,
)
from .sap_client import SapClient, SapError, env
from .store import norm_matnr, pretty_matnr

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

ASSEMBLYAI_API_KEY = env("ASSEMBLYAI_API_KEY")
TOOL_SHARED_SECRET = env("TOOL_SHARED_SECRET")
AGENT_ID = env("AGENT_ID")

# The port we hand uvicorn locally. The mock is no longer reached through
# this port (see below); it only exists so serve.sh and we agree on a number.
PORT = int(env("PORT", "8000"))

# The "reset" button on the demo screen rebuilds the mock database and asks
# for no identity. The default is now OFF: an open default meant anyone with
# the address could wipe the demo out from under the judges — tried on the
# live address, and it worked. Set GLOVESON_ENABLE_RESET=1 for rehearsals.
ENABLE_RESET = env("GLOVESON_ENABLE_RESET", "0") in ("1", "true", "yes")

# The shared secret used to fall back to the text in .env.example. Locally
# that was harmless; on a public address, a documented default secret is no
# secret at all. If it is missing we stop at startup — better not to run
# than to run unprotected in silence.
if not TOOL_SHARED_SECRET or TOOL_SHARED_SECRET in ("change-me-please", "degistir-beni-lutfen"):
    raise RuntimeError(
        "TOOL_SHARED_SECRET is unset or still the placeholder from .env.example. "
        "Set it to a value of your own (locally in .env, on Vercel in the project's "
        "environment variables) and make sure ./publish.sh runs with the same value."
    )

@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Startup and shutdown. Setting _sap to None on shutdown is not a detail:
    previously only aclose() was called, so the singleton stayed up holding
    a closed HTTP client and the app could not be started a second time in
    the same process. In production, one lifetime per process, it never
    showed; the tests exposed it on their first run.
    """
    global _sap
    # A fresh start clears the shutdown latch. Without this, the first test
    # client's exit set the event forever and every later SSE stream in the
    # same process exited on arrival — the whole checks/ suite only passed
    # when it ran alone.
    _shutting_down.clear()
    store.init_db()
    audit.init()
    confirmation.init()
    communications.init()
    live.init()
    try:
        yield
    finally:
        _shutting_down.set()
        if _sap is not None:
            await _sap.aclose()
            _sap = None


app = FastAPI(title="GlovesOn Gateway", version="0.2.0", lifespan=lifespan)

# The mock S/4HANA is ITS OWN application. Not a layout preference — a
# security fix: while the mock was mounted on the public app, anyone could
# fetch a CSRF token and POST straight to A_MaterialDocumentHeader — no
# shared secret, no spoken confirmation, no duplicate guard, no audit trail.
# The claim "every write is confirmed" could be refuted from the internet
# with a single command.
#
# The gateway still reaches it over HTTP, as if it were an external system;
# all that changed is that requests go to this second app and no route from
# the outside leads there. The only door to SAP is the /erp/* endpoints,
# and they require the secret.
mock_app = FastAPI(title="Mock S/4HANA", version="0.2.0")
mock_app.include_router(sap_mock.router, prefix="/sap/opu/odata/sap", tags=["mock-s4hana"])

_sap: SapClient | None = None

# How the mock S/4HANA is reached. Three possibilities, one code path:
#   SAP_BASE_URL      -> a real tenant, plain HTTP
#   MOCK_SAP_BASE_URL -> the mock in a separate process, plain HTTP
#   neither           -> the mock in the same app, over an ASGI transport
#
# The third is what the serverless platform imposes: no listening port, so
# no loopback — and calling our own public URL would push every ERP call out
# of the data centre and back in: one round of network latency and twice the
# function invocations. ADR-0003's requirement was "call the mock like an
# external system"; the OData path, the CSRF handshake and the error
# envelope are unchanged — the only difference is whether the bytes reach
# a socket.
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
# Live event stream (the demo screen)
# ---------------------------------------------------------------------------

_shutting_down = asyncio.Event()
SSE_MAX_LIFETIME_SECONDS = 50
EVENT_POLL_SECONDS = 0.4


event_scope: ContextVar[str | None] = ContextVar("event_scope", default=None)


@app.middleware("http")
async def bind_event_scope(request: Request, call_next):
    token = request.headers.get("X-Event-Scope", "")
    scope = session_scope.verify(token, TOOL_SHARED_SECRET) if token else None
    if token and scope is None:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Event scope expired or invalid"}, status_code=401)
    reset = event_scope.set(scope)
    try:
        response = await call_next(request)
        if request.url.path.startswith(('/api/voice-token', '/api/voice-session/', '/api/voice-history/')):
            response.headers['Cache-Control'] = 'no-store'
        return response
    finally:
        event_scope.reset(reset)


def publish(event_type: str, payload: dict[str, Any]) -> None:
    live.publish(event_type, {**payload, "event_scope": event_scope.get()})


@app.get("/events")
async def events(request: Request, scope_token: str = Query(...)) -> StreamingResponse:
    scope = session_scope.verify(scope_token, TOOL_SHARED_SECRET)
    if scope is None:
        raise HTTPException(status_code=401, detail="Event scope expired or invalid")
    # The stream reads events from the database: the instance holding the
    # screen and the instance doing the write may not be the same one.
    # See live.py.
    last_id = await asyncio.to_thread(live.latest_id)
    cursor = request.headers.get("last-event-id", "")
    if cursor.isdigit():
        last_id = min(last_id, int(cursor))

    async def stream():
        nonlocal last_id
        deadline = time.monotonic() + SSE_MAX_LIFETIME_SECONDS
        idle = 0.0
        yield "retry: 2000\n\n"
        while not _shutting_down.is_set() and time.monotonic() < deadline:
            if session_scope.verify(scope_token, TOOL_SHARED_SECRET) is None:
                break
            rows = await asyncio.to_thread(live.since, last_id)
            if rows:
                idle = 0.0
                for event_id, payload in rows:
                    last_id = event_id
                    if session_scope.owns_event(scope, json.loads(payload)):
                        yield f"id: {event_id}\ndata: {payload}\n\n"
            else:
                idle += EVENT_POLL_SECONDS
                if idle >= 5:
                    idle = 0.0
                    yield ": keep-alive\n\n"
            await asyncio.sleep(EVENT_POLL_SECONDS)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def require_tool_auth(secret: str | None) -> None:
    # compare_digest measures equality without short-circuiting character by
    # character. It raises TypeError on a non-ASCII header; uncaught, that
    # turns the 401 into a 500 — still closed, but telling the wrong story.
    try:
        ok = bool(secret) and hmac.compare_digest(secret, TOOL_SHARED_SECRET)
    except TypeError:
        ok = False
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid tool secret")


# ---------------------------------------------------------------------------
# TOOL 1 — stock query
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
        # Same as real SAP: stock from one API, the description from another.
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
# TOOL 2 — material search
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


@app.get('/erp/mm-knowledge')
def mm_reference(query: str = Query(..., min_length=2, max_length=500),
                 x_tool_secret: str | None = Header(default=None, alias='X-Tool-Secret')):
    require_tool_auth(x_tool_secret)
    return mm_knowledge.search(query)


@app.get('/knowledge/{article_id}')
def knowledge_article(article_id: str):
    for article in mm_knowledge.ARTICLES:
        if article['id'] == article_id:
            return {k: v for k, v in article.items() if k != 'terms'}
    raise HTTPException(status_code=404, detail='Reference not found')


@app.get('/erp/colleagues')
def find_colleague(query: str = Query(..., min_length=1, max_length=100),
                   x_tool_secret: str | None = Header(default=None, alias='X-Tool-Secret')):
    require_tool_auth(x_tool_secret)
    return communications.find_colleague(query)


@app.get('/erp/communications')
def communication_history(x_tool_secret: str | None = Header(default=None, alias='X-Tool-Secret')):
    require_tool_auth(x_tool_secret)
    return communications.history(event_scope.get())


def communication_route(kind, preparing):
    def endpoint(body: dict = Body(...), x_tool_secret: str | None = Header(default=None, alias='X-Tool-Secret')):
        require_tool_auth(x_tool_secret)
        operation = communications.prepare if preparing else communications.commit
        return operation(event_scope.get(), kind, body)
    return endpoint


@app.post('/erp/follow-up-options')
def follow_up_options(body: dict = Body(...), x_tool_secret: str | None = Header(default=None, alias='X-Tool-Secret')):
    require_tool_auth(x_tool_secret)
    try:
        reason = communications.text_field(body, 'reason', 600)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    # Who it should go to is decided here, from what the worker said and the role
    # they are working as, so the agent reads a name back instead of choosing one.
    recipient, because = communications.follow_up_recipient(
        reason, str(body.get('worker_role') or ''))
    return {'suggested': True, 'simulated': True, 'reason': reason,
            'recipient': recipient, 'because': because,
            'options': ['call_colleague', 'draft_email', 'save_note'],
            'message': f'Options only; no action taken. Suggested colleague: {recipient["name"]}, '
                       f'{recipient["role"]} — {because}. Name them when you offer the choice, and '
                       'use this colleague_id unless the worker names someone else. Each call, email '
                       'or note still needs its own draft, read-back and spoken confirmation.'}


for communication_kind in ('email', 'call', 'note'):
    for preparing in (True, False):
        path = f'/erp/{"prepare" if preparing else "send"}-{communication_kind}'
        app.add_api_route(path, communication_route(communication_kind, preparing), methods=['POST'],
                          name=f'{"prepare" if preparing else "send"}_demo_{communication_kind}')


# ---------------------------------------------------------------------------
# TOOL 3 — goods receipt (WRITE)
# ---------------------------------------------------------------------------

def draft_decision(body, operation, details):
    scope = event_scope.get()
    if body.get("prepare") is True:
        if not scope:
            return {"prepared": False, "message": "Start a private voice session first."}
        token = confirmation.prepare(scope, operation, details)
        publish("write_draft", {**details, "operation": operation, "expires_in": 120})
        return {"prepared": True, "draft_token": token, "details": details,
                "message": "Nothing recorded. Read back quantity, unit, description and bin (and document for reversal). Wait for explicit confirmation. Any correction requires a new draft."}
    error = confirmation.consume(scope, body.get("draft_token"), operation, details,
                                 body.get("user_confirmation") if body.get("confirmed_utterance") else None)
    if error:
        publish("write_rejected", {"message": error})
        return {"posted": False, "reversed": False, "message": error}
    publish("write_posting", {**details, "operation": operation})
    return None


@app.post("/erp/prepare-goods-receipt")
async def prepare_receipt(body: dict = Body(...), x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret")):
    return await post_goods_receipt({**body, "prepare": True}, x_tool_secret)


@app.post("/erp/prepare-reversal")
async def prepare_reversal(body: dict = Body(...), x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret")):
    return await reverse_goods_receipt({**body, "prepare": True}, x_tool_secret)


@app.post("/erp/goods-receipt")
async def post_goods_receipt(
    body: dict = Body(...),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)
    if body.get("prepare") is True:
        confirmation.invalidate(event_scope.get())
        publish("write_draft_cleared", {})


    material, quantity = body.get("material"), body.get("quantity")
    if material is None or quantity is None:
        raise HTTPException(status_code=400, detail="material and quantity are required")
    # "Whole number" means whole number. int(20.5) -> 20 used to be accepted
    # silently: the worker heard "twenty and a half" and confirmed it, and
    # the document said 20 — AFTER confirmation, in the very place exact
    # confirmation is meant to protect. A write that differs from the
    # sentence read back contradicts this project's reason to exist.
    try:
        if isinstance(quantity, bool):
            raise ValueError
        as_float = float(quantity)
        if as_float != int(as_float):
            return {"posted": False,
                    "message": (f"{quantity} is not a whole number of units. Ask the worker "
                                f"for a whole number and read the line back again.")}
        quantity = int(as_float)
    except (TypeError, ValueError, OverflowError):
        return {"posted": False, "message": "Quantity must be a whole number."}
    if quantity <= 0:
        return {"posted": False, "message": "Quantity must be greater than zero."}

    plant = str(body.get("plant") or "1000")
    lgort = str(body.get("storage_location") or "0001")
    allow_duplicate = body.get("allow_duplicate") is True
    matnr = norm_matnr(material)
    # For the audit trail: the sentence read back to the worker, and the
    # session reference.
    # Consent is agent-reported; the gateway binds it to a one-use draft.
    utterance = str(body.get("confirmed_utterance") or "")
    session_id = event_scope.get() or str(body.get("session_id") or "")

    try:
        rows = await sap().get_stock(matnr, plant)
        desc = await sap().get_description(matnr)
    except SapError as e:
        publish("write_rejected", {"message": e.message})
        return {"posted": False, "message": e.message}
    if not rows:
        return {"posted": False,
                "message": f"Material {pretty_matnr(matnr)} is not stocked in plant {plant}."}

    destination = next((r for r in rows if r["StorageLocation"] == lgort), None)
    if destination is None:
        return {"posted": False, "message": "Storage location not found. Look up the destination again."}
    unit = destination["MaterialBaseUnit"]
    bin_ = destination["StorageBin"]
    maktx = desc["ProductDescription"] if desc else ""

    details = {"MATNR": pretty_matnr(matnr), "MENGE": quantity, "MEINS": unit,
               "MAKTX": maktx, "WERKS": plant, "LGORT": lgort, "LGPLA": bin_,
               "purchase_order": body.get("purchase_order") or None,
               "allow_duplicate": allow_duplicate}
    decision = draft_decision(body, "receipt", details)
    if decision is not None:
        return decision

    # --- The same intent must not be recorded twice ------------------------
    # A timed-out write is ambiguous: the document may have landed while the
    # response was lost. The worker repeats the sentence, stock doubles.
    # This check is here deliberately: real SAP does not refuse the second
    # posting, so we do.
    if not allow_duplicate:
        dup = await _recent_identical(matnr, quantity, plant, lgort, body.get("purchase_order"))
        if dup is not None:
            seconds = int(time.time() - float(dup["CreationDateTime"]))
            publish("duplicate_blocked", {"MBLNR": dup["MaterialDocument"], "seconds_ago": seconds})
            return {
                "posted": False, "duplicate": True,
                "MBLNR": dup["MaterialDocument"], "seconds_ago": seconds,
                "message": (
                    f"This exact posting already went through {seconds} seconds ago as "
                    f"material document {dup['MaterialDocument']}: {quantity} {unit} of "
                    f"{maktx} into bin {bin_}. Nothing was posted this time. Ask the worker "
                    f"whether this is a second, separate delivery. If it is, call again with "
                    f"prepare a new draft with allow_duplicate true, read it back and obtain fresh confirmation."),
            }

    payload = sap_client.goods_receipt_payload(
        matnr, quantity, plant, lgort, unit, body.get("purchase_order"),
        session_ref=session_id or None)

    try:
        d = await sap().post_material_document(payload)
    except SapError as e:
        publish("write_rejected", {"message": e.message})
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
    Reads the recent documents from SAP and checks whether the same intent
    was recorded moments ago. The gateway stays stateless: it keeps nothing
    in memory and always asks the system of record for the truth.
    """
    try:
        docs = await sap().list_documents(10)
    except SapError:
        return None   # if we cannot read we do not block the write; the real guard is spoken confirmation
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
# TOOL 4 — recent documents
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
# TOOL 5 — reverse a goods receipt (WRITE)
#
# In SAP a wrong document is never DELETED. A reversal is posted instead:
# a 102 against a 101, a 502 against a 501. Stock comes back down, but both
# documents stay in the history and remain auditable. "Cancelling" is
# therefore a write in the fullest sense, and it sits behind the same
# protections as the goods receipt itself.
# ---------------------------------------------------------------------------

@app.post("/erp/reverse-goods-receipt")
async def reverse_goods_receipt(
    body: dict = Body(...),
    x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret"),
) -> dict[str, Any]:
    require_tool_auth(x_tool_secret)
    if body.get("prepare") is True:
        confirmation.invalidate(event_scope.get())
        publish("write_draft_cleared", {})


    document = str(body.get("document") or "").strip()
    if not document:
        raise HTTPException(status_code=400, detail="document is required")
    utterance = str(body.get("confirmed_utterance") or "")
    session_id = event_scope.get() or str(body.get("session_id") or "")

    try:
        docs = await sap().list_documents(10)
    except SapError as e:
        publish("write_rejected", {"message": e.message})
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
        details = {"MATNR": pretty_matnr(original["Material"]),
                   "MENGE": int(float(original["QuantityInEntryUnit"])),
                   "MEINS": original["EntryUnit"], "MAKTX": desc["ProductDescription"] if desc else "",
                   "WERKS": original["Plant"], "LGORT": original["StorageLocation"],
                   "LGPLA": original["StorageBin"], "document": document,
                   "original_movement": original["GoodsMovementType"]}
        decision = draft_decision(body, "reversal", details)
        if decision is not None:
            return decision
        payload = sap_client.reversal_payload(
            original["Material"], original["Plant"], original["StorageLocation"],
            original["EntryUnit"], document, original["GoodsMovementType"],
            quantity=int(float(original["QuantityInEntryUnit"])),
            session_ref=session_id or None)
        d = await sap().post_material_document(payload)
    except SapError as e:
        publish("write_rejected", {"message": e.message})
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
# TOOL 6 — purchase order status
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
# Support endpoints for the demo screen
# ---------------------------------------------------------------------------

# A voice session is billed per second, and this endpoint is deliberately
# unauthenticated so the API key can stay on the server: we mint the token
# so the browser never sees the key. While the tunnel address changed on
# every start, nobody would find it. On a fixed address it will be found,
# and whoever finds it opens sessions on our bill. The cost: a legitimate
# demo can hit the ceiling too, so the window is kept generous and crossing
# it answers with an explicit 429.
VOICE_TOKEN_MAX = int(env("VOICE_TOKEN_MAX_PER_HOUR", "40"))


async def clean_scoped_agents(client: httpx.AsyncClient, scope: str | None = None) -> bool:
    """Bound provider cleanup; retain failed rows for a later expiry sweep."""
    async def remove(row):
        if row['agent_id'] == voice_tools.INLINE_AGENT:
            await asyncio.to_thread(live.forget_agent, row['scope'])
            return True
        try:
            response = await client.delete(
                f"https://agents.assemblyai.com/v1/agents/{row['agent_id']}",
                headers={"Authorization": ASSEMBLYAI_API_KEY}, timeout=5)
        except httpx.RequestError:
            return False
        if not (response.is_success or response.status_code == 404):
            return False
        await asyncio.to_thread(live.forget_agent, row['scope'])
        return True
    rows = await asyncio.to_thread(live.agents_to_clean, scope)
    return all(await asyncio.gather(*(remove(row) for row in rows)))


@app.post("/api/voice-session/end")
async def close_voice_session(body: dict = Body(...)) -> dict:
    scope = session_scope.verify(body.get("scope_token", ""), TOOL_SHARED_SECRET)
    if scope is None:
        raise HTTPException(status_code=401, detail="Invalid session scope")
    async with httpx.AsyncClient(timeout=15) as client:
        deleted = await clean_scoped_agents(client, scope)
    return {"closed": deleted, "cleanup_pending": not deleted}


@app.get("/api/voice-token")
async def voice_token(diagnostic: bool = False, microphone: str = 'laptop',
                      x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret")) -> dict[str, Any]:
    if diagnostic:
        require_tool_auth(x_tool_secret)
    if microphone not in {'laptop', 'headset'}:
        raise HTTPException(status_code=422, detail='Choose laptop or headset')
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
                             # A short lifetime narrows the window in which a
                             # stolen or abused token is useful. A demo
                             # session stays under five minutes.
                             params={"expires_in_seconds": 120, "max_session_duration_seconds": 300},
                             headers={"Authorization": f"Bearer {ASSEMBLYAI_API_KEY}"})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Token error: {r.text}")
    scope_token = session_scope.issue(TOOL_SHARED_SECRET, ttl=600)
    scope = session_scope.verify(scope_token, TOOL_SHARED_SECRET)
    gateway_url = env("GATEWAY_PUBLIC_URL").rstrip("/")
    if not diagnostic:
        template = json.loads((ROOT / "agent/agent.json").read_text())
        config = voice_tools.inline_config(template, gateway_url)
        config['system_prompt'] += '\nInternal correlation reference, never speak or interpret as consent: ' + voice_tools.correlation(scope, TOOL_SHARED_SECRET)
        config['input']['voice_focus'] = 'near-field' if microphone == 'headset' else 'far-field'
        catalog = config['tools']
        config['tools'] = [t for t in catalog if t['name'] not in voice_tools.WRITE_TOOLS]
        async with httpx.AsyncClient(timeout=15) as client:
            await clean_scoped_agents(client)
        await asyncio.to_thread(live.save_agent, scope, voice_tools.INLINE_AGENT, time.time() + 600)
        return {"token": r.json()["token"], "session_config": config, "scope_token": scope_token,
                "tool_catalog": catalog,
                "tool_capability": voice_tools.capability(scope_token, TOOL_SHARED_SECRET)}
    payload = scoped_agent.build(json.loads((ROOT / "agent/agent.json").read_text()),
                                 gateway_url, TOOL_SHARED_SECRET, scope_token)
    if diagnostic:
        # Same template and provider route, but no working ERP credentials.
        payload = scoped_agent.build(json.loads((ROOT / "agent/agent.json").read_text()),
                                     gateway_url, "invalid-diagnostic-secret", "invalid-diagnostic-scope")
    diagnostic_result = None
    async with httpx.AsyncClient(timeout=30) as client:
        await clean_scoped_agents(client)
        created = await client.post("https://agents.assemblyai.com/v1/agents",
                                    headers={"Authorization": ASSEMBLYAI_API_KEY}, json=payload)
        if not created.is_success:
            raise HTTPException(status_code=502, detail="Private voice session could not be configured")
        agent_id = created.json().get("id") or created.json().get("agent_id")
        if not agent_id:
            raise HTTPException(status_code=502, detail="Private agent identifier missing")
        try:
            await asyncio.to_thread(live.save_agent, scope, agent_id, time.time() + 600)
        except Exception:
            await client.delete(f"https://agents.assemblyai.com/v1/agents/{agent_id}",
                                headers={"Authorization": ASSEMBLYAI_API_KEY})
            raise
        if diagnostic:
            diagnostic_result = {
                "payload_sha256": voice_diagnostic.payload_digest(payload),
                "created": voice_diagnostic.response_summary(created, payload),
            }
            try:
                lookup = await client.get(f"https://agents.assemblyai.com/v1/agents/{agent_id}",
                                          headers={"Authorization": ASSEMBLYAI_API_KEY})
                diagnostic_result["server_lookup"] = voice_diagnostic.response_summary(lookup, payload)
            except httpx.RequestError:
                # The tracked agent can still be closed normally after a failed probe.
                diagnostic_result["server_lookup"] = {"transport_error": True}
    result = {"token": r.json()["token"], "agent_id": agent_id, "scope_token": scope_token}
    if diagnostic_result is not None:
        result["diagnostic"] = diagnostic_result
    return result


async def active_voice_scope(request: Request) -> str:
    token = request.headers.get('X-Event-Scope', '')
    if not voice_tools.authorized(token, request.headers.get('X-Voice-Capability', ''), TOOL_SHARED_SECRET):
        raise HTTPException(status_code=401, detail='Invalid voice capability')
    scope = session_scope.verify(token, TOOL_SHARED_SECRET)
    if not await asyncio.to_thread(live.inline_session_active, scope):
        raise HTTPException(status_code=401, detail='Voice session ended or expired')
    return scope


@app.post('/api/voice-session/bind')
async def bind_voice_session(request: Request, body: dict = Body(...)):
    scope = await active_voice_scope(request)
    session_id = body.get('session_id', '')
    if not isinstance(session_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', session_id):
        raise HTTPException(status_code=422, detail='Invalid provider session identifier')
    if not await provider_belongs_to_scope(scope, session_id):
        raise HTTPException(status_code=403, detail='Provider session ownership could not be verified')
    if not await asyncio.to_thread(live.bind_provider_session, scope, session_id):
        raise HTTPException(status_code=409, detail='Session already bound')
    return {'bound': True}


async def provider_belongs_to_scope(scope: str, session_id: str) -> bool:
    # A browser's session ID alone is not authority to resume another worker's conversation.
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(f'https://agents.assemblyai.com/v1/sessions/{session_id}',
                                       headers={'Authorization': ASSEMBLYAI_API_KEY})
    except httpx.RequestError:
        return False
    if not response.is_success:
        return False
    prompt = response.json().get('config', {}).get('system_prompt', '')
    return isinstance(prompt, str) and voice_tools.correlation(scope, TOOL_SHARED_SECRET) in prompt


@app.post('/api/voice-session/alex-token')
async def alex_voice_token(request: Request):
    scope = await active_voice_scope(request)
    history = await asyncio.to_thread(communications.history, scope)
    if not any(r.get('status') == 'simulated_call_logged'
               and r.get('details', {}).get('recipient', {}).get('id') == 'alex'
               for r in history['records']):
        raise HTTPException(status_code=409, detail='Confirm an Alex demo call first')
    if await asyncio.to_thread(live.voice_budget_left, VOICE_TOKEN_MAX) <= 0:
        raise HTTPException(status_code=429, detail='Voice session budget exhausted')
    await asyncio.to_thread(live.mint_session, secrets.token_hex(4))
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get('https://agents.assemblyai.com/v1/token',
            params={'expires_in_seconds': 60, 'max_session_duration_seconds': 180},
            headers={'Authorization': f'Bearer {ASSEMBLYAI_API_KEY}'})
    if not response.is_success:
        raise HTTPException(status_code=502, detail='Alex voice unavailable')
    return {'token': response.json()['token'], 'voice': 'james'}


@app.post('/api/voice-session/resume-token')
async def resume_voice_token(request: Request):
    scope = await active_voice_scope(request)
    session_id = await asyncio.to_thread(live.resume_provider_session, scope)
    if not session_id:
        raise HTTPException(status_code=409, detail='Recovery limit reached or session expired')
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get('https://agents.assemblyai.com/v1/token',
            params={'expires_in_seconds': 60, 'max_session_duration_seconds': 300},
            headers={'Authorization': f'Bearer {ASSEMBLYAI_API_KEY}'})
    if not response.is_success:
        raise HTTPException(status_code=502, detail='Recovery token unavailable')
    return {'token': response.json()['token'], 'session_id': session_id}


@app.get('/api/voice-history/{session_id}')
async def voice_history(session_id: str,
                        x_tool_secret: str | None = Header(default=None, alias='X-Tool-Secret')):
    # Provider history is account-wide. A client-reported correlation ID never grants access.
    require_tool_auth(x_tool_secret)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', session_id):
        raise HTTPException(status_code=422, detail='Invalid session identifier')
    async with httpx.AsyncClient(timeout=15) as client:
        result = await client.get(f'https://agents.assemblyai.com/v1/sessions/{session_id}',
                                  headers={'Authorization': ASSEMBLYAI_API_KEY})
    if not result.is_success:
        raise HTTPException(status_code=502, detail=f'Provider history unavailable ({result.status_code})')
    data = result.json()
    # Exclude resolved config, which can contain tool headers or custom-model credentials.
    return Response(json.dumps({k: data.get(k) for k in (
        'id', 'status', 'duration_seconds', 'created_at', 'ended_at', 'artifacts')}),
        media_type='application/json', headers={'Cache-Control': 'no-store'})


@app.post('/api/voice-tools/{tool_name}')
async def execute_voice_tool(tool_name: str, request: Request) -> Response:
    scope_token = request.headers.get('X-Event-Scope', '')
    access = request.headers.get('X-Voice-Capability', '')
    if not voice_tools.authorized(scope_token, access, TOOL_SHARED_SECRET):
        raise HTTPException(status_code=401, detail='Invalid voice capability')
    scope = session_scope.verify(scope_token, TOOL_SHARED_SECRET)
    if not await asyncio.to_thread(live.inline_session_active, scope):
        raise HTTPException(status_code=401, detail='Voice session ended or expired')
    allowed = voice_tools.routes(json.loads((ROOT / 'agent/agent.json').read_text()))
    if tool_name not in allowed:
        raise HTTPException(status_code=404, detail='Unknown voice tool')
    method, path = allowed[tool_name]
    try:
        arguments = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail='Tool arguments must be JSON') from None
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=422, detail='Tool arguments must be an object')
    arguments = voice_tools.normalize_arguments(arguments)
    # Reuse the exact ERP routes, schema validation, draft protocol and audit path.
    # The permanent tool secret never leaves this process or reaches the browser.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://internal') as client:
        result = await client.request(method, path,
                                      params=arguments if method == 'GET' else None,
                                      json=arguments if method == 'POST' else None,
                                      headers={'X-Tool-Secret': TOOL_SHARED_SECRET,
                                               'X-Event-Scope': scope_token,
                                               'Content-Type': 'application/json'})
    return Response(result.content, status_code=result.status_code,
                    media_type='application/json', headers={'Cache-Control': 'no-store'})


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


@app.get("/api/facts")
def facts() -> dict[str, Any]:
    """
    Every number the how-it-works page prints, derived at request time from the
    files and tables that hold the truth.

    A diagram that carries hand-typed counts drifts from the thing it claims to
    describe, and the drift is invisible until a reader checks — which is the
    one thing a page like that exists to invite. Anything that cannot be
    derived here is omitted rather than guessed: a missing number is honest,
    a stale one is not.
    """
    out: dict[str, Any] = {}

    # Each section is suppressed on its own: a deployment that does not bundle
    # the test tree should still report its tools, and a database blip should
    # not blank the page. A missing section is visible as a missing number.
    with suppress(Exception):
        spec = json.loads((ROOT / "agent/agent.json").read_text())
        tools = spec.get("tools", [])
        out["tools"] = {
            "count": len(tools),
            "writes": [t["name"] for t in tools if t["name"] in
                       ("post_goods_receipt", "reverse_goods_receipt")],
            "hold": [t["name"] for t in tools if t.get("execution_mode") == "hold"],
        }
        listen = spec.get("input", {})
        out["recognition"] = {
            "keyterms": len(listen.get("keyterms", [])),
            "voice_focus": listen.get("voice_focus"),
            "turn_detection": listen.get("turn_detection", {}),
        }

    with suppress(Exception):
        out["evidence"] = {
            "adrs": len(sorted((ROOT / "docs/adr").glob("0*.md"))),
            "tests": sum(p.read_text().count("def test_")
                         for d in ("tests", "checks")
                         for p in (ROOT / d).glob("*.py")),
        }

    out["erp"] = {"target": sap_target()}
    with suppress(Exception), store.db() as conn:
        out["erp"]["materials"] = conn.execute(
            "SELECT COUNT(*) AS c FROM mard").fetchone()["c"]
        out["erp"]["documents"] = conn.execute(
            "SELECT COUNT(*) AS c FROM mkpf").fetchone()["c"]

    return out


@app.get("/how-it-works", include_in_schema=False)
def how_it_works() -> FileResponse:
    return FileResponse(WEB_DIR / "how-it-works.html")


@app.get("/api/directory")
def demo_directory() -> dict[str, Any]:
    """
    Who the worker can reach, for the screen to show before anybody speaks.

    Invented people at a reserved example domain, and the only names the demo
    accepts; no secret, because there is nothing here to protect and a worker
    guessing at names is the failure this answers.
    """
    return {"simulated": True, "colleagues": communications.directory()}


@app.get("/api/provenance/{mblnr}")
def provenance(mblnr: str) -> dict[str, Any]:
    """
    "Why does this document exist?" — the question the screen asks and
    answers.

    No secret required, because the browser must never see the secret and
    this endpoint only reads. What it shows is mock data; in a real
    deployment authentication would sit in front of it, exactly as it
    would in front of the screen itself.
    """
    row = audit.provenance(mblnr.strip())
    if row is None:
        raise HTTPException(status_code=404, detail=f"No material document {mblnr}.")
    return row


@app.post("/api/reset")
def reset(x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret")) -> dict[str, str]:
    # A flag is not authorization. This endpoint used to ask for no identity
    # and the default was open: anyone with the address could wipe the demo —
    # tried on the live address, it returned 200. Worse, a POST carrying no
    # custom header goes out without a preflight, so luring a maintainer onto
    # a hostile page was enough. Now both the flag and the secret are required.
    if not ENABLE_RESET:
        raise HTTPException(status_code=403, detail="Reset is disabled on this deployment.")
    require_tool_auth(x_tool_secret)
    store.init_db(force=True)
    audit.init()
    confirmation.init()
    live.init()
    publish("reset", {})
    return {"status": "reset"}


@app.get("/health")
def health(x_tool_secret: str | None = Header(default=None, alias="X-Tool-Secret")
           ) -> dict[str, Any]:
    # agent_id no longer lives here: it was the second piece needed to open
    # a voice session, and anyone can call this endpoint. The browser gets
    # it from the /api/voice-token response instead.
    #
    # What IS here is which pieces are configured. A voice session needs four
    # things to line up across two systems, and when one of them is wrong the
    # symptom is a silent agent — which reads like a network fault and is not.
    # Answering "which of them is actually set" without a microphone is the
    # difference between finding that in a minute and finding it in an evening.
    out: dict[str, Any] = {
        "ok": True,
        "agent_configured": bool(AGENT_ID),
        "sap_base_url": sap_target(),
        "configured": {
            "assemblyai_key": bool(ASSEMBLYAI_API_KEY),
            "tool_secret": bool(TOOL_SHARED_SECRET),
            "gateway_public_url": bool(env("GATEWAY_PUBLIC_URL")),
            "agent_id": bool(AGENT_ID),
            "database": False,
        },
    }
    with suppress(Exception), store.db() as conn:
        conn.execute("SELECT 1")
        out["configured"]["database"] = True

    # Fingerprints only for a caller who already holds the secret. Twelve hex
    # characters of a SHA-256 cannot be walked back to a key, but they answer
    # the one question a deployment cannot otherwise answer: is the key up
    # there the same key as the one down here? Comparing two values you are
    # not allowed to read is the whole problem.
    with suppress(HTTPException):
        require_tool_auth(x_tool_secret)
        fp = lambda s: hashlib.sha256(s.encode()).hexdigest()[:12] if s else None  # noqa: E731
        out["fingerprints"] = {
            "assemblyai_key": fp(ASSEMBLYAI_API_KEY),
            "tool_secret": fp(TOOL_SHARED_SECRET),
            "gateway_public_url": env("GATEWAY_PUBLIC_URL"),
            "agent_id": AGENT_ID or None,
        }
    return out


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get('/agent-desktop.js', include_in_schema=False)
def agent_desktop_script():
    return FileResponse(WEB_DIR / 'agent-desktop.js', media_type='text/javascript', headers={'Cache-Control': 'no-cache'})


@app.get('/agent-desktop.css', include_in_schema=False)
def agent_desktop_styles():
    return FileResponse(WEB_DIR / 'agent-desktop.css', media_type='text/css', headers={'Cache-Control': 'no-cache'})


@app.get('/work-screen.css', include_in_schema=False)
def work_screen_styles():
    return FileResponse(WEB_DIR / 'work-screen.css', media_type='text/css', headers={'Cache-Control': 'no-cache'})


@app.get('/voice-policy.js', include_in_schema=False)
def voice_policy_script() -> FileResponse:
    return FileResponse(WEB_DIR / 'voice-policy.js', media_type='text/javascript',
                        headers={'Cache-Control': 'no-cache'})


@app.get('/how-stories.js', include_in_schema=False)
def how_stories_script() -> FileResponse:
    return FileResponse(WEB_DIR / 'how-stories.js', media_type='text/javascript',
                        headers={'Cache-Control': 'no-cache'})


@app.get("/assets/{scene}.webp", include_in_schema=False)
def scene_webp(scene: str) -> FileResponse:
    if scene not in {"worker-3d"}:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(WEB_DIR / "assets" / f"{scene}.webp",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/assets/warehouse-composite.svg", include_in_schema=False)
def warehouse_composite() -> FileResponse:
    return FileResponse(WEB_DIR / "assets" / "warehouse-composite.svg", media_type="image/svg+xml")


# The social card the og:image tag points at. Assets are served by allowlist
# rather than a static mount, so a file nobody routes is a file nobody sees --
# and a share card that 404s fails silently in the one place it matters.
@app.get("/assets/og-card.jpg", include_in_schema=False)
def og_card() -> FileResponse:
    return FileResponse(WEB_DIR / "assets" / "og-card.jpg", media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/assets/{scene}.png", include_in_schema=False)
def scenario_image(scene: str) -> FileResponse:
    if scene not in {"warehouse-3d", "warehouse-interior", "hero-scene", "workspace-parcel-studio", "hex-bolts-studio"}:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(WEB_DIR / "assets" / f"{scene}.png",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/assets/avatar/{filename:path}", include_in_schema=False)
def avatar_asset(filename: str) -> FileResponse:
    allowed = {"worker.glb", "worker-fingers.glb", "delivery-scene.js", "work-scenes.js", "motions.json", "character.js", "warehouse-detail.jpg", "receiving-intro.mp4", "review-intro.mp4", "storage-intro.mp4",
               "vendor/three.module.js", "vendor/three.core.js", "vendor/GLTFLoader.js",
               "vendor/BufferGeometryUtils.js", "vendor/LICENSE"}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(WEB_DIR / "assets" / "avatar" / filename,
                        headers={"Cache-Control": "public, max-age=3600"})
