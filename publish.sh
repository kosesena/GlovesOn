#!/usr/bin/env bash
# Ajani yayinla. Hangi sekmede olursan ol calisir.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python agent/publish.py "$@"
