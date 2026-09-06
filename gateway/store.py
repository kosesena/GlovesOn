"""
Postgres deposu — mock S/4HANA sisteminin arkasindaki veri.

Bu dosya SAP'nin *verisini* tutar, sozlesmesini degil. OData yuzeyi
sap_mock.py'de. Gercek bir S/4HANA'ya gecildiginde bu dosya tamamen olur.

Neden SQLite degil: gateway artik istek basina uyanan bir fonksiyon olarak
calisiyor (bkz. docs/adr/0005). Orada kalici disk yok ve iki istek ayni surece
dusmeyebilir - yani yan yana duran bir dosya, bir cumlede yazilip digerinde
kaybolan bir veritabani demekti. Bedeli: artik cevrimdisi calisilamiyor,
en basit testte bile bir Postgres baglantisi gerekiyor.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

def database_url() -> str:
    """
    Calisma aninda okunuyor, import aninda degil: sunucusuz bir ortamda
    degiskenler surecin omrunden bagimsiz gelir, ve yerelde .env'in ne zaman
    yuklendigine bagli kalmak istemiyoruz.
    """
    return os.getenv("DATABASE_URL", "") or os.getenv("POSTGRES_URL", "")

# Ayni malzeme + miktar + depo yeri bu sure icinde ikinci kez gelirse yeni belge
# acilmaz. Zaman asimina ugramis bir yazmadan sonra iscinin cumleyi tekrar
# etmesi bu pencereye duser.
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

# mkpf.seq: SQLite'in rowid'si vardi, Postgres'te yok. Belge sirasi demoda
# gorunur bir sey - "son belgeler" listesi bununla siralaniyor - o yuzden
# sirayi sansa birakmayip acikca sayiyoruz.
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
    Havuz bilerek kucuk ve tembel. Bir fonksiyon ornegi birkac istegi birden
    goruyor, ama yuz tanesini gormuyor; acik tutulan her baglanti Postgres
    tarafinda bir slot demek ve sunucusuz ortamda ornek sayisi bizim
    kontrolumuzde degil. Neon'un pooled adresini kullanmak sart.
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
        _pool = ConnectionPool(url, min_size=0, max_size=4, kwargs={"row_factory": dict_row},
                               open=True, timeout=10)
    return _pool


@contextmanager
def db():
    """
    Baglanti verir; blok hatasiz biterse commit, hata alirsa rollback eder.
    Cagiran taraftaki `conn.commit()` cagrilari zararsiz, sadece gereksiz.
    """
    with pool().connection() as conn:
        yield conn


def norm_matnr(raw: str | int) -> str:
    """SAP MATNR 18 karakter, sifirla soldan dolu. Sesle '4711' denir."""
    s = str(raw).strip().upper().replace(" ", "").replace("-", "")
    return s.zfill(18) if s.isdigit() else s


def pretty_matnr(matnr: str) -> str:
    return matnr.lstrip("0") or "0"


# Sema degistiginde var olan veritabani kendini guncellemez: CREATE TABLE IF
# NOT EXISTS mevcut tabloya dokunmaz. Eksik kolonlari tek tek ekliyoruz,
# boylece eski bir veritabani yeni kodla calisiyor. Kolon eklerken bu listeyi
# de buyut - semadaki degisikligin tek basina yetecegini varsayma.
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
            continue                      # tablo henuz yok, SCHEMA olusturacak
        for name, decl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                added.append(f"{table}.{name}")
    return added


def init_db(force: bool = False) -> None:
    """
    force=True demo sifirlamasi: tablolari dusurup tohum veriyi geri yaziyor.
    Dosya silmek yerine DROP - artik silinecek bir dosya yok.
    """
    with db() as conn:
        if force:
            conn.execute("DROP TABLE IF EXISTS mard, mkpf, ekko, audit_trail, events")
        conn.execute(SCHEMA)
        added = _ensure_columns(conn)
        if added:
            print(f"  [store] eksik kolonlar eklendi: {', '.join(added)}")
        if not conn.execute("SELECT COUNT(*) AS c FROM mard").fetchone()["c"]:
            conn.cursor().executemany(
                "INSERT INTO mard (matnr, maktx, meins, werks, lgort, lgpla, labst)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                [(norm_matnr(m), d, u, w, l, b, q) for m, d, u, w, l, b, q in SEED_MATERIALS],
            )
            conn.cursor().executemany(
                "INSERT INTO ekko (ebeln, lifnr, matnr, menge, status, eta)"
                " VALUES (%s,%s,%s,%s,%s,%s)",
                [(e, li, norm_matnr(m), q, s, eta) for e, li, m, q, s, eta in SEED_ORDERS],
            )


def recent_duplicate(conn, matnr: str, menge: int, werks: str, lgort: str, ebeln: str | None):
    return conn.execute(
        "SELECT * FROM mkpf WHERE matnr=%s AND menge=%s AND werks=%s AND lgort=%s"
        " AND COALESCE(ebeln,'')=%s AND bwart NOT IN ('102','502') AND created_at >= %s"
        " ORDER BY created_at DESC LIMIT 1",
        (matnr, menge, werks, lgort, ebeln or "", time.time() - DUPLICATE_WINDOW_SECONDS),
    ).fetchone()
