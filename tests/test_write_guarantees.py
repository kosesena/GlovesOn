"""
The promises this project makes about writing, as executable statements.

Every test here corresponds to a sentence in the README or an ADR. If one of
them fails, a claim the submission makes out loud has stopped being true — that
is the point of testing these and not, say, the JSON shape of a stock reply.
"""

from __future__ import annotations

import pytest
from conftest import AUTH, post_receipt, reverse_receipt, scope_of, scoped_headers, stock_level
from fastapi import HTTPException

from gateway import audit, sap_client, store
from gateway.main import require_tool_auth

# --- a write needs the secret ------------------------------------------------

def test_a_write_without_the_shared_secret_is_refused(client):
    r = client.post("/erp/goods-receipt", json={"material": "4711", "quantity": 20})
    assert r.status_code == 401


def test_a_wrong_secret_is_refused(client):
    r = client.post("/erp/goods-receipt", json={"material": "4711", "quantity": 20},
                    headers={"X-Tool-Secret": "not-the-secret"})
    assert r.status_code == 401


# --- a receipt posts, and stock moves ----------------------------------------

def test_a_goods_receipt_posts_a_document_and_raises_stock(client):
    before = stock_level(client)
    body = post_receipt(client, quantity=20).json()

    assert body["posted"] is True
    assert body["MBLNR"]
    assert body["BWART"] == "501"           # receipt without a purchase order
    assert body["new_stock_level"] == before + 20
    assert stock_level(client) == before + 20


def test_the_reply_names_the_description_not_only_the_number(client):
    # The read-back is what lets a worker catch that they are holding nuts, not
    # bolts. If the tool reply stopped carrying MAKTX, the agent could not say it.
    body = post_receipt(client).json()
    assert body["MAKTX"] == "Hex Bolt M8x40 Zinc Plated"
    assert body["LGPLA"] == "A-03-02"
    assert body["MEINS"] == "EA"


# --- the duplicate guard (ADR-0002) ------------------------------------------

def test_an_identical_repeat_is_refused_and_writes_nothing(client):
    first = post_receipt(client, quantity=20).json()
    after_first = stock_level(client)

    second = post_receipt(client, quantity=20).json()

    assert second["posted"] is False
    assert second["duplicate"] is True
    assert second["MBLNR"] == first["MBLNR"]        # points at the original
    assert stock_level(client) == after_first       # and stock did not move


def test_a_genuinely_separate_second_delivery_can_be_forced(client):
    first = post_receipt(client, quantity=20).json()
    second = post_receipt(client, quantity=20, allow_duplicate=True).json()

    assert second["posted"] is True
    assert second["MBLNR"] != first["MBLNR"]


def test_a_different_quantity_is_not_a_duplicate(client):
    post_receipt(client, quantity=20)
    other = post_receipt(client, quantity=21).json()
    assert other["posted"] is True


# --- nothing is deleted; it is reversed --------------------------------------

def test_a_reversal_posts_a_second_document_and_returns_the_stock(client):
    before = stock_level(client)
    receipt = post_receipt(client, quantity=20).json()

    reversal = reverse_receipt(client, receipt["MBLNR"],
                               confirmed_utterance="Reverse it").json()

    assert reversal["reversed"] is True
    assert reversal["BWART"] == "502"                    # the reverse of a 501
    assert reversal["reverses"] == receipt["MBLNR"]
    assert reversal["MBLNR"] != receipt["MBLNR"]
    assert stock_level(client) == before

    # Both documents stay. That is the whole point of reversing rather than deleting.
    docs = client.get("/erp/recent-documents", headers=AUTH).json()["documents"]
    numbers = {d["MBLNR"] for d in docs}
    assert receipt["MBLNR"] in numbers
    assert reversal["MBLNR"] in numbers


def test_a_reversal_cannot_itself_be_reversed(client):
    receipt = post_receipt(client).json()
    reversal = reverse_receipt(client, receipt["MBLNR"]).json()

    again = reverse_receipt(client, reversal["MBLNR"]).json()
    assert again["reversed"] is False
    assert "reversal" in again["message"].lower()


