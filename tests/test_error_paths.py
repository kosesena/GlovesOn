"""
What the gateway says when SAP misbehaves mid-write.

The hardening list named these as the code work left: a timeout mid-write, a CSRF token
refused twice, a reversal of a document that has scrolled out of the last ten.
The faults are injected at the transport between the gateway's SapClient and
the mock, so the OData path, the handshake and the mock's own rules stay
exactly what they are in production; only the wire misbehaves.

Two properties run through every test. The agent gets a refusal it can say out
loud, never a 500. And the stock is read back at the end, so "nothing was
written" (or "exactly one thing was written") is asserted.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import AUTH, post_receipt, reverse_receipt, scoped_headers, stock_level

from gateway import main
from gateway.main import mock_app
from gateway.sap_client import SapClient


class FaultyWire(httpx.AsyncBaseTransport):
    """The ASGI transport to the mock, with a fault script in front of it.

    `script` is a list of callables. Each request is shown to the first step
    still waiting; the step returns None to let the request through untouched
    (and stays armed for the next one), or acts and is spent: a Response
    (answer without reaching the mock), an exception to raise, or the string
    "lose" (let the mock handle the request, then drop its answer and raise a
    timeout — the "did it land?" case). Requests beyond the script pass through.
    """

    def __init__(self, script=()):
        self.inner = httpx.ASGITransport(app=mock_app)
        self.script = list(script)
        self.seen: list[httpx.Request] = []

    async def handle_async_request(self, request):
        self.seen.append(request)
        action = self.script[0](request) if self.script else None
        if action is not None:
            self.script.pop(0)
        if action == "lose":
            await self.inner.handle_async_request(request)
            raise httpx.ReadTimeout("answer lost after the request reached SAP", request=request)
        if isinstance(action, Exception):
            raise action
        if isinstance(action, httpx.Response):
            return action
        return await self.inner.handle_async_request(request)

    def posts(self):
        return [r for r in self.seen if r.method == "POST"]

    def fetches(self):
        return [r for r in self.seen if r.headers.get("X-CSRF-Token") == "Fetch"]


@pytest.fixture()
def wire(client, monkeypatch):
    """Swap the gateway's SAP client for one whose wire the test controls."""
    w = FaultyWire()
    monkeypatch.setattr(main, "_sap", SapClient("http://mock-s4hana.internal", transport=w))
    yield w
    monkeypatch.setattr(main, "_sap", None)


def only_posts(action):
    """A script step that acts on POSTs and lets everything else through.
    `action` may be a value (an exception, "lose") or a callable that builds
    the answer from the request (a Response that needs the request attached)."""
    return lambda r: (action(r) if callable(action) else action) if r.method == "POST" else None


def csrf_refusal(request):
    return httpx.Response(
        403, request=request,
        json={"error": {"code": "CSRF_TOKEN_INVALID",
                        "message": {"value": "CSRF token validation failed. Fetch a token from the service root first."}}})


# --- SAP times out mid-write -----------------------------------------------------

def test_a_timeout_before_the_write_reaches_sap_is_a_refusal_not_a_crash(client, wire):
    wire.script = [only_posts(httpx.ReadTimeout("no answer", request=None))]
    before = stock_level(client)

    r = post_receipt(client)

    assert r.status_code == 200          # a refusal the agent can read, not a 500
    body = r.json()
    assert body["posted"] is False
    assert "do not repeat" in body["message"].lower()
    assert stock_level(client) == before


def test_a_write_whose_answer_is_lost_is_caught_by_the_duplicate_guard(client, wire):
    # The scenario nfr.md calls the most serious defect in the design: the
    # request reached SAP, the document was created, the answer never came
    # back. The worker hears "no answer" and says the sentence again. The
    # first call must report the ambiguity, and the second must find the
    # document instead of posting a twin.
    wire.script = [only_posts("lose")]
    before = stock_level(client)

    first = post_receipt(client).json()
    assert first["posted"] is False
    assert "may or may not exist" in first["message"]
    assert stock_level(client) == before + 20     # it landed; the answer was lost

    second = post_receipt(client).json()          # the repeat, read back and confirmed again
    assert second["posted"] is False
    assert second.get("duplicate") is True
    assert "already went through" in second["message"]
    assert stock_level(client) == before + 20     # once, not twice


def test_the_worker_can_force_the_second_delivery_after_a_lost_answer(client, wire):
    # ...and if it genuinely was a second pallet, the explicit path still works.
    wire.script = [only_posts("lose")]
    before = stock_level(client)
    post_receipt(client)

    forced = post_receipt(client, allow_duplicate=True).json()

    assert forced["posted"] is True
    assert stock_level(client) == before + 40


