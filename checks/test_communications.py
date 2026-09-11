"""Exercise real draft/record SQL against isolated SQLite, never the shared demo DB.

The adapter removes Postgres row locks; this verifies payload/consent/scope rules,
not PostgreSQL concurrency. Production uses the existing one-use draft row lock.
"""
import asyncio
import sqlite3
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest

from gateway import communications, confirmation, main, session_scope, store, voice_tools


@pytest.fixture
def isolated_store(monkeypatch):
    connection = sqlite3.connect(':memory:', check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript(confirmation.SCHEMA + communications.SCHEMA)
    class Adapter:
        def execute(self, sql, params=()):
            return connection.execute(sql.replace('%s', '?').replace(' FOR UPDATE', ''), params)
    @contextmanager
    def db():
        with connection:
            yield Adapter()
    monkeypatch.setattr(store, 'db', db)
    yield connection
    connection.close()


def confirmed(draft, **fields):
    return dict(fields, draft_token=draft['draft_token'], confirmed_utterance='Read back the full action.', user_confirmation='confirm')


def test_email_requires_exact_confirmed_draft_and_is_persisted_once(isolated_store):
    payload=dict(colleague_id='alex', subject='Short delivery', body='Twelve pieces arrived; twenty were expected.')
    draft=communications.prepare('a','email',payload)
    assert draft['details']['recipient']['email'].endswith('.example')
    assert communications.history('a')['records']==[]
    result=communications.commit('a','email',confirmed(draft,**payload))
    assert result['completed'] and result['simulated']
    assert result['record']['status']=='saved_to_demo_outbox'
    assert not communications.commit('a','email',confirmed(draft,**payload))['completed']
    assert len(communications.history('a')['records'])==1
    assert communications.history('b')['records']==[]


@pytest.mark.parametrize('change',[
    dict(colleague_id='jamie'),dict(subject='Changed'),dict(body='Different message'),
    dict(user_confirmation='yes but wait'),dict(confirmed_utterance=''),dict(draft_token='wrong'),
])
def test_changed_content_or_invalid_consent_cannot_write(isolated_store,change):
    payload=dict(colleague_id='alex',subject='Delivery',body='Check the delivery.')
    draft=communications.prepare('a','email',payload)
    assert not communications.commit('a','email',{**confirmed(draft,**payload),**change})['completed']
    assert communications.history('a')['records']==[]


def test_call_scope_expiry_and_cross_action_guards(isolated_store):
    payload=dict(colleague_id='alex',purpose='Short delivery')
    draft=communications.prepare('a','call',payload)
    assert not communications.commit('b','call',confirmed(draft,**payload))['completed']
    isolated_store.execute('UPDATE write_drafts SET expires_at=0')
    assert not communications.commit('a','call',confirmed(draft,**payload))['completed']
    fresh=communications.prepare('a','call',payload)
    assert not communications.commit('a','email',confirmed(fresh,colleague_id='alex',subject='Wrong action',body='No'))['completed']
    again=communications.prepare('a','call',payload)
    result=communications.commit('a','call',confirmed(again,**payload))
    assert result['record']['status']=='simulated_call_logged'
    assert 'nobody answered' in result['message']
    assert len(communications.history('a')['records'])==1


def test_note_replaces_email_draft_and_saves_without_contact(isolated_store):
    email=dict(colleague_id='alex',subject='Delivery',body='Twelve arrived.')
    old=communications.prepare('a','email',email)
    note=dict(title='Short delivery',body='Follow up on the missing eight pieces.')
    draft=communications.prepare('a','note',note)
    result=communications.commit('a','note',confirmed(draft,**note))
    assert result['record']['status']=='saved_to_demo_notes'
    assert not communications.commit('a','email',confirmed(old,**email))['completed']


def test_invalid_replacement_invalidates_old_and_directory_is_bounded(isolated_store):
    draft=communications.prepare('a','call',dict(colleague_id='alex'))
    assert not communications.prepare('a','call',dict(colleague_id='my-mom'))['prepared']
    assert not communications.commit('a','call',confirmed(draft,colleague_id='alex'))['completed']
    assert communications.find_colleague('warehouse supervisor')['matches'][0]['id']=='alex'
    assert communications.find_colleague('mom')['matches']==[]
    # A follow-up is routed by what was said, and a worker never reports to
    # their own role.
    assert communications.follow_up_recipient('Two bearings dropped and broke')[0]['id']=='sam'
    assert communications.follow_up_recipient('Only twelve of twenty arrived')[0]['id']=='dana'
    assert communications.follow_up_recipient('The paperwork is unclear')[0]['id']=='alex'
    assert communications.follow_up_recipient('A pallet broke','Maintenance technician')[0]['id']=='alex'


def test_browser_relay_routes_are_gated_and_suggestions_do_not_write(isolated_store):
    asyncio.run(browser_relay_check())


async def browser_relay_check():
    token=session_scope.issue(main.TOOL_SHARED_SECRET)
    headers={'X-Event-Scope':token,'X-Voice-Capability':voice_tools.capability(token,main.TOOL_SHARED_SECRET)}
    scope=session_scope.verify(token,main.TOOL_SHARED_SECRET)
    with patch.object(main.live,'inline_session_active',return_value=True):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            denied=await client.post('/api/voice-tools/place_call',json={'colleague_id':'alex'})
            assert denied.status_code==401
            suggested=await client.post('/api/voice-tools/suggest_follow_up',headers=headers,json={'reason':'The worker reports eight pieces missing.'})
            assert suggested.json()['suggested']
            assert communications.history(scope)['records']==[]
            found=await client.post('/api/voice-tools/find_colleague',headers=headers,json={'query':'Alex'})
            assert found.json()['matches'][0]['id']=='alex'
            prepared=await client.post('/api/voice-tools/prepare_email',headers=headers,json={'colleague_id':'alex','subject':'Short delivery','body':'Twelve arrived.'})
            draft=prepared.json()
            assert draft['prepared']
            sent=await client.post('/api/voice-tools/send_email',headers=headers,json=confirmed(draft,colleague_id='alex',subject='Short delivery',body='Twelve arrived.'))
            assert sent.json()['completed']
            history=await client.post('/api/voice-tools/get_communication_history',headers=headers,json={})
            assert history.json()['records'][0]['id']==sent.json()['record']['id']
    # A new read from storage, without any model/session object carrying the result.
    assert len(communications.history(scope)['records'])==1
