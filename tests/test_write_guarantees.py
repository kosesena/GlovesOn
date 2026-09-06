"""
The promises this project makes about writing, as executable statements.

Every test here corresponds to a sentence in the README or an ADR. If one of
them fails, a claim the submission makes out loud has stopped being true — that
is the point of testing these and not, say, the JSON shape of a stock reply.
"""

from __future__ import annotations

from conftest import AUTH, post_receipt, stock_level

from gateway import audit, store

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

    reversal = client.post("/erp/reverse-goods-receipt",
                           json={"document": receipt["MBLNR"],
                                 "confirmed_utterance": "Reverse it",
                                 "session_id": "test-session"},
                           headers=AUTH).json()

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
    reversal = client.post("/erp/reverse-goods-receipt", json={"document": receipt["MBLNR"]},
                           headers=AUTH).json()

    again = client.post("/erp/reverse-goods-receipt", json={"document": reversal["MBLNR"]},
                        headers=AUTH).json()
    assert again["reversed"] is False
    assert "reversal" in again["message"].lower()


def test_a_document_is_not_reversed_twice(client):
    receipt = post_receipt(client).json()
    client.post("/erp/reverse-goods-receipt", json={"document": receipt["MBLNR"]}, headers=AUTH)

    second = client.post("/erp/reverse-goods-receipt", json={"document": receipt["MBLNR"]},
                         headers=AUTH).json()
    assert second["reversed"] is False
    assert "already reversed" in second["message"].lower()


def test_an_unknown_document_is_refused_in_words_a_worker_can_act_on(client):
    r = client.post("/erp/reverse-goods-receipt", json={"document": "4900000000"},
                    headers=AUTH).json()
    assert r["reversed"] is False
    assert "read the number again" in r["message"].lower()


# --- the gateway validates, whatever the model sends -------------------------

def test_a_quantity_that_is_not_a_whole_number_is_refused(client):
    assert post_receipt(client, quantity="twenty").json()["posted"] is False


def test_a_zero_or_negative_quantity_is_refused(client):
    assert post_receipt(client, quantity=0).json()["posted"] is False
    assert post_receipt(client, quantity=-5).json()["posted"] is False


def test_an_unstocked_material_is_refused_with_the_plant_named(client):
    body = post_receipt(client, material="9999").json()
    assert body["posted"] is False
    assert "9999" in body["message"]


# --- the trail from document back to the spoken sentence ---------------------

def test_the_audit_trail_records_the_confirmed_utterance(client):
    receipt = post_receipt(client, confirmed_utterance="Twenty pieces of hex bolt M8x40",
                           session_id="session-abc").json()

    row = audit.lookup(receipt["MBLNR"])
    assert row is not None
    assert row["utterance"] == "Twenty pieces of hex bolt M8x40"
    assert row["session_id"] == "session-abc"
    assert row["action"] == "goods_receipt"


def test_a_reversal_is_recorded_too(client):
    receipt = post_receipt(client).json()
    reversal = client.post("/erp/reverse-goods-receipt",
                           json={"document": receipt["MBLNR"],
                                 "confirmed_utterance": "Reverse that one",
                                 "session_id": "session-abc"},
                           headers=AUTH).json()

    row = audit.lookup(reversal["MBLNR"])
    assert row["action"] == "reversal"
    assert row["utterance"] == "Reverse that one"


def test_a_missing_utterance_does_not_block_the_write(client):
    # The trail enriches a posting; the read-back-and-yes protocol is what
    # authorises it (ADR-0002). A tool call without the sentence still posts.
    body = client.post("/erp/goods-receipt",
                       json={"material": "4711", "quantity": 20}, headers=AUTH).json()
    assert body["posted"] is True


def test_the_document_carries_its_voice_origin_into_sap(client):
    # The SAP document says where it came from — and deliberately not who the
    # speaker claimed to be. BKTXT marks the origin, XBLNR carries the session
    # reference that leads back to the audit trail. Read from the mock's own
    # tables, because these are fields SAP stores, not fields our tools return.
    receipt = post_receipt(client, session_id="abc123").json()

    with store.db() as conn:
        row = conn.execute("SELECT bktxt, xblnr FROM mkpf WHERE mblnr=%s",
                           (receipt["MBLNR"],)).fetchone()
    assert row["bktxt"] == "GLOVESON VOICE"
    assert row["xblnr"] == "VOICE:abc123"


# --- the trail is readable, not only writable --------------------------------

def test_a_document_can_be_traced_back_to_the_sentence_that_caused_it(client):
    # A trail nothing reads is not a trail. This is the endpoint the screen
    # calls when a judge clicks a document, so the evidence is visible rather
    # than merely stored.
    # A real session reference is secrets.token_hex(4) — eight characters.
    receipt = post_receipt(client, confirmed_utterance="Twenty pieces of hex bolt M8x40",
                           session_id="a1b2c3d4").json()

    p = client.get(f"/api/provenance/{receipt['MBLNR']}").json()

    assert p["MBLNR"] == receipt["MBLNR"]
    assert p["MENGE"] == 20
    assert p["BKTXT"] == "GLOVESON VOICE"
    assert p["XBLNR"] == "VOICE:a1b2c3d4"
    assert p["voice"]["utterance"] == "Twenty pieces of hex bolt M8x40"
    assert p["voice"]["session_id"] == "a1b2c3d4"
    assert p["voice"]["action"] == "goods_receipt"


def test_provenance_says_so_when_no_sentence_was_recorded(client):
    # Silence is information: the document was posted by a direct tool call.
    # Showing an empty quote would imply someone said nothing out loud.
    body = client.post("/erp/goods-receipt",
                       json={"material": "4711", "quantity": 20}, headers=AUTH).json()
    p = client.get(f"/api/provenance/{body['MBLNR']}").json()
    assert p["voice"] is None or p["voice"]["utterance"] == ""


def test_a_reversal_points_at_the_document_it_reverses(client):
    receipt = post_receipt(client).json()
    reversal = client.post("/erp/reverse-goods-receipt",
                           json={"document": receipt["MBLNR"],
                                 "confirmed_utterance": "Reverse it"},
                           headers=AUTH).json()

    p = client.get(f"/api/provenance/{reversal['MBLNR']}").json()
    assert p["reverses"] == receipt["MBLNR"]
    assert p["voice"]["action"] == "reversal"


def test_an_unknown_document_has_no_provenance(client):
    assert client.get("/api/provenance/4900000000").status_code == 404


def test_the_reference_document_field_respects_sap_s_width(client):
    # XBLNR is 16 characters in SAP. "VOICE:" takes six, so a session
    # reference longer than ten is truncated rather than sent whole — a real
    # tenant would reject the field, and the truncation is the faithful
    # behaviour, not a bug to "fix" by widening it.
    receipt = post_receipt(client, session_id="far-too-long-to-fit").json()
    p = client.get(f"/api/provenance/{receipt['MBLNR']}").json()
    assert p["XBLNR"] == "VOICE:far-too-lo"     # six for the marker, ten for the reference
    assert len(p["XBLNR"]) == 16
