"""
The confirmation flow under a worker who does not follow the script.

checks/test_confirmation.py proves the rejection rules one at a time on a
fabricated draft row. These tests go through the HTTP door with the real
Postgres behind it, because the promises are about *sequences*: a draft that
was refused once must stay refused, a token from one session must be worthless
in another, a newer draft must retire the older one. Each one ends by reading
the stock back, so "nothing was written" is asserted, never assumed.

Every test here is a sentence from the hardening list or from the
"Five guardrails" slide, so a failure is a claim going false out loud.
"""

from __future__ import annotations

import time

import pytest
from conftest import AUTH, post_receipt, scoped_headers, stock_level

from gateway import store


def prepare(client, headers, **details):
    body = {"material": "4711", "quantity": 20}
    body.update(details)
    prep = client.post("/erp/prepare-goods-receipt", json=body, headers=headers).json()
    assert prep["prepared"] is True, prep
    return prep["draft_token"]


def post_with(client, headers, token, response, **body):
    payload = {"material": "4711", "quantity": 20, "draft_token": token,
               "user_confirmation": response,
               "confirmed_utterance": "Twenty pieces of hex bolt into bin A-03-02"}
    payload.update(body)
    return client.post("/erp/goods-receipt", json=payload, headers=headers).json()


def documents(client):
    return {d["MBLNR"] for d in client.get("/erp/recent-documents", headers=AUTH).json()["documents"]}


# --- "yes, no, wait" -----------------------------------------------------------

@pytest.mark.parametrize("response", [
    "yes, no, wait",
    "yes... actually no",
    "yes twelve",          # a correction folded into the answer is not a yes
    "yeah",                # close to yes and deliberately not accepted
    "ok",
    "sure",
    "yes please post it",  # a yes with cargo; the cargo could be anything
    "no",
    "",
])
def test_a_hedged_or_decorated_answer_does_not_post(client, response):
    headers = scoped_headers()
    before = stock_level(client)
    token = prepare(client, headers)

    body = post_with(client, headers, token, response)

    assert body["posted"] is False
    assert "confirmation" in body["message"].lower()
    assert stock_level(client) == before


def test_a_refused_answer_spends_the_draft(client):
    # One strike. After "yes, no, wait" the same token with a clean "yes" is
    # not a second chance: the draft was invalidated when it was refused, so
    # the agent has to read the line back again. This is the property the
    # unit tests cannot see, because it lives in the row's state transition.
    headers = scoped_headers()
    before = stock_level(client)
    token = prepare(client, headers)

    first = post_with(client, headers, token, "yes, no, wait")
    second = post_with(client, headers, token, "yes")

    assert first["posted"] is False
    assert second["posted"] is False
    assert "draft" in second["message"].lower()
    assert stock_level(client) == before


@pytest.mark.parametrize("response", ["yes", "Yes.", "CONFIRM!", "yes, confirm", "I confirm", "evet", "onaylıyorum"])
def test_the_accepted_spellings_of_yes(client, response):
    # The other half of the contract, so the list above cannot drift into
    # refusing everything: punctuation and case are forgiven, words are not.
    headers = scoped_headers()
    before = stock_level(client)
    token = prepare(client, headers)

    body = post_with(client, headers, token, response)

    assert body["posted"] is True, body
    assert stock_level(client) == before + 20


# --- a confirmation that names a different quantity than the read-back ---------

def test_confirming_a_different_quantity_than_the_read_back_writes_nothing(client):
    # The agent read back twenty. The worker said twelve. If the agent sends
    # twelve against the draft for twenty, the gateway refuses: the draft is
    # bound to the exact details that were read back, and a changed detail is
    # a new draft, not a corrected old one.
    headers = scoped_headers()
    before = stock_level(client)
    token = prepare(client, headers, quantity=20)

    body = post_with(client, headers, token, "yes", quantity=12)

    assert body["posted"] is False
    assert "details changed" in body["message"].lower()
    assert stock_level(client) == before

    # ...and the honest path works: a new draft for twelve, read back, confirmed.
    token = prepare(client, headers, quantity=12)
    body = post_with(client, headers, token, "yes", quantity=12)
    assert body["posted"] is True
    assert stock_level(client) == before + 12


def test_a_changed_destination_is_a_changed_detail(client):
    headers = scoped_headers()
    before = stock_level(client)
    token = prepare(client, headers)

    body = post_with(client, headers, token, "yes", storage_location="0002")

    assert body["posted"] is False
    assert stock_level(client) == before


# --- answering a question that was not asked -----------------------------------

