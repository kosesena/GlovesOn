#!/usr/bin/env bash
# Gateway'i baslat. Hangi sekmede olursan ol calisir - venv aktif olmasi gerekmez.
# Portu .replit ile ayni degiskenden okuyoruz: gateway kendi mock S/4HANA'sina
# 127.0.0.1:$PORT uzerinden baglaniyor, iki tarafin ayni sayiyi bilmesi sart.
cd "$(dirname "$0")" || exit 1
export PORT="${PORT:-8000}"
exec .venv/bin/uvicorn gateway.main:app --reload --port "$PORT"
