#!/usr/bin/env bash
# Gateway'i baslat. Hangi sekmede olursan ol calisir - venv aktif olmasi gerekmez.
# DATABASE_URL gerekiyor: mock S/4HANA verisini Postgres'te tutuyor, yerelde de.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/uvicorn gateway.main:app --reload --port "${PORT:-8000}"
