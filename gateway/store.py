"""
SQLite deposu — mock S/4HANA sisteminin arkasindaki veri.

Bu dosya SAP'nin *verisini* tutar, sozlesmesini degil. OData yuzeyi
sap_mock.py'de. Gercek bir S/4HANA'ya gecildiginde bu dosya tamamen olur.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

# Varsayilan olarak dosya kodun yanindadir. Bir dagitimda kod dizini her
# yayinda yeniden kurulur, yani veri yayinlar arasi yasamaz; kalici bir disk
# baglayabilenler GLOVESON_DB_PATH ile onu gosterir. Mock icin kayip veri
# felaket degil - acilista tohum veri yeniden yazilir - ama bu ayrimi
# yapilandirmayla soylemek, kod okuyup tahmin ettirmekten iyi.
DB_PATH = Path(os.getenv("GLOVESON_DB_PATH", "")
               or Path(__file__).resolve().parent / "gloveson.db")

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

SCHEMA = """
CREATE TABLE IF NOT EXISTS mard (
    matnr TEXT NOT NULL, maktx TEXT NOT NULL, meins TEXT NOT NULL,
    werks TEXT NOT NULL, lgort TEXT NOT NULL, lgpla TEXT NOT NULL,
    labst INTEGER NOT NULL,
    PRIMARY KEY (matnr, werks, lgort)
);
CREATE TABLE IF NOT EXISTS mkpf (
    mblnr TEXT PRIMARY KEY, mjahr TEXT NOT NULL, bwart TEXT NOT NULL,
    matnr TEXT NOT NULL, menge INTEGER NOT NULL, meins TEXT NOT NULL,
    werks TEXT NOT NULL, lgort TEXT NOT NULL, lgpla TEXT NOT NULL,
    budat TEXT NOT NULL, ebeln TEXT, reversed_of TEXT,
    created_at REAL NOT NULL DEFAULT 0,
    bktxt TEXT NOT NULL DEFAULT '',   -- MaterialDocumentHeaderText
    xblnr TEXT NOT NULL DEFAULT ''    -- basliktaki ReferenceDocument
);
CREATE TABLE IF NOT EXISTS ekko (
    ebeln TEXT PRIMARY KEY, lifnr TEXT NOT NULL, matnr TEXT NOT NULL,
    menge INTEGER NOT NULL, status TEXT NOT NULL, eta TEXT NOT NULL
);
"""


def norm_matnr(raw: str | int) -> str:
    """SAP MATNR 18 karakter, sifirla soldan dolu. Sesle '4711' denir."""
    s = str(raw).strip().upper().replace(" ", "").replace("-", "")
    return s.zfill(18) if s.isdigit() else s


def pretty_matnr(matnr: str) -> str:
    return matnr.lstrip("0") or "0"


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Sema degistiginde eski veritabani dosyasi kendini guncellemez:
# CREATE TABLE IF NOT EXISTS var olan tabloya dokunmaz. Eksik kolonlari
# tek tek ekliyoruz, boylece eski bir gloveson.db yeni kodla calisiyor.
MIGRATIONS = {
    "mkpf": [
        ("mjahr", "TEXT NOT NULL DEFAULT ''"),
        ("reversed_of", "TEXT"),
        ("created_at", "REAL NOT NULL DEFAULT 0"),
        ("bktxt", "TEXT NOT NULL DEFAULT ''"),
        ("xblnr", "TEXT NOT NULL DEFAULT ''"),
    ],
}


def _ensure_columns(conn) -> list[str]:
    added = []
    for table, columns in MIGRATIONS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue                      # tablo henuz yok, SCHEMA olusturacak
        for name, decl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                added.append(f"{table}.{name}")
    return added


def init_db(force: bool = False) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if force and DB_PATH.exists():
        DB_PATH.unlink()
    with closing(db()) as conn:
        conn.executescript(SCHEMA)
        added = _ensure_columns(conn)
        if added:
            print(f"  [store] eksik kolonlar eklendi: {', '.join(added)}")
        if not conn.execute("SELECT COUNT(*) c FROM mard").fetchone()["c"]:
            conn.executemany(
                "INSERT INTO mard (matnr, maktx, meins, werks, lgort, lgpla, labst)"
                " VALUES (?,?,?,?,?,?,?)",
                [(norm_matnr(m), d, u, w, l, b, q) for m, d, u, w, l, b, q in SEED_MATERIALS],
            )
            conn.executemany(
                "INSERT INTO ekko (ebeln, lifnr, matnr, menge, status, eta) VALUES (?,?,?,?,?,?)",
                [(e, li, norm_matnr(m), q, s, eta) for e, li, m, q, s, eta in SEED_ORDERS],
            )
        conn.commit()


def recent_duplicate(conn, matnr: str, menge: int, werks: str, lgort: str, ebeln: str | None):
    return conn.execute(
        "SELECT * FROM mkpf WHERE matnr=? AND menge=? AND werks=? AND lgort=?"
        " AND IFNULL(ebeln,'')=? AND bwart NOT IN ('102','502') AND created_at >= ?"
        " ORDER BY created_at DESC LIMIT 1",
        (matnr, menge, werks, lgort, ebeln or "", time.time() - DUPLICATE_WINDOW_SECONDS),
    ).fetchone()
