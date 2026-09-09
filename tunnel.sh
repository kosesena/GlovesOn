#!/usr/bin/env bash
# Open the tunnel. The address changes on every start; write the
# https://...trycloudflare.com address from the boxed output into
# GATEWAY_PUBLIC_URL in .env, then run ./publish.sh.
exec cloudflared tunnel --url http://localhost:8000
