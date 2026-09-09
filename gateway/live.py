"""
The live event path and the voice-session counter — both in the database.

Why not in memory: the gateway now runs as functions that wake per request.
The instance holding the browser's SSE connection and the instance where
AssemblyAI's tool call lands need not be the same one. Had events sat in an
in-memory list, the document would be written to SAP and never appear on
the screen — and in a working demo that would happen ONLY OCCASIONALLY,
which is the worst kind of failure.

The cost: every event is an INSERT, every screen refresh a SELECT. The
screen now updates with half a second of lag instead of instantly. Next to
a voice session nobody notices that; a lost document would be noticed.
"""

from __future__ import annotations

import json
import time
from typing import Any

from . import store

# Events are demo material: nothing older than a few minutes is of use to
# anyone, and the table must not grow forever. Voice-session rows, though,
# have to live an hour so the hourly budget can be computed.
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
CREATE TABLE IF NOT EXISTS voice_links (
    scope TEXT PRIMARY KEY,
    provider_session TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    resume_count INTEGER NOT NULL DEFAULT 0
);
"""


def init() -> None:
    with store.schema_lock() as conn:
        conn.execute(SCHEMA)


# --- events ----------------------------------------------------------------

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
    """Do not replay history to a freshly opened screen — only what comes next."""
    with store.db() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS id FROM events").fetchone()
    return int(row["id"])


def since(last_id: int) -> list[tuple[int, str]]:
    with store.db() as conn:
        rows = conn.execute(
            "SELECT id, payload FROM events WHERE id > %s ORDER BY id LIMIT 50", (last_id,)
        ).fetchall()
    return [(int(r["id"]), r["payload"]) for r in rows]


# --- voice sessions --------------------------------------------------------

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
    The most recently minted session reference. Tool calls arrive from
    AssemblyAI's servers and do not say which session they were born in;
    "the currently open session" is correct but not precise — if two people
    speak at once, both get the same reference. A consequence of the
    single-session ceiling in docs/nfr.md.
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


def inline_session_active(scope: str) -> bool:
    from .voice_tools import INLINE_AGENT
    with store.db() as conn:
        row = conn.execute(
            "SELECT 1 FROM scoped_agents WHERE scope = %s AND agent_id = %s AND expires_at > %s",
            (scope, INLINE_AGENT, time.time())).fetchone()
    return row is not None


def bind_provider_session(scope: str, provider_session: str) -> bool:
    """Client-reported correlation; not proof of provider ownership or spoken identity."""
    with store.db() as conn:
        row = conn.execute('''INSERT INTO voice_links(scope, provider_session, created_at)
            VALUES (%s,%s,%s) ON CONFLICT(scope) DO UPDATE SET scope=EXCLUDED.scope
            WHERE voice_links.provider_session=EXCLUDED.provider_session RETURNING scope''',
            (scope, provider_session, time.time())).fetchone()
        conn.execute('DELETE FROM voice_links WHERE created_at < %s', (time.time()-86400,))
    return bool(row)


def resume_provider_session(scope: str) -> str | None:
    with store.db() as conn:
        row = conn.execute('''UPDATE voice_links SET resume_count=resume_count+1
            WHERE scope=%s AND resume_count<5 AND created_at>%s
            RETURNING provider_session''', (scope, time.time()-300)).fetchone()
    return row['provider_session'] if row else None
