#!/usr/bin/env python3
"""
agent.json'daki tanimi AssemblyAI'ye yayinlar.

  python agent/publish.py            -> yeni agent olusturur (veya AGENT_ID varsa gunceller)
  python agent/publish.py --force-new -> AGENT_ID olsa bile yenisini olusturur

Yayindan sonra donen agent id'yi .env icindeki AGENT_ID'ye yaz.
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
    print(f"\n  HATA: {message}\n", file=sys.stderr)
    raise SystemExit(1)


def preflight() -> None:
    if not API_KEY:
        fail("ASSEMBLYAI_API_KEY bos. .env dosyasini doldur.")
    if not GATEWAY_URL:
        fail("GATEWAY_PUBLIC_URL bos. Once tuneli ac, sonra adresi .env'e yaz.")
    if not GATEWAY_URL.startswith("https://"):
        fail(
            "GATEWAY_PUBLIC_URL https:// ile baslamali.\n"
            "  AssemblyAI HTTP tool'lari localhost'a ve http'ye BAGLANAMAZ.\n"
            "  Cozum:  cloudflared tunnel --url http://localhost:8000"
        )
    if "localhost" in GATEWAY_URL or "127.0.0.1" in GATEWAY_URL:
        fail("GATEWAY_PUBLIC_URL localhost olamaz - AssemblyAI disaridan cagiriyor.")
    if not TOOL_SECRET or TOOL_SECRET == "degistir-beni-lutfen":
        print("  UYARI: TOOL_SHARED_SECRET varsayilan degerde. Degistirmen onerilir.\n")


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
        # Guncelleme fiili dokumanda net degil; desteklenen ilkini kullan.
        url = f"{API_BASE}/agents/{AGENT_ID}"
        print(f"  Guncelleniyor: {AGENT_ID}")
        response = None
        for method in ("PUT", "PATCH", "POST"):
            response = httpx.request(method, url, headers=headers, json=payload, timeout=30)
            if response.status_code != 405:
                print(f"  ({method} kabul edildi)")
                break
            print(f"  {method} desteklenmiyor, sonrakini deniyorum...")
    else:
        url, method = f"{API_BASE}/agents", "POST"
        print("  Yeni agent olusturuluyor...")
        response = httpx.request(method, url, headers=headers, json=payload, timeout=30)

    if response.status_code >= 400:
        print(f"\n  {url}")
        print(f"  HTTP {response.status_code}\n", file=sys.stderr)
        _print_error(response)
        if updating:
            print("\n  Ipucu: guncelleme calismazsa --force-new ile yenisini olustur.")
        raise SystemExit(1)

    data = response.json()
    agent_id = data.get("id") or data.get("agent_id") or "?"

    print("\n  Yayinlandi.")
    print(f"  agent id : {agent_id}")
    print(f"  gateway  : {GATEWAY_URL}")
    print(f"  tools    : {', '.join(t['name'] for t in payload['tools'])}")
    if not updating:
        print(f"\n  Simdi .env icine yaz:  AGENT_ID={agent_id}\n")


def _print_error(response) -> None:
    """
    Hatayi okunabilir bas. Dogrulama hatalarinda API tum govdeyi geri
    yansitiyor; icinde bogulmak yerine hangi alanin nesi bozuk onu goster.
    """
    try:
        data = response.json()
    except Exception:
        print(f"  {response.text[:400]}", file=sys.stderr)
        return

    detail = data.get("detail", data)
    if isinstance(detail, list):
        for item in detail:
            loc = ".".join(str(x) for x in item.get("loc", []))
            print(f"  ALAN : {loc}", file=sys.stderr)
            print(f"  SORUN: {item.get('msg','')}  [{item.get('type','')}]\n", file=sys.stderr)
        return

    if isinstance(detail, dict):
        for key in ("message", "error", "detail", "code"):
            if key in detail:
                print(f"  {key}: {detail[key]}", file=sys.stderr)
        return

    print(f"  {str(detail)[:400]}", file=sys.stderr)


if __name__ == "__main__":
    main()
