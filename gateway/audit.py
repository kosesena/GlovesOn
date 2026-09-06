"""
Denetim izi: hangi cumle hangi belgeyi dogurdu.

SAP belgesi "ne oldu"yu tutar; bu dosya "neden oldu"yu — belge numarasindan
geriye, isciye okunup onaylanan cumleye ve saniyesine gidilebilsin diye.
docs/clean-core.md'nin actigi bosluk burada KAPANMIYOR: principal propagation
olmadan SAP hala kimin konustugunu bilmiyor. Bu iz onun yerine gecmez, onu
beklerken elimizde olan tek dogru seyi kaydeder: soylenen sozun kendisi.

Bilerek store.py'de degil. store.py mock S/4HANA'nin veritabanidir ve gercek
bir tenant'a gecildiginde tamamen olur; denetim izi ise tam o gun daha da
gerekli. Ayni SQLite dosyasini paylasiyorlar - ikinci bir dosya iki yedekleme
ve iki yol demekti - ama tablo, mock silinip gittiginde tasinacak sekilde
kendi basina duruyor.
"""

from __future__ import annotations

import time
from typing import Any

from . import store

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_trail (
    mblnr      TEXT NOT NULL,          -- SAP belge numarasi
    action     TEXT NOT NULL,          -- goods_receipt | reversal
    utterance  TEXT NOT NULL,          -- isciye okunup onaylanan cumle
    session_id TEXT NOT NULL,          -- ses oturumu referansi
    created_at REAL NOT NULL           -- UTC epoch, gateway saati
);
CREATE INDEX IF NOT EXISTS idx_audit_mblnr ON audit_trail (mblnr);
"""


def init() -> None:
    with store.db() as conn:
        conn.execute(SCHEMA)


def record(mblnr: str, action: str, utterance: str, session_id: str) -> None:
    with store.db() as conn:
        conn.execute(
            "INSERT INTO audit_trail (mblnr, action, utterance, session_id, created_at)"
            " VALUES (%s,%s,%s,%s,%s)",
            (mblnr, action, utterance.strip()[:500], session_id.strip()[:64], time.time()),
        )


def lookup(mblnr: str) -> dict[str, Any] | None:
    with store.db() as conn:
        r = conn.execute(
            "SELECT * FROM audit_trail WHERE mblnr=%s ORDER BY created_at DESC LIMIT 1",
            (mblnr,),
        ).fetchone()
    return dict(r) if r else None
