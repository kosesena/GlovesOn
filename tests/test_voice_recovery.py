"""Recovery persistence and normalized lookup against the isolated test database."""
import secrets
import time

from gateway import live, main, session_scope, voice_tools


def test_recovery_binding_is_immutable_bounded_and_scoped(client):
    a, b = secrets.token_hex(12), secrets.token_hex(12)
    live.save_agent(a, voice_tools.INLINE_AGENT, time.time()+300)
    live.save_agent(b, voice_tools.INLINE_AGENT, time.time()+300)
    assert live.bind_provider_session(a, 'sess_a')
    assert not live.bind_provider_session(a, 'sess_other')
    assert live.bind_provider_session(b, 'sess_b')
    for _ in range(5):
        assert live.resume_provider_session(a) == 'sess_a'
    assert live.resume_provider_session(a) is None
    assert live.resume_provider_session(b) == 'sess_b'
    live.forget_agent(a)
    assert not live.inline_session_active(a)
    assert live.inline_session_active(b)


def test_spoken_identifier_reaches_the_actual_stock_route(client):
    token = session_scope.issue(main.TOOL_SHARED_SECRET)
    scope = session_scope.verify(token, main.TOOL_SHARED_SECRET)
    live.save_agent(scope, voice_tools.INLINE_AGENT, time.time()+300)
    headers = {'X-Event-Scope': token,
               'X-Voice-Capability': voice_tools.capability(token, main.TOOL_SHARED_SECRET)}
    response = client.post('/api/voice-tools/get_stock',
                           headers=headers, json={'material': '4 7 1 1', 'plant': '1 0 0 0'})
    assert response.status_code == 200
    assert response.json()['found']
    assert response.json()['MATNR'] == '4711'
    live.forget_agent(scope)
    assert client.post('/api/voice-tools/get_stock', headers=headers,
                       json={'material': '4711'}).status_code == 401
