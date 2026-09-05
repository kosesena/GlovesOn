#!/usr/bin/env bash
# Gateway'i baslat. Hangi sekmede olursan ol calisir - venv aktif olmasi gerekmez.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/uvicorn gateway.main:app --reload --port 8000
