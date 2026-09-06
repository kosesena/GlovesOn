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

from gateway import audit, live, store  # noqa: E402
from gateway.main import app  # noqa: E402

SECRET = os.environ["TOOL_SHARED_SECRET"]
AUTH = {"X-Tool-Secret": SECRET}


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


def post_receipt(client, **body):
    payload = {"material": "4711", "quantity": 20,
               "confirmed_utterance": "Twenty pieces of hex bolt into bin A-03-02",
               "session_id": "test-session"}
    payload.update(body)
    return client.post("/erp/goods-receipt", json=payload, headers=AUTH)


def stock_level(client, material="4711", lgort="0001"):
    rows = client.get(f"/erp/stock?material={material}", headers=AUTH).json()["locations"]
    return next(r["LABST"] for r in rows if r["LGORT"] == lgort)
