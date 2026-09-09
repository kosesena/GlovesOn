"""
The audit trail: which sentence gave birth to which document.

The SAP document holds "what happened"; this file holds "why" — so that from
a document number one can walk back to the sentence read to the worker, and
to the second it was confirmed. The gap docs/clean-core.md opens is NOT
closed here: without principal propagation SAP still does not know who was
speaking. This trail does not replace that; while waiting for it, it records
the one true thing we do have: the spoken sentence itself.

Deliberately not in store.py. store.py is the mock S/4HANA's database and
dies entirely on the day a real tenant takes over; the audit trail is more
necessary on exactly that day. They share the same database — a second one
would have meant two backups and two paths — but the table stands on its
own, ready to move out when the mock is deleted.
"""

from __future__ import annotations

import time
from typing import Any

from . import store

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_trail (
    mblnr      TEXT NOT NULL,          -- SAP document number
    action     TEXT NOT NULL,          -- goods_receipt | reversal
    utterance  TEXT NOT NULL,          -- the sentence read to and confirmed by the worker
    session_id TEXT NOT NULL,          -- voice session reference
    created_at DOUBLE PRECISION NOT NULL -- UTC epoch, gateway clock
);
CREATE INDEX IF NOT EXISTS idx_audit_mblnr ON audit_trail (mblnr);
"""


def init() -> None:
    with store.schema_lock() as conn:
        conn.execute(SCHEMA)
        # REAL (float4) rounds epoch seconds into 128-second buckets:
        # 1788723673.14 -> 1788723712.0, a 39-second drift. The audit trail's
        # clock is itself the evidence, so this is a silent falsehood.
        # CREATE TABLE IF NOT EXISTS does not fix an existing table; the
        # column has to be converted separately.
        conn.execute("ALTER TABLE audit_trail ALTER COLUMN created_at TYPE DOUBLE PRECISION")


def record(mblnr: str, action: str, utterance: str, session_id: str) -> None:
    with store.db() as conn:
        conn.execute(
            "INSERT INTO audit_trail (mblnr, action, utterance, session_id, created_at)"
            " VALUES (%s,%s,%s,%s,%s)",
            (mblnr, action, utterance.strip()[:500], session_id.strip()[:64], time.time()),
        )


def provenance(mblnr: str) -> dict[str, Any] | None:
    """
    A document's origin: the header fields SAP keeps and the trail we keep,
    in one answer. They live in separate systems and say separate things —
    one says "this document was opened by voice", the other "this is the
    sentence that was spoken".

    Why this endpoint exists: an audit trail that is written but never read
    from anywhere is an audit trail that does not exist. Evidence is only
    evidence if it can be shown.
    """
    with store.db() as conn:
        doc = conn.execute(
            "SELECT mblnr, bwart, matnr, menge, meins, lgpla, budat, created_at,"
            " bktxt, xblnr, reversed_of FROM mkpf WHERE mblnr=%s", (mblnr,)).fetchone()
        if doc is None:
            return None
        trail = conn.execute(
            "SELECT action, utterance, session_id, created_at FROM audit_trail"
            " WHERE mblnr=%s ORDER BY created_at DESC LIMIT 1", (mblnr,)).fetchone()

    return {
        "MBLNR": doc["mblnr"], "BWART": doc["bwart"],
        "MATNR": store.pretty_matnr(doc["matnr"]), "MENGE": doc["menge"],
        "MEINS": doc["meins"], "LGPLA": doc["lgpla"], "BUDAT": doc["budat"],
        "posted_at": doc["created_at"],
        "BKTXT": doc["bktxt"], "XBLNR": doc["xblnr"],
        "reverses": doc["reversed_of"],
        # A missing trail is not a defect, it is information: the document
        # may have been opened by a direct tool call rather than by voice.
        # Saying so beats showing an empty field in silence.
        "voice": {
            "action": trail["action"],
            "utterance": trail["utterance"],
            "session_id": trail["session_id"],
            "recorded_at": trail["created_at"],
        } if trail else None,
    }


def lookup(mblnr: str) -> dict[str, Any] | None:
    with store.db() as conn:
        r = conn.execute(
            "SELECT * FROM audit_trail WHERE mblnr=%s ORDER BY created_at DESC LIMIT 1",
            (mblnr,),
        ).fetchone()
    return dict(r) if r else None
