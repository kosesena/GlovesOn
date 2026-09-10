"""
The credential a real SAP endpoint demands, and the mock never did.

No database and no network: these assert what the client puts on the wire, which
is the part that was silently missing while every test passed against a mock that
asks for nothing.
"""

import asyncio

import httpx

from gateway import sap_client


def test_no_key_configured_sends_no_credential_header():
    # The mock needs none, and sending an empty APIKey to it would be worse than
    # sending nothing: it looks like a credential that failed rather than absent.
    assert sap_client.credentials("") == {}
    assert sap_client.credentials(None) in ({}, {"APIKey": sap_client.SAP_API_KEY})


def test_a_configured_key_becomes_the_header_saps_gateway_asks_for():
    # Verbatim from the sandbox's own 401: "Failed to resolve API Key variable
    # request.header.apikey". Header names are case-insensitive on the wire.
    assert sap_client.credentials("abc123") == {"APIKey": "abc123"}


def test_the_credential_rides_on_the_session_so_the_csrf_fetch_carries_it():
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"X-CSRF-Token": "tok"}, json={"d": {}})

    client = sap_client.SapClient(base_url="https://sandbox.example/s4hanacloud",
                                  transport=httpx.MockTransport(record),
                                  api_key="secret-key")
    asyncio.run(client._fetch_csrf())
    asyncio.run(client.aclose())

    assert seen, "the CSRF fetch should have been sent"
    assert seen[0].headers.get("apikey") == "secret-key"
    # An unauthenticated fetch behind SAP's gateway never returns a token, and the
    # resulting SapError names CSRF rather than authentication. That misdiagnosis
    # is the reason this assertion exists.
    assert seen[0].headers.get("x-csrf-token") == "Fetch"


def test_a_client_without_a_key_sends_no_apikey_header_at_all():
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"X-CSRF-Token": "tok"}, json={"d": {}})

    client = sap_client.SapClient(base_url="https://mock.example",
                                  transport=httpx.MockTransport(record),
                                  api_key="")
    asyncio.run(client._fetch_csrf())
    asyncio.run(client.aclose())

    assert "apikey" not in {k.lower() for k in seen[0].headers}
