#!/usr/bin/env bash
# Tuneli ac. Adres her acilista degisir; ciktidaki kutuda yazan
# https://...trycloudflare.com adresini .env icindeki GATEWAY_PUBLIC_URL'e yaz,
# sonra ./publish.sh calistir.
exec cloudflared tunnel --url http://localhost:8000