def test_a_document_is_not_reversed_twice(client):
    receipt = post_receipt(client).json()
    reverse_receipt(client, receipt["MBLNR"])

    second = reverse_receipt(client, receipt["MBLNR"]).json()
    assert second["reversed"] is False
    assert "already reversed" in second["message"].lower()


def test_an_unknown_document_is_refused_in_words_a_worker_can_act_on(client):
    r = reverse_receipt(client, "4900000000").json()
    assert r["reversed"] is False
    assert "read the number again" in r["message"].lower()


# --- the gateway validates, whatever the model sends -------------------------

def test_a_quantity_that_is_not_a_whole_number_is_refused(client):
    # Both shapes, because only the string was covered before and the number
    # was the one that got through: int(20.5) is 20, so a worker who heard
    # "twenty point five" read back had 20 posted — after the confirmation.
    assert post_receipt(client, quantity="twenty").json()["posted"] is False
    fractional = post_receipt(client, quantity=20.5).json()
    assert fractional["posted"] is False
    assert "whole number" in fractional["message"].lower()


def test_a_zero_or_negative_quantity_is_refused(client):
    assert post_receipt(client, quantity=0).json()["posted"] is False
    assert post_receipt(client, quantity=-5).json()["posted"] is False


def test_an_unstocked_material_is_refused_with_the_plant_named(client):
    body = post_receipt(client, material="9999").json()
    assert body["posted"] is False
    assert "9999" in body["message"]


# --- the trail from document back to the spoken sentence ---------------------

def test_the_audit_trail_records_the_confirmed_utterance(client):
    # The session reference is no longer a string the caller invents: it is
    # the scope the gateway verified on the request, the same identity that
    # signed the draft. The trail therefore links the document to a session
    # that provably existed, not to a claim.
    headers = scoped_headers()
    receipt = post_receipt(client, headers=headers,
                           confirmed_utterance="Twenty pieces of hex bolt M8x40").json()

    row = audit.lookup(receipt["MBLNR"])
    assert row is not None
    assert row["utterance"] == "Twenty pieces of hex bolt M8x40"
    assert row["session_id"] == scope_of(headers)
    assert row["action"] == "goods_receipt"


def test_a_reversal_is_recorded_too(client):
    receipt = post_receipt(client).json()
    reversal = reverse_receipt(client, receipt["MBLNR"],
                               confirmed_utterance="Reverse that one").json()

    row = audit.lookup(reversal["MBLNR"])
    assert row["action"] == "reversal"
    assert row["utterance"] == "Reverse that one"


def test_a_missing_utterance_now_blocks_the_write(client):
    # This guarantee flipped with the draft protocol, deliberately. The trail
    # used to merely enrich a posting; now the confirmed sentence is part of
    # what the gateway demands before consuming a draft, so a call without it
    # is refused and nothing reaches SAP (ADR-0002, revised).
    before = stock_level(client)
    body = post_receipt(client, confirmed_utterance=None).json()
    assert body["posted"] is False
    assert "confirmation" in body["message"].lower()
    assert stock_level(client) == before


def test_the_document_carries_its_voice_origin_into_sap(client):
    # The SAP document says where it came from — and deliberately not who the
    # speaker claimed to be. BKTXT marks the origin, XBLNR carries the session
    # reference that leads back to the audit trail. Read from the mock's own
    # tables, because these are fields SAP stores, not fields our tools return.
    headers = scoped_headers()
    receipt = post_receipt(client, headers=headers).json()

    with store.db() as conn:
        row = conn.execute("SELECT bktxt, xblnr FROM mkpf WHERE mblnr=%s",
                           (receipt["MBLNR"],)).fetchone()
    assert row["bktxt"] == "GLOVESON VOICE"
    # XBLNR is 16 chars in SAP; "VOICE:" leaves ten for the scope id.
    assert row["xblnr"] == "VOICE:" + scope_of(headers)[:10]


