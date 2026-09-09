"""
The Postgres store — the data behind the mock S/4HANA.

This file holds SAP's *data*, not its contract. The OData surface lives in
sap_mock.py. On the day a real S/4HANA takes over, this file dies entirely.

Why not SQLite: the gateway now runs as functions that wake per request
(see docs/adr/0005). There is no persistent disk there, and two requests
may not land in the same process — so a file sitting next to the code meant
a database written in one sentence and lost in the next. The cost: no more
offline work; even the simplest test needs a Postgres connection.
"""

from __future__ import annotations

import time
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .sap_client import env


def database_url() -> str:
    """
    Read at call time, not at import time: in a serverless environment the
    variables arrive independently of the process's lifetime, and locally we
    do not want to depend on when .env happened to be loaded.
    """
    return env("DATABASE_URL") or env("POSTGRES_URL")

# If the same material + quantity + storage location arrives again within
# this window, no new document is opened. A worker repeating the sentence
# after a timed-out write falls inside this window.
DUPLICATE_WINDOW_SECONDS = 120

SEED_MATERIALS = [
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
    ("4500001234", "Bosch Rexroth AG", "4713", 50, "Partially Delivered", "2026-09-11"),
    ("4500001235", "SKF Turkiye", "5100", 200, "Open", "2026-09-18"),
    ("4500001236", "Fuchs Lubricants", "6201", 40, "Delivered", "2026-09-02"),
]

# mkpf.seq: SQLite had rowid, Postgres does not. Document order is visible
# in the demo — the "recent documents" list sorts by it — so we count
# explicitly rather than leave the order to chance.
SCHEMA = """
CREATE TABLE IF NOT EXISTS mard (
    matnr TEXT NOT NULL, maktx TEXT NOT NULL, meins TEXT NOT NULL,
    werks TEXT NOT NULL, lgort TEXT NOT NULL, lgpla TEXT NOT NULL,
    labst INTEGER NOT NULL,
    PRIMARY KEY (matnr, werks, lgort)
);
CREATE TABLE IF NOT EXISTS mkpf (
    seq BIGSERIAL,
    mblnr TEXT PRIMARY KEY, mjahr TEXT NOT NULL, bwart TEXT NOT NULL,
    matnr TEXT NOT NULL, menge INTEGER NOT NULL, meins TEXT NOT NULL,
    werks TEXT NOT NULL, lgort TEXT NOT NULL, lgpla TEXT NOT NULL,
    budat TEXT NOT NULL, ebeln TEXT, reversed_of TEXT,
    created_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    bktxt TEXT NOT NULL DEFAULT '',
    xblnr TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ekko (
    ebeln TEXT PRIMARY KEY, lifnr TEXT NOT NULL, matnr TEXT NOT NULL,
    menge INTEGER NOT NULL, status TEXT NOT NULL, eta TEXT NOT NULL
);
"""

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    """
    The pool is deliberately small and lazy. A function instance sees a few
    requests, not a hundred; every connection held open is a slot on the
    Postgres side, and in a serverless environment the number of instances
    is not under our control. Using Neon's pooled endpoint is a must.
    """
    global _pool
    if _pool is None:
        url = database_url()
        if not url:
            raise RuntimeError(
                "DATABASE_URL is not set. The mock S/4HANA keeps its data in Postgres "
                "(see docs/adr/0005); point DATABASE_URL at your database — locally in "
                ".env, on Vercel through the storage integration."
            )
        # A frozen serverless instance freezes the pool's maintenance thread
        # with it; Neon closes the idle connection meanwhile, and the thawed
        # instance discovers the dead socket only mid-query ("SSL connection
        # has been closed unexpectedly", /api/voice-token, 9 Sep). check pings
        # every connection at checkout and replaces a dead one silently — one
        # extra round trip per checkout, paid so a warm demo cannot 500.
        _pool = ConnectionPool(url, min_size=0, max_size=4, kwargs={"row_factory": dict_row},
                               open=True, timeout=10, check=ConnectionPool.check_connection)
    return _pool


