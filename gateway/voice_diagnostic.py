"""Allowlisted provider metadata for an authenticated, non-operational probe.

Never log raw agent JSON: HTTP tool definitions can contain credentials.
"""
from __future__ import annotations

import hashlib
import json

import httpx


def response_summary(response: httpx.Response, payload: dict | None = None) -> dict:
    out = {
        "status": response.status_code,
        "headers": {key: response.headers[key][:200] for key in
                    ("server", "content-type", "date", "via", "age", "cf-ray", "x-request-id", "x-cache")
                    if key in response.headers},
        "body_bytes": len(response.content),
    }
    try:
        body = response.json()
    except ValueError:
        out["json"] = False
        return out
    out["json"] = True
    out["body_type"] = type(body).__name__
    if not isinstance(body, dict):
        return out
    out["field_types"] = {key: type(value).__name__ for key, value in body.items()}
    # Do not copy arbitrary error strings, tools, prompts or configuration values.
    out["identifiers"] = {key: value for key in ("id", "agent_id", "created_at", "updated_at")
                          if isinstance((value := body.get(key)), (str, int))}
    if payload is not None:
        out["echoed_fields_match"] = {key: body[key] == value for key, value in payload.items() if key in body}
    return out


def payload_digest(payload: dict) -> str:
    """Only used with invalid diagnostic credentials, never production secrets."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
