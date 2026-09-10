#!/usr/bin/env python3
"""
Point the real client at a real SAP endpoint and write down what actually happens.

`docs/JUDGE-GUIDE.md` names three specific unknowns between "speaks the API
correctly" and "works against S/4HANA": CSRF behaviour behind a reverse proxy,
$batch for multi-item documents, and error payloads considerably less tidy than
a mock's. This script settles the first and the third against SAP's own sandbox.

It is deliberately READ-ONLY. Nothing here posts a document. The sandbox is a
shared environment belonging to SAP, and writing into it is a separate decision
taken on purpose, not a side effect of finding out whether reads work.

Put the key in .env, which is gitignored, rather than in the shell — an exported
key lives on in shell history, and this one is yours rather than the project's:

    SAP_API_KEY=...                        # add the line to .env
    ./.venv/bin/python checks/probe_real_sap.py

The venv matters: httpx is installed there and not in the system python.

The output is evidence either way. A failure that names its cause is worth more
to this repository than a success nobody can reproduce, so every outcome is
printed with the status and the first of SAP's own words.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx

# This script does not import the gateway package, so nothing has loaded .env for
# it. Do that here, so the key can live in the gitignored file rather than in the
# shell's history.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - only when run outside the venv
    pass

SANDBOX = "https://sandbox.api.sap.com/s4hanacloud"

SERVICES = {
    "material document": "/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV",
    "material stock": "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV",
    "product": "/sap/opu/odata/sap/API_PRODUCT_SRV",
    "purchase order": "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV",
}


def first_words(body: str, limit: int = 160) -> str:
    """SAP's own sentence, whatever envelope it arrived in."""
    try:
        data = json.loads(body)
    except ValueError:
        return body[:limit].replace("\n", " ").strip()
    for path in (("error", "message", "value"), ("fault", "faultstring"),
                 ("error", "message")):
        node = data
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, str):
            return node[:limit]
    return body[:limit].replace("\n", " ").strip()


async def main() -> int:
    key = os.getenv("SAP_API_KEY", "").strip()
    if not key or key in {"buraya", "...", "your-key", "change-me"}:
        print("SAP_API_KEY is not set to a real key.")
        print("Get one free from api.sap.com (log in, open any S/4HANA API, Show API Key),")
        print("then add  SAP_API_KEY=<the key>  to .env and run this again.")
        return 2

    base = os.getenv("SAP_BASE_URL", "").strip().rstrip("/") or SANDBOX
    print(f"Probing {base}\n")

    async with httpx.AsyncClient(timeout=20, headers={"APIKey": key},
                                 follow_redirects=False) as client:
        print("1. Do the four services this gateway uses exist and answer?\n")
        reachable = {}
        for name, path in SERVICES.items():
            try:
                r = await client.get(f"{base}{path}/$metadata")
            except httpx.RequestError as exc:
                print(f"   {name:<20} transport error: {exc!r}")
                continue
            reachable[name] = r.status_code == 200
            note = "" if r.status_code == 200 else f"  {first_words(r.text)}"
            print(f"   {name:<20} HTTP {r.status_code}{note}")

        print("\n2. Does the CSRF handshake behave the same behind SAP's gateway?\n")
        doc = SERVICES["material document"]
        r = await client.get(f"{base}{doc}/", headers={"X-CSRF-Token": "Fetch"})
        token = r.headers.get("X-CSRF-Token")
        print(f"   fetch              HTTP {r.status_code}")
        print(f"   token returned     {'yes, ' + token[:12] + '…' if token else 'NO'}")
        print(f"   session cookie     {'yes' if r.cookies else 'no'}")
        if not token:
            # Worth stating plainly: our client raises CSRF_FETCH_FAILED here, which
            # reads as a protocol fault. Behind an API gateway it usually is not one.
            print("   → the client would raise CSRF_FETCH_FAILED. Check the key first.")

        print("\n3. Does a real read return the shape the gateway parses?\n")
        r = await client.get(f"{base}{doc}/A_MaterialDocumentHeader", params={"$top": 1})
        print(f"   documents          HTTP {r.status_code}")
        if r.status_code == 200:
            rows = r.json().get("d", {}).get("results", [])
            print(f"   envelope           {'d.results, as expected' if rows or r.json().get('d') else 'UNEXPECTED'}")
            if rows:
                keys = sorted(rows[0])[:8]
                print(f"   first row fields   {', '.join(keys)}")
        else:
            print(f"   {first_words(r.text)}")

        print("\n4. What does a real error look like? (deliberately bad filter)\n")
        r = await client.get(f"{base}{doc}/A_MaterialDocumentHeader",
                             params={"$filter": "NotAField eq 'x'"})
        print(f"   HTTP {r.status_code}")
        print(f"   {first_words(r.text)}")
        print("\n   _parse_odata_error expects error.message.value; compare the above.")

    print("\nRead-only probe complete. Nothing was written.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
