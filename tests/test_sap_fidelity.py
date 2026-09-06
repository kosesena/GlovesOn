"""
The mock behaves like SAP, not like a convenient stub (ADR-0003).

The value of the mock is entirely in the rules it refuses to bend. If it
started accepting a four-digit material number, or a movement type that
disagrees with the goods-movement code, or a write without a CSRF token, then
"pointing SAP_BASE_URL at a real tenant is the whole migration" would stop
being true — and that sentence is the one the submission rests on.

These tests talk to the mock the way the gateway does: over HTTP, through its
own ASGI app, with the OData paths and the CSRF handshake.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gateway.main import mock_app
from gateway.store import norm_matnr, pretty_matnr

MATERIAL_DOC = "/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV"


@pytest.fixture()
def sap(client):                       # client resets the database
    # The mock lives in its own app, unreachable from the public one, so the
    # tests reach it the way the gateway does — through that app directly.
    with TestClient(mock_app, base_url="http://mock-s4hana.internal") as c:
        yield c


def csrf(sap) -> str:
    r = sap.get(f"{MATERIAL_DOC}/", headers={"X-CSRF-Token": "Fetch"})
    return r.headers["X-CSRF-Token"]


def item(**over):
    body = {"Material": "4711", "Plant": "1000", "StorageLocation": "0001",
            "GoodsMovementType": "501", "EntryUnit": "EA", "QuantityInEntryUnit": "20"}
    body.update(over)
    return body


# --- material numbers --------------------------------------------------------

def test_a_spoken_material_number_becomes_an_18_character_matnr():
    assert norm_matnr("4711") == "000000000000004711"
    assert norm_matnr(" 47-11 ") == "000000000000004711"
    assert norm_matnr(4711) == "000000000000004711"
    assert pretty_matnr("000000000000004711") == "4711"


def test_a_non_numeric_material_is_left_alone():
    # SAP allows alphanumeric material numbers; zero-padding one would corrupt it.
    assert norm_matnr("ABC-1") == "ABC1"


# --- the CSRF handshake a real S/4HANA demands -------------------------------

def test_a_write_without_a_csrf_token_is_refused(sap):
    r = sap.post(f"{MATERIAL_DOC}/A_MaterialDocumentHeader",
                 json={"GoodsMovementCode": "05", "to_MaterialDocumentItem": [item()]})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CSRF_TOKEN_INVALID"


def test_the_service_root_hands_out_a_token_that_works(sap):
    token = csrf(sap)
    assert token
    r = sap.post(f"{MATERIAL_DOC}/A_MaterialDocumentHeader",
                 headers={"X-CSRF-Token": token},
                 json={"GoodsMovementCode": "05", "to_MaterialDocumentItem": [item()]})
    assert r.status_code == 201


# --- SAP's own consistency rules --------------------------------------------

def test_a_movement_type_must_agree_with_the_goods_movement_code(sap):
    # 101 is a receipt against a purchase order (code 01); sending it with 05
    # is the mistake a real system refuses, so the mock refuses it too.
    r = sap.post(f"{MATERIAL_DOC}/A_MaterialDocumentHeader",
                 headers={"X-CSRF-Token": csrf(sap)},
                 json={"GoodsMovementCode": "05",
                       "to_MaterialDocumentItem": [item(GoodsMovementType="101")]})
    assert r.status_code >= 400
    assert r.json()["error"]["code"] == "GOODS_MOVEMENT_CODE_MISMATCH"


def test_an_unsupported_movement_type_is_refused(sap):
    r = sap.post(f"{MATERIAL_DOC}/A_MaterialDocumentHeader",
                 headers={"X-CSRF-Token": csrf(sap)},
                 json={"GoodsMovementCode": "05",
                       "to_MaterialDocumentItem": [item(GoodsMovementType="311")]})
    assert r.json()["error"]["code"] == "UNSUPPORTED_MOVEMENT_TYPE"


def test_a_material_not_maintained_in_the_plant_is_refused_with_sap_s_code(sap):
    r = sap.post(f"{MATERIAL_DOC}/A_MaterialDocumentHeader",
                 headers={"X-CSRF-Token": csrf(sap)},
                 json={"GoodsMovementCode": "05",
                       "to_MaterialDocumentItem": [item(Material="9999")]})
    assert r.json()["error"]["code"] == "M7_042"


def test_the_mock_accepts_the_same_receipt_twice(sap):
    # Deliberate, and the reason the duplicate guard lives in the gateway: a
    # real S/4HANA does not refuse a repeated goods receipt. If this test ever
    # fails, the mock has grown a protection that production does not have, and
    # the guard would be testing itself against a friendly system.
    body = {"GoodsMovementCode": "05", "to_MaterialDocumentItem": [item()]}
    token = csrf(sap)
    first = sap.post(f"{MATERIAL_DOC}/A_MaterialDocumentHeader",
                     headers={"X-CSRF-Token": token}, json=body)
    second = sap.post(f"{MATERIAL_DOC}/A_MaterialDocumentHeader",
                      headers={"X-CSRF-Token": token}, json=body)
    assert first.status_code == 201 and second.status_code == 201
    assert (first.json()["d"]["MaterialDocument"]
            != second.json()["d"]["MaterialDocument"])