@contextmanager
def db():
    """
    Hands out a connection; commits when the block ends cleanly, rolls back
    on error. `conn.commit()` calls on the caller's side are harmless,
    merely redundant.
    """
    with pool().connection() as conn:
        yield conn


# A single lock for schema setup. "CREATE TABLE IF NOT EXISTS" is NOT
# idempotent under concurrency in Postgres: when two sessions try at once,
# one blows up with a uniqueness violation on pg_type. In a serverless
# deployment two instances cold-starting together do this regularly — the
# tests showed it on their first run; in production it would have shown up
# as an occasional 500.
SCHEMA_LOCK_KEY = 0x67_10_5E


@contextmanager
def schema_lock():
    """Every path that changes the schema goes through this. The lock is released at commit."""
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK_KEY,))
        yield conn


def norm_matnr(raw: str | int) -> str:
    """SAP MATNR is 18 characters, zero-padded on the left. By voice one says '4711'."""
    s = str(raw).strip().upper().replace(" ", "").replace("-", "")
    return s.zfill(18) if s.isdigit() else s


def pretty_matnr(matnr: str) -> str:
    return matnr.lstrip("0") or "0"


# A schema change does not reach an existing database: CREATE TABLE IF NOT
# EXISTS leaves the existing table alone. We add the missing columns one by
# one, so an old database runs with new code. When you add a column, grow
# this list too — do not assume the change in SCHEMA alone will be enough.
MIGRATIONS = {
    "mkpf": [
        ("seq", "BIGSERIAL"),
        ("mjahr", "TEXT NOT NULL DEFAULT ''"),
        ("reversed_of", "TEXT"),
        ("created_at", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("bktxt", "TEXT NOT NULL DEFAULT ''"),
        ("xblnr", "TEXT NOT NULL DEFAULT ''"),
    ],
}


def _ensure_columns(conn) -> list[str]:
    added = []
    for table, columns in MIGRATIONS.items():
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema='public' AND table_name=%s", (table,)).fetchall()
        existing = {r["column_name"] for r in rows}
        if not existing:
            continue                      # table does not exist yet; SCHEMA will create it
        for name, decl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                added.append(f"{table}.{name}")
    return added


def init_db(force: bool = False) -> None:
    """
    force=True is the demo reset: drop the tables and write the seed data
    back. DROP instead of deleting a file — there is no file to delete
    any more.
    """
    with schema_lock() as conn:
        if force:
            conn.execute("DROP TABLE IF EXISTS mard, mkpf, ekko, audit_trail, events")
        conn.execute(SCHEMA)
        added = _ensure_columns(conn)
        if added:
            print(f"  [store] added missing columns: {', '.join(added)}")
        if not conn.execute("SELECT COUNT(*) AS c FROM mard").fetchone()["c"]:
            conn.cursor().executemany(
                "INSERT INTO mard (matnr, maktx, meins, werks, lgort, lgpla, labst)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                [(norm_matnr(m), desc, unit, plant, sloc, bin_, qty)
                 for m, desc, unit, plant, sloc, bin_, qty in SEED_MATERIALS],
            )
            conn.cursor().executemany(
                "INSERT INTO ekko (ebeln, lifnr, matnr, menge, status, eta)"
                " VALUES (%s,%s,%s,%s,%s,%s)",
                [(po, supplier, norm_matnr(m), qty, status, eta)
                 for po, supplier, m, qty, status, eta in SEED_ORDERS],
            )


def recent_duplicate(conn, matnr: str, menge: int, werks: str, lgort: str, ebeln: str | None):
    return conn.execute(
        "SELECT * FROM mkpf WHERE matnr=%s AND menge=%s AND werks=%s AND lgort=%s"
        " AND COALESCE(ebeln,'')=%s AND bwart NOT IN ('102','502') AND created_at >= %s"
        " ORDER BY created_at DESC LIMIT 1",
        (matnr, menge, werks, lgort, ebeln or "", time.time() - DUPLICATE_WINDOW_SECONDS),
    ).fetchone()
