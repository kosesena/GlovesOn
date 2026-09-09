#!/usr/bin/env python3
"""
Publishes the definition in agent.json to AssemblyAI.

  python agent/publish.py             -> creates a new agent (or updates it if AGENT_ID is set)
  python agent/publish.py --force-new -> creates a fresh one even if AGENT_ID is set

After publishing, write the returned agent id into AGENT_ID in .env.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

API_BASE = "https://agents.assemblyai.com/v1"
API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
GATEWAY_URL = os.getenv("GATEWAY_PUBLIC_URL", "").strip().rstrip("/")
TOOL_SECRET = os.getenv("TOOL_SHARED_SECRET", "").strip()
AGENT_ID = os.getenv("AGENT_ID", "").strip()


def fail(message: str) -> None:
    print(f"\n  ERROR: {message}\n", file=sys.stderr)
    raise SystemExit(1)


def preflight() -> None:
    if not API_KEY:
        fail("ASSEMBLYAI_API_KEY is empty. Fill in the .env file.")
    if not GATEWAY_URL:
        fail("GATEWAY_PUBLIC_URL is empty. Open the tunnel first, then write the address into .env.")
    if not GATEWAY_URL.startswith("https://"):
        fail(
            "GATEWAY_PUBLIC_URL must start with https://.\n"
            "  AssemblyAI HTTP tools CANNOT reach localhost or plain http.\n"
            "  Fix:  cloudflared tunnel --url http://localhost:8000"
        )
    if "localhost" in GATEWAY_URL or "127.0.0.1" in GATEWAY_URL:
        fail("GATEWAY_PUBLIC_URL cannot be localhost - AssemblyAI calls it from the outside.")
    if not TOOL_SECRET or TOOL_SECRET in ("change-me-please", "degistir-beni-lutfen"):
        print("  WARNING: TOOL_SHARED_SECRET is still the placeholder. Change it.\n")


def build_payload() -> dict:
    raw = (ROOT / "agent" / "agent.json").read_text(encoding="utf-8")
    raw = raw.replace("{{GATEWAY_PUBLIC_URL}}", GATEWAY_URL)
    raw = raw.replace("{{TOOL_SHARED_SECRET}}", TOOL_SECRET)
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-new", action="store_true")
    args = parser.parse_args()

    preflight()
    payload = build_payload()
    headers = {"Authorization": API_KEY, "Content-Type": "application/json"}

    updating = bool(AGENT_ID) and not args.force_new

    if updating:
        # The update verb is not clear in the docs; use the first one that works.
        url = f"{API_BASE}/agents/{AGENT_ID}"
        print(f"  Updating: {AGENT_ID}")
        response = None
        for method in ("PUT", "PATCH", "POST"):
            response = httpx.request(method, url, headers=headers, json=payload, timeout=30)
            if response.status_code != 405:
                print(f"  ({method} accepted)")
                break
            print(f"  {method} not supported, trying the next...")
    else:
        url, method = f"{API_BASE}/agents", "POST"
        print("  Creating a new agent...")
        response = httpx.request(method, url, headers=headers, json=payload, timeout=30)

    if response.status_code >= 400:
        print(f"\n  {url}")
        print(f"  HTTP {response.status_code}\n", file=sys.stderr)
        _print_error(response)
        if updating:
            print("\n  Hint: if updating fails, create a fresh agent with --force-new.")
        raise SystemExit(1)

    data = response.json()
    agent_id = data.get("id") or data.get("agent_id") or "?"

    print("\n  Published.")
    print(f"  agent id : {agent_id}")
    print(f"  gateway  : {GATEWAY_URL}")
    print(f"  tools    : {', '.join(t['name'] for t in payload['tools'])}")
    if not updating:
        print(f"\n  Now write into .env:  AGENT_ID={agent_id}\n")


def _redact(text: str) -> str:
    """
    On validation errors the API reflects the body we sent back at us — and
    inside that body TOOL_SHARED_SECRET sits in six tool headers. Harmless
    in a terminal; in a CI log or a shared shell, the only thing protecting
    the write endpoints would have landed there.
    """
    secret = os.getenv("TOOL_SHARED_SECRET", "").strip()
    return text.replace(secret, "***") if secret else text


def _print_error(response) -> None:
    """
    Print the error readably. On validation errors the API reflects the
    whole body back; instead of drowning in it, show which field is broken
    and how.
    """
    try:
        data = response.json()
    except Exception:
        print(f"  {_redact(response.text[:400])}", file=sys.stderr)
        return

    detail = data.get("detail", data)
    if isinstance(detail, list):
        for item in detail:
            loc = ".".join(str(x) for x in item.get("loc", []))
            print(f"  FIELD  : {loc}", file=sys.stderr)
            print(f"  PROBLEM: {item.get('msg','')}  [{item.get('type','')}]\n", file=sys.stderr)
        return

    if isinstance(detail, dict):
        for key in ("message", "error", "detail", "code"):
            if key in detail:
                print(f"  {key}: {detail[key]}", file=sys.stderr)
        return

    print(f"  {str(detail)[:400]}", file=sys.stderr)


if __name__ == "__main__":
    main()