# --- the trail is readable, not only writable --------------------------------

def test_a_document_can_be_traced_back_to_the_sentence_that_caused_it(client):
    # A trail nothing reads is not a trail. This is the endpoint the screen
    # calls when a judge clicks a document, so the evidence is visible rather
    # than merely stored.
    headers = scoped_headers()
    sid = scope_of(headers)
    receipt = post_receipt(client, headers=headers,
                           confirmed_utterance="Twenty pieces of hex bolt M8x40").json()

    p = client.get(f"/api/provenance/{receipt['MBLNR']}").json()

    assert p["MBLNR"] == receipt["MBLNR"]
    assert p["MENGE"] == 20
    assert p["BKTXT"] == "GLOVESON VOICE"
    assert p["XBLNR"] == "VOICE:" + sid[:10]
    assert p["voice"]["utterance"] == "Twenty pieces of hex bolt M8x40"
    assert p["voice"]["session_id"] == sid
    assert p["voice"]["action"] == "goods_receipt"


def test_a_bare_call_without_a_draft_writes_nothing(client):
    # The state this test used to document — a posted document with no spoken
    # sentence — is no longer reachable through the API: a bare tool call,
    # valid input and all, dies on the missing draft before SAP is touched.
    # That unreachability IS the guarantee now.
    before = stock_level(client)
    body = post_receipt(client, drafted=False).json()
    assert body["posted"] is False
    assert "draft" in body["message"].lower()
    assert stock_level(client) == before


def test_a_reversal_points_at_the_document_it_reverses(client):
    receipt = post_receipt(client).json()
    reversal = reverse_receipt(client, receipt["MBLNR"],
                               confirmed_utterance="Reverse it").json()

    p = client.get(f"/api/provenance/{reversal['MBLNR']}").json()
    assert p["reverses"] == receipt["MBLNR"]
    assert p["voice"]["action"] == "reversal"


def test_an_unknown_document_has_no_provenance(client):
    assert client.get("/api/provenance/4900000000").status_code == 404


def test_the_reference_document_field_respects_sap_s_width():
    # XBLNR is 16 characters in SAP. "VOICE:" takes six, so a session
    # reference longer than ten is truncated rather than sent whole — a real
    # tenant would reject the field, and the truncation is the faithful
    # behaviour, not a bug to "fix" by widening it.
    # Asserted on the payload the gateway builds, not on what the mock stored:
    # the mock truncates to 16 itself, so reading it back would pass even if
    # the gateway stopped truncating — the test would be measuring the mock.
    payload = sap_client.goods_receipt_payload(
        "000000000000004711", 20, "1000", "0001", "EA", None,
        session_ref="far-too-long-to-fit")
    assert payload["ReferenceDocument"] == "VOICE:far-too-lo"
    assert len(payload["ReferenceDocument"]) == 16


def test_a_reversal_sends_the_original_quantity_not_a_placeholder(client):
    # The payload used to carry a hard-coded "1" and the mock quietly replaced
    # it with the original quantity, so nothing looked wrong here. A real
    # S/4HANA would have closed a twenty-piece receipt with one piece and left
    # nineteen behind. Assert on the payload, where the mock cannot help.
    payload = sap_client.reversal_payload(
        "000000000000004711", "1000", "0001", "EA", "4900000123", "501", quantity=20)
    item = payload["to_MaterialDocumentItem"][0]
    assert item["QuantityInEntryUnit"] == "20"
    assert item["GoodsMovementType"] == "502"


def test_a_non_ascii_secret_is_refused_rather_than_crashing():
    # hmac.compare_digest raises TypeError on a non-ASCII str; unhandled, a
    # wrong secret became a 500 instead of a 401 — closed either way, but
    # reporting the wrong thing. Tested at the function rather than over HTTP
    # because httpx refuses to build such a header, while a raw client can
    # send the bytes and Starlette decodes them to exactly this string.
    with pytest.raises(HTTPException) as e:
        require_tool_auth("gizli-şifre")
    assert e.value.status_code == 401
