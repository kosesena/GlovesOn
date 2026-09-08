"""
Shared fixtures.

The tests run against a real Postgres, never a fake one. The mock S/4HANA is
the system under test as much as the gateway is: its CSRF handshake, its
movement-type rules and its refusal messages are what the agent will meet, and
a stubbed database would test none of it.

They must not run against the demo database. TEST_DATABASE_URL is required and
is checked to be a different database from DATABASE_URL, because every test
drops and reseeds the schema — pointing it at the deployment's data would empty
it silently.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()
DEMO_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not TEST_DATABASE_URL:
    pytest.skip(
        "TEST_DATABASE_URL is not set. These tests drop and recreate every table, so "
        "they need a database of their own — never the one the deployment uses.",
        allow_module_level=True,
    )

if TEST_DATABASE_URL == DEMO_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL and DATABASE_URL are the same database. The tests would "
        "erase the demo data on the first run."
    )

# The gateway reads its configuration when the package is imported, so the
# environment has to be right before that happens.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("TOOL_SHARED_SECRET", "test-secret-not-a-real-one")
os.environ["GLOVESON_ENABLE_RESET"] = "0"
os.environ["ASSEMBLYAI_API_KEY"] = ""
os.environ["SAP_BASE_URL"] = ""
os.environ["MOCK_SAP_BASE_URL"] = ""
# Pinned so the tests do not depend on whether the developer running them
# happens to have published an agent. CI has no .env at all.
os.environ["AGENT_ID"] = "test-agent-id"

from fastapi.testclient import TestClient  # noqa: E402

from gateway import audit, live, session_scope, store  # noqa: E402
from gateway.main import app  # noqa: E402

SECRET = os.environ["TOOL_SHARED_SECRET"]
AUTH = {"X-Tool-Secret": SECRET}


def scoped_headers():
    """One voice session's identity. The same scope must sign the preparation
    and the write — the draft is keyed to it — so tests mint one per exchange
    and pass it to both calls, exactly as the published agent does."""
    return {**AUTH, "X-Event-Scope": session_scope.issue(SECRET)}


def scope_of(headers):
    return session_scope.verify(headers["X-Event-Scope"], SECRET)


@pytest.fixture()
def client():
    """
    A fresh database per test. The seed data is small and the guarantees under
    test are about *sequences* of writes — a receipt, then its repeat, then its
    reversal — so leaking rows between tests would make failures depend on
    order.
    """
    store.init_db(force=True)
    audit.init()
    live.init()
    with TestClient(app) as c:
        yield c


def post_receipt(client, headers=None, drafted=True, user_confirmation="confirm", **body):
    """Prepare-then-confirm, the way the agent is now required to write.

    drafted=False skips the preparation and calls the write bare — the path a
    misbehaving client would take. Input validation runs before the draft is
    consumed, so the validation tests use it to reach their messages; the
    contract tests use it to prove a bare call cannot post. If a preparation
    itself is refused (unknown material, malformed quantity), the helper falls
    back to the bare call so the refusal message still comes from validation,
    which fires first on both paths."""
    headers = headers or scoped_headers()
    payload = {"material": "4711", "quantity": 20,
               "confirmed_utterance": "Twenty pieces of hex bolt into bin A-03-02"}
    payload.update(body)
    details = {k: v for k, v in payload.items()
               if k in ("material", "quantity", "plant", "storage_location",
                        "purchase_order", "allow_duplicate")}
    if drafted:
        prep = client.post("/erp/prepare-goods-receipt", json=details, headers=headers).json()
        if prep.get("prepared"):
            payload["draft_token"] = prep["draft_token"]
            payload.setdefault("user_confirmation", user_confirmation)
    return client.post("/erp/goods-receipt", json=payload, headers=headers)


def reverse_receipt(client, document, headers=None, drafted=True,
                    user_confirmation="confirm", **body):
    """The reversal twin of post_receipt, through /erp/prepare-reversal."""
    headers = headers or scoped_headers()
    payload = {"document": document,
               "confirmed_utterance": f"Reverse document {document}"}
    payload.update(body)
    details = {"document": document}
    if drafted:
        prep = client.post("/erp/prepare-reversal", json=details, headers=headers).json()
        if prep.get("prepared"):
            payload["draft_token"] = prep["draft_token"]
            payload.setdefault("user_confirmation", user_confirmation)
    return client.post("/erp/reverse-goods-receipt", json=payload, headers=headers)


def stock_level(client, material="4711", lgort="0001"):
    rows = client.get(f"/erp/stock?material={material}", headers=AUTH).json()["locations"]
    return next(r["LABST"] for r in rows if r["LGORT"] == lgort)
