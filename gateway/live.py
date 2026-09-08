"""
Canli olay yolu ve ses oturumu sayaci — ikisi de veritabaninda.

Neden bellekte degil: gateway artik istek basina uyanan fonksiyonlar olarak
calisiyor. Tarayicinin SSE baglantisini tutan ornek ile AssemblyAI'in tool
cagrisinin dustugu ornek ayni olmak zorunda degil. Olaylar bellekteki bir
listede dursaydi, belge SAP'ye yazilir ama ekranda hicbir zaman gorunmezdi -
ve bu, calisan bir demoda ARADA BIR olurdu, ki en kotu hata turu budur.

Bedeli: her olay bir INSERT, her ekran yenilemesi bir SELECT. Ekran artik
aninda degil, yarim saniyelik bir gecikmeyle guncelleniyor. Bir ses oturumunun
yaninda bu fark edilmiyor; kaybolan bir belge fark edilirdi.
"""

from __future__ import annotations

import json
import time
from typing import Any

from . import store

# Olaylar demoluk: birkac dakikadan eskisi kimsenin isine yaramaz ve tablo
# suresiz buyumesin. Ses oturumu kayitlari ise saatlik butceyi hesaplamak icin
# bir saat yasamak zorunda.
EVENT_RETENTION_SECONDS = 900
VOICE_WINDOW_SECONDS = 3600

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    type       TEXT NOT NULL,
    payload    TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS scoped_agents (
    scope TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS voice_sessions (
    ref        TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_voice_created ON voice_sessions (created_at);
"""


def init() -> None:
    with store.schema_lock() as conn:
        conn.execute(SCHEMA)


# --- olaylar ---------------------------------------------------------------

def publish(event_type: str, payload: dict[str, Any]) -> None:
    message = json.dumps({"type": event_type, "ts": time.time(), "data": payload})
    with store.db() as conn:
        conn.execute(
            "INSERT INTO events (type, payload, created_at) VALUES (%s,%s,%s)",
            (event_type, message, time.time()),
        )
        conn.execute("DELETE FROM events WHERE created_at < %s",
                     (time.time() - EVENT_RETENTION_SECONDS,))


def latest_id() -> int:
    """Yeni acilan bir ekrana gecmisi tekrar oynatma - sadece bundan sonrasini ver."""
    with store.db() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS id FROM events").fetchone()
    return int(row["id"])


def since(last_id: int) -> list[tuple[int, str]]:
    with store.db() as conn:
        rows = conn.execute(
            "SELECT id, payload FROM events WHERE id > %s ORDER BY id LIMIT 50", (last_id,)
        ).fetchall()
    return [(int(r["id"]), r["payload"]) for r in rows]


# --- ses oturumlari --------------------------------------------------------

def voice_budget_left(ceiling: int) -> int:
    with store.db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM voice_sessions WHERE created_at >= %s",
            (time.time() - VOICE_WINDOW_SECONDS,),
        ).fetchone()
    return ceiling - int(row["c"])


def mint_session(ref: str) -> None:
    with store.db() as conn:
        conn.execute("INSERT INTO voice_sessions (ref, created_at) VALUES (%s,%s)",
                     (ref, time.time()))
        conn.execute("DELETE FROM voice_sessions WHERE created_at < %s",
                     (time.time() - VOICE_WINDOW_SECONDS * 2,))


def current_session() -> str:
    """
    En son basilan oturum referansi. Tool cagrilari AssemblyAI'in sunucusundan
    gelir ve hangi oturumdan dogduklarini soylemez; "su an acik olan oturum"
    demek dogru ama kesin degil - iki kisi ayni anda konusursa ikisi de ayni
    referansi alir. docs/nfr.md'deki tek-oturum tavaninin bir sonucu.
    """
    with store.db() as conn:
        row = conn.execute(
            "SELECT ref FROM voice_sessions ORDER BY created_at DESC LIMIT 1").fetchone()
    return str(row["ref"]) if row else ""


def save_agent(scope: str, agent_id: str, expires_at: float) -> None:
    with store.db() as conn:
        conn.execute("INSERT INTO scoped_agents(scope, agent_id, expires_at) VALUES (%s,%s,%s)",
                     (scope, agent_id, expires_at))


def agents_to_clean(scope: str | None = None) -> list[dict]:
    with store.db() as conn:
        if scope is not None:
            return conn.execute(
                "SELECT scope, agent_id FROM scoped_agents WHERE scope = %s", (scope,)).fetchall()
        return conn.execute(
            "SELECT scope, agent_id FROM scoped_agents WHERE expires_at <= %s ORDER BY expires_at LIMIT 5",
            (time.time(),)).fetchall()


def forget_agent(scope: str) -> None:
    with store.db() as conn:
        conn.execute("DELETE FROM scoped_agents WHERE scope = %s", (scope,))