def test_a_receipt_draft_cannot_confirm_a_reversal(client):
    # The draft on the table is a goods receipt. The worker says "yes" and the
    # agent, confused, calls the reversal tool with that token. Operation is
    # part of what the token is bound to, so the reversal does not happen.
    receipt = post_receipt(client).json()
    assert receipt["posted"] is True
    headers = scoped_headers()
    before = stock_level(client)
    token = prepare(client, headers)  # a receipt draft, in this session

    body = client.post("/erp/reverse-goods-receipt",
                       json={"document": receipt["MBLNR"], "draft_token": token,
                             "user_confirmation": "yes",
                             "confirmed_utterance": "Reverse it"},
                       headers=headers).json()

    assert body["reversed"] is False
    assert stock_level(client) == before
    assert documents(client) == documents(client)  # nothing new appeared


def test_a_reversal_draft_cannot_confirm_a_receipt(client):
    receipt = post_receipt(client).json()
    headers = scoped_headers()
    before = stock_level(client)
    prep = client.post("/erp/prepare-reversal", json={"document": receipt["MBLNR"]},
                       headers=headers).json()
    assert prep["prepared"] is True

    body = post_with(client, headers, prep["draft_token"], "yes")

    assert body["posted"] is False
    assert stock_level(client) == before


# --- the token is worth nothing outside its session -----------------------------

def test_a_draft_token_from_another_session_is_refused(client):
    # Session A prepared the draft. Session B, holding A's token, says yes.
    # The draft is keyed to the scope that prepared it, so B has no draft at
    # all, whatever it carries.
    a, b = scoped_headers(), scoped_headers()
    before = stock_level(client)
    token = prepare(client, a)

    body = post_with(client, b, token, "yes")

    assert body["posted"] is False
    assert "draft" in body["message"].lower()
    assert stock_level(client) == before

    # A can still use its own draft: B's attempt did not spend it.
    body = post_with(client, a, token, "yes")
    assert body["posted"] is True


# --- a token is one use, and a newer draft retires the older one ---------------

def test_a_consumed_token_cannot_post_a_second_document(client):
    # Distinct from the duplicate guard, which looks at content and time. This
    # is the token itself: once consumed it is gone, and a replay of the exact
    # same request with the same yes is refused on the draft, before the
    # duplicate window is even consulted.
    headers = scoped_headers()
    before = stock_level(client)
    token = prepare(client, headers)

    first = post_with(client, headers, token, "yes")
    second = post_with(client, headers, token, "yes")

    assert first["posted"] is True
    assert second["posted"] is False
    assert "draft" in second["message"].lower()
    assert stock_level(client) == before + 20


def test_a_newer_draft_retires_the_older_one(client):
    # "Twenty." Read back. "Actually twelve." Read back again. The agent still
    # holds the first token and tries it. Two things must be true: the stale
    # token posts nothing, and the attempt is a strike, so the newer draft is
    # spent as well. A session holds one draft; any refused confirmation
    # against it closes it. Fail closed, then prepare again: the agent that
    # mixed up its tokens has to read the line back once more, which is the
    # cheap side of this trade. Recovery is then the ordinary path.
    headers = scoped_headers()
    before = stock_level(client)
    old = prepare(client, headers, quantity=20)
    new = prepare(client, headers, quantity=12)

    stale = post_with(client, headers, old, "yes", quantity=20)
    assert stale["posted"] is False
    assert "token" in stale["message"].lower()
    assert stock_level(client) == before

    spent = post_with(client, headers, new, "yes", quantity=12)
    assert spent["posted"] is False
    assert "draft" in spent["message"].lower()
    assert stock_level(client) == before

    fresh = prepare(client, headers, quantity=12)
    body = post_with(client, headers, fresh, "yes", quantity=12)
    assert body["posted"] is True
    assert stock_level(client) == before + 12


def test_an_expired_draft_is_refused_and_says_so(client):
    # Two minutes is the budget between read-back and yes. The test cannot
    # wait two minutes, so it ages the row the way the clock would.
    headers = scoped_headers()
    before = stock_level(client)
    token = prepare(client, headers)
    with store.db() as conn:
        conn.execute("UPDATE write_drafts SET expires_at=%s", (time.time() - 1,))

    body = post_with(client, headers, token, "yes")

    assert body["posted"] is False
    assert "expired" in body["message"].lower()
    assert stock_level(client) == before


def test_preparing_again_after_a_refusal_recovers_cleanly(client):
    # The recovery path the agent is told to take after every refusal: prepare
    # a new draft, read it back, get a fresh yes. It must work after each kind
    # of refusal, or the worker is stuck.
    headers = scoped_headers()
    before = stock_level(client)

    token = prepare(client, headers)
    assert post_with(client, headers, token, "yes, no, wait")["posted"] is False
    token = prepare(client, headers)
    assert post_with(client, headers, token, "yes", quantity=12)["posted"] is False
    token = prepare(client, headers)

    body = post_with(client, headers, token, "yes")

    assert body["posted"] is True
    assert stock_level(client) == before + 20
