"""Signed event-routing scopes. These do not authorize ERP operations."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time


def issue(secret: str, *, now: int | None = None, ttl: int = 420) -> str:
    if not secret or ttl <= 0:
        raise ValueError("A signing secret and positive TTL are required")
    issued = int(time.time()) if now is None else now
    payload = f"v1.{secrets.token_hex(16)}.{issued + ttl}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify(token: str, secret: str, *, now: int | None = None) -> str | None:
    """Return an opaque scope id only for an intact, unexpired token."""
    if not secret or not isinstance(token, str) or len(token) > 160:
        return None
    parts = token.split('.')
    if len(parts) != 4:
        return None
    version, scope, expiry, signature = parts
    if version != 'v1' or len(scope) != 32 or any(c not in '0123456789abcdef' for c in scope):
        return None
    if len(signature) != 64 or any(c not in '0123456789abcdef' for c in signature):
        return None
    try:
        expires = int(expiry)
    except ValueError:
        return None
    expected = hmac.new(secret.encode(), '.'.join(parts[:3]).encode(), hashlib.sha256).hexdigest()
    current = int(time.time()) if now is None else now
    if not hmac.compare_digest(expected, signature) or expires <= current:
        return None
    return scope


def owns_event(scope: str, event: dict) -> bool:
    """Unscoped events and other sessions never belong to this reader."""
    return bool(scope) and event.get("data", {}).get("event_scope") == scope
