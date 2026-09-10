"""
What the internet can reach.

These are regression tests for real findings, not hypotheticals. Each one was
exploitable against the live deployment on 2026-09-06 and is named for what it
allowed. They exist so the doors cannot quietly reopen: a router remounted for
convenience, a default flipped back, a CORS middleware added for a stray fetch.
"""

from __future__ import annotations

from conftest import AUTH

# --- the mock ERP is not on the public app ----------------------------------

def test_the_mock_odata_surface_is_not_routed_publicly(client):
    # It used to be. Two anonymous requests — fetch a CSRF token, then POST —
    # wrote a material document with no secret, no read-back, no duplicate
    # check and no audit row, which made the project's central claim false
    # from the outside.
    assert client.get("/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/").status_code == 404
    assert client.get(
        "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod?Material=4711"
    ).status_code == 404


def test_the_public_app_offers_no_way_to_post_a_material_document(client):
    r = client.post("/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader",
                    json={"GoodsMovementCode": "05", "to_MaterialDocumentItem": [
                        {"Material": "4711", "Plant": "1000", "StorageLocation": "0001",
                         "GoodsMovementType": "501", "QuantityInEntryUnit": "9999"}]})
    assert r.status_code == 404


def test_every_erp_route_refuses_an_unauthenticated_caller(client):
    # Anything under /erp/ reads or writes the system of record. Called with
    # valid input and no secret, each one must answer 401 — not a result.
    calls = [
        ("GET", "/erp/stock?material=4711", None),
        ("GET", "/erp/material-search?query=bolt", None),
        ("GET", "/erp/mm-knowledge?query=invoice", None),
        ("GET", "/erp/purchase-order?order=4500001234", None),
        ("GET", "/erp/recent-documents", None),
        ("POST", "/erp/goods-receipt", {"material": "4711", "quantity": 20}),
        ("POST", "/erp/reverse-goods-receipt", {"document": "4900000000"}),
        # The preparation endpoints mint write drafts; a stranger minting
        # drafts is a stranger halfway to a posting, so they answer 401 too.
        ("POST", "/erp/prepare-goods-receipt", {"material": "4711", "quantity": 20}),
        ("POST", "/erp/prepare-reversal", {"document": "4900000000"}),
        ("GET", "/erp/colleagues?query=Alex", None),
        ("GET", "/erp/communications", None),
        ("POST", "/erp/follow-up-options", {"reason": "Eight pieces are missing."}),
        ("POST", "/erp/prepare-email", {"colleague_id": "alex", "subject": "Delivery", "body": "Twelve arrived."}),
        ("POST", "/erp/send-email", {"colleague_id": "alex", "subject": "Delivery", "body": "Twelve arrived."}),
        ("POST", "/erp/prepare-call", {"colleague_id": "alex", "purpose": "Delivery"}),
        ("POST", "/erp/send-call", {"colleague_id": "alex", "purpose": "Delivery"}),
        ("POST", "/erp/prepare-note", {"title": "Delivery", "body": "Twelve arrived."}),
        ("POST", "/erp/send-note", {"title": "Delivery", "body": "Twelve arrived."}),
    ]
    routed = {r.path for r in client.app.routes if getattr(r, "path", "").startswith("/erp/")}
    assert routed == {p.split("?")[0] for _, p, _ in calls}, (
        "an /erp route was added or removed without being covered here"
    )
    for method, path, body in calls:
        r = client.request(method, path, json=body)
        assert r.status_code == 401, f"{path} answered {r.status_code} without a secret"


# --- destructive endpoints ---------------------------------------------------

def test_reset_is_refused_without_the_flag_and_without_the_secret(client):
    # It answered an anonymous POST with 200 on the live URL, dropping every
    # table including audit_trail. It carries no custom header, so a browser
    # sends it with no preflight: visiting a hostile page was enough.
    assert client.post("/api/reset").status_code == 403
    assert client.post("/api/reset", headers=AUTH).status_code == 403


# --- what an anonymous caller learns ----------------------------------------

def test_health_does_not_hand_out_the_agent_id(client):
    # The agent id is half of what it takes to open a voice session against our
    # agent, and /health is anonymous. Whether one is configured is fine to say;
    # which one it is, is not.
    body = client.get("/health").json()
    assert "agent_id" not in body
    assert body["agent_configured"] is True     # AGENT_ID is pinned in conftest


def test_no_wildcard_cors_header_is_returned(client):
    # Wildcard CORS let any page in a visitor's browser read the minted voice
    # token and the ERP data. Tool calls come from AssemblyAI's servers and the
    # client is same-origin, so the header buys nothing.
    r = client.get("/api/inventory", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}
