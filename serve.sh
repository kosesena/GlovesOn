#!/usr/bin/env bash
# Start the gateway. Works from any tab - no activated venv required.
# DATABASE_URL is required: the mock S/4HANA keeps its data in Postgres, locally too.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/uvicorn gateway.main:app --reload --port "${PORT:-8000}"
