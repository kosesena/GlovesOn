"""
Record real tool calls against a running gateway and keep the answers.

`recent-documents` is empty until somebody talks to the demo, so a judge who
opens the deployment after a quiet week sees a system that has never done
anything. This script leaves evidence that survives that: the actual request
and the actual response for a stock read, a refused correction, a posted
material document, a refused duplicate, the provenance row and the reversal.

It drives the same door the browser uses — `/api/voice-tools/{tool}` with a
per-session capability — so the draft protocol, the allow-list, the duplicate
guard and the audit trail are all the real ones. What it does NOT do is speak:
the arguments come from this file instead of from a worker and an agent, and
the confirmation it sends says so in its own text, because a receipt that
implies a microphone nobody switched on would be worth less than no receipt.

    python -m checks.record_receipts --base https://gloveson.vercel.app

Session tokens, the capability and draft tokens are redacted before writing:
they are short-lived, and a receipt is a record, not a credential store.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx

REDACT = {"scope_token", "tool_capability", "draft_token", "token", "session_config",
          "tool_catalog"}
CONFIRMATION_NOTE = ("yes, confirm — typed by checks/record_receipts.py, "
                     "no microphone and no spoken turn in this run")


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("<redacted: short-lived>" if k in REDACT else scrub(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


class Recorder:
    def __init__(self, base: str, out: Path) -> None:
        self.base = base.rstrip("/")
        self.out = out
        self.client = httpx.Client(timeout=60)
        self.scope_token = ""
        self.capability = ""
        self.index: list[dict[str, Any]] = []
        self.step = 0

    def headers(self) -> dict[str, str]:
        return {"X-Event-Scope": self.scope_token, "X-Voice-Capability": self.capability}

    def record(self, name: str, method: str, path: str, *, request: dict | None = None,
               params: dict | None = None, authorized: bool = True) -> dict[str, Any]:
        started = time.time()
        response = self.client.request(
            method, f"{self.base}{path}", json=request, params=params,
            headers=self.headers() if authorized else None)
        elapsed = round((time.time() - started) * 1000)
        try:
            body = response.json()
        except ValueError:
            body = {"non_json_body": response.text[:500]}
        self.save(name, method, path, request, params, response.status_code, body,
                  elapsed, started)
        return body

    def save(self, name: str, method: str, path: str, request: dict | None,
             params: dict | None, status: int, body: Any, elapsed: int,
             started: float) -> None:
        self.step += 1
        receipt = {
            "step": self.step,
            "name": name,
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
            "gateway": self.base,
            "request": {"method": method, "path": path,
                        "body": scrub(request) if request else None,
                        "query": params or None},
            "status": status,
            "elapsed_ms": elapsed,
            "response": scrub(body),
        }
        target = self.out / f"{self.step:02d}-{name}.json"
        target.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
        self.index.append({"step": self.step, "name": name, "status": status,
                           "file": target.name, "elapsed_ms": elapsed})
        print(f"  {self.step:02d} {name:38} {status} {elapsed:>6} ms")

    def tool(self, name: str, arguments: dict) -> dict[str, Any]:
        return self.record(name, "POST", f"/api/voice-tools/{name}", request=arguments)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://gloveson.vercel.app")
    parser.add_argument("--material", default="4711")
    parser.add_argument("--quantity", type=int, default=40)
    parser.add_argument("--out", default="receipts")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.json"):
        stale.unlink()

    r = Recorder(args.base, out)
    print(f"Recording against {r.base}")

    # One session only: the endpoint is rate limited by the hour, and every
    # extra call spends a slot a rehearsal may need.
    started = time.time()
    opened = r.client.get(f"{r.base}/api/voice-token")
    raw = opened.json()
    r.save("voice-session-opened", "GET", "/api/voice-token", None, None,
           opened.status_code, raw, round((time.time() - started) * 1000), started)
    if opened.status_code != 200:
        print(f"  could not open a session: {raw}")
        return 1
    r.scope_token = raw["scope_token"]
    r.capability = raw["tool_capability"]

    goods = {"material": args.material, "quantity": args.quantity}

    r.tool("get_stock", {"material": args.material})
    prepared = r.tool("prepare_goods_receipt", dict(goods))
    token = prepared.get("draft_token", "")

    # The read-back said one quantity; the confirmation names another. A write
    # that differs from the sentence read back is the failure this project
    # exists to prevent, so it must be visible in the evidence, not only in a test.
    r.record("refused-quantity-changed-after-readback", "POST",
             "/api/voice-tools/post_goods_receipt",
             request={**goods, "quantity": args.quantity + 1, "draft_token": token,
                      "confirmed_utterance": CONFIRMATION_NOTE, "user_confirmation": "yes"})

    prepared = r.tool("prepare_goods_receipt", dict(goods))
    posted = r.record("posted-goods-receipt", "POST", "/api/voice-tools/post_goods_receipt",
                      request={**goods, "draft_token": prepared.get("draft_token", ""),
                               "confirmed_utterance": CONFIRMATION_NOTE,
                               "user_confirmation": "yes"})
    document = posted.get("MBLNR")
    if not document:
        print(f"  no document posted: {posted.get('message')}")
        return 1

    # Same intent, fresh draft, fresh confirmation. Real S/4HANA would accept
    # this second posting; the gateway is where it gets refused.
    prepared = r.tool("prepare_goods_receipt", dict(goods))
    r.record("refused-duplicate", "POST", "/api/voice-tools/post_goods_receipt",
             request={**goods, "draft_token": prepared.get("draft_token", ""),
                      "confirmed_utterance": CONFIRMATION_NOTE, "user_confirmation": "yes"})

    r.record("provenance", "GET", f"/api/provenance/{document}", authorized=False)

    prepared = r.tool("prepare_reversal", {"document": document})
    r.record("reversed", "POST", "/api/voice-tools/reverse_goods_receipt",
             request={"document": document, "draft_token": prepared.get("draft_token", ""),
                      "confirmed_utterance": CONFIRMATION_NOTE, "user_confirmation": "yes"})

    r.tool("get_stock", {"material": args.material})
    r.record("voice-session-closed", "POST", "/api/voice-session/end",
             request={"scope_token": r.scope_token}, authorized=False)

    (out / "index.json").write_text(json.dumps({
        "gateway": r.base,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "material_document": document,
        "spoken": False,
        "note": ("Real HTTP calls through the browser's own tool door. The arguments were "
                 "supplied by this script, not by a worker or an agent."),
        "steps": r.index,
    }, indent=2) + "\n")
    print(f"\nMaterial document {document} — {len(r.index)} receipts in {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