def test_a_timeout_on_a_read_says_it_is_safe_to_retry(client, wire):
    wire.script = [lambda r: httpx.ReadTimeout("no answer", request=None) if r.method == "GET" else None]

    r = client.get("/erp/stock?material=4711", headers=AUTH)

    assert r.status_code in (200, 502, 504)
    text = r.text.lower()
    assert "did not answer" in text
    assert "nothing was written" in text


# --- CSRF refused ------------------------------------------------------------------

def test_a_csrf_token_refused_once_is_refreshed_and_the_write_goes_through(client, wire):
    # The path real SAP integrations take: the token expired, SAP says 403,
    # the client fetches a fresh one and retries. One document, not two.
    wire.script = [only_posts(csrf_refusal)]
    before = stock_level(client)

    body = post_receipt(client).json()

    assert body["posted"] is True
    assert stock_level(client) == before + 20
    assert len(wire.posts()) == 2          # the refused attempt and the retry
    assert len(wire.fetches()) == 2        # the first handshake and the refresh


def test_a_csrf_token_refused_twice_is_a_refusal_with_sap_s_own_words(client, wire):
    # Refresh once, retry once, then stop. No third attempt, no loop, and the
    # agent hears the reason SAP gave rather than a generic failure.
    wire.script = [only_posts(csrf_refusal), only_posts(csrf_refusal)]
    before = stock_level(client)

    r = post_receipt(client)

    assert r.status_code == 200
    body = r.json()
    assert body["posted"] is False
    assert "csrf token validation failed" in body["message"].lower()
    assert stock_level(client) == before
    assert len(wire.posts()) == 2          # exactly one retry


def test_a_handshake_that_returns_no_token_is_reported_as_such(client, wire):
    # Behind SAP's API gateway an unauthenticated fetch comes back without a
    # token. That is what the 10 September sandbox probe looked like from
    # here, and it must read as "no token", not as a crash further down.
    def strip_token(request):
        if request.headers.get("X-CSRF-Token") == "Fetch":
            return httpx.Response(200, request=request, headers={}, json={"d": {"results": []}})
        return None
    wire.script = [strip_token, strip_token]
    before = stock_level(client)

    body = post_receipt(client).json()

    assert body["posted"] is False
    assert "csrf token" in body["message"].lower()
    assert stock_level(client) == before


def test_sap_errors_on_a_write_leave_the_draft_spent(client, wire):
    # After SAP refuses, the draft is gone: the agent cannot resend the same
    # token once the wire recovers. It has to read the line back again, which
    # is the right cost, because the worker may have walked away in between.
    wire.script = [only_posts(csrf_refusal), only_posts(csrf_refusal)]
    headers = scoped_headers()
    prep = client.post("/erp/prepare-goods-receipt",
                       json={"material": "4711", "quantity": 20}, headers=headers).json()
    payload = {"material": "4711", "quantity": 20, "draft_token": prep["draft_token"],
               "user_confirmation": "yes", "confirmed_utterance": "Twenty pieces of hex bolt"}
    before = stock_level(client)

    refused = client.post("/erp/goods-receipt", json=payload, headers=headers).json()
    retried = client.post("/erp/goods-receipt", json=payload, headers=headers).json()

    assert refused["posted"] is False
    assert retried["posted"] is False
    assert "draft" in retried["message"].lower()
    assert stock_level(client) == before


# --- a reversal of a document that scrolled out of the last ten -----------------

def test_a_document_older_than_the_last_ten_cannot_be_reversed_blind(client):
    # The reversal tool looks at the ten most recent documents, because that
    # is what the worker can plausibly mean by "that one". A document pushed
    # out of that window is refused with a sentence that sends the worker
    # back to the number, and nothing is written.
    first = post_receipt(client, quantity=1).json()
    assert first["posted"] is True
    for q in range(2, 12):                       # ten more, each a different quantity
        assert post_receipt(client, quantity=q).json()["posted"] is True
    before = stock_level(client)

    body = reverse_receipt(client, first["MBLNR"]).json()

    assert body["reversed"] is False
    assert "not among the recent postings" in body["message"]
    assert stock_level(client) == before


def test_the_tenth_most_recent_document_can_still_be_reversed(client):
    # The boundary from the other side, so the window is ten and not nine.
    docs = [post_receipt(client, quantity=q).json()["MBLNR"] for q in range(1, 11)]
    before = stock_level(client)

    body = reverse_receipt(client, docs[0]).json()

    assert body["reversed"] is True
    assert stock_level(client) == before - 1


def test_a_reversal_whose_answer_is_lost_does_not_reverse_twice(client, wire):
    receipt = post_receipt(client).json()
    wire.script = [only_posts("lose")]
    before = stock_level(client)

    first = reverse_receipt(client, receipt["MBLNR"]).json()
    assert first["reversed"] is False
    assert stock_level(client) == before - 20        # the reversal landed

    second = reverse_receipt(client, receipt["MBLNR"]).json()
    assert second["reversed"] is False
    assert "already reversed" in second["message"]
    assert stock_level(client) == before - 20        # and only once
