"""Offline feature contracts: no production database, microphone or provider requests."""
import json
import os
import unittest
from unittest.mock import patch

import httpx

os.environ.setdefault('TOOL_SHARED_SECRET', 'scope-test-secret')
from gateway import main, mm_knowledge, session_scope, voice_tools


class VoiceFeatureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.scope = session_scope.issue(main.TOOL_SHARED_SECRET)
        self.headers = {'X-Event-Scope': self.scope,
                        'X-Voice-Capability': voice_tools.capability(self.scope, main.TOOL_SHARED_SECRET)}

    def test_identifier_normalization_preserves_codes_and_leading_zeroes(self):
        data = {'material': ' 4 7 1 1 ', 'document': '49 00 00 00 01',
                'storage_location': '0 0 0 1', 'purchase_order': '0000001234',
                'plant': 'A-01', 'query': 'hydraulic hose'}
        result = voice_tools.normalize_arguments(data)
        self.assertEqual(result['material'], '4711')
        self.assertEqual(result['storage_location'], '0001')
        self.assertEqual(result['purchase_order'], '0000001234')
        self.assertEqual(result['plant'], 'A-01')
        self.assertEqual(result['query'], 'hydraulic hose')
        self.assertEqual(data['material'], ' 4 7 1 1 ')

    def test_knowledge_sources_and_unknown_questions(self):
        invoice = mm_knowledge.search('What does invoice verification mean?')
        self.assertTrue(invoice['found'])
        self.assertEqual(invoice['references'][0]['id'], 'invoice-verification')
        self.assertIn('help.sap.com', invoice['references'][0]['url'])
        self.assertFalse(mm_knowledge.search('Configure nuclear reactor controls')['found'])

    async def test_resume_and_binding_require_active_capability(self):
        with patch.object(main.live, 'inline_session_active', return_value=False):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as c:
                for path in ('bind', 'resume-token'):
                    for headers in ({}, self.headers):
                        r = await c.post('/api/voice-session/'+path, headers=headers, json={'session_id': 'sess_test'})
                        self.assertEqual(r.status_code, 401)

    async def test_binding_cannot_change_and_resume_is_bounded(self):
        with (patch.object(main.live, 'inline_session_active', return_value=True),
              patch.object(main, 'provider_belongs_to_scope', return_value=True),
              patch.object(main.live, 'bind_provider_session', return_value=False),
              patch.object(main.live, 'resume_provider_session', return_value=None)):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as c:
                r = await c.post('/api/voice-session/bind', headers=self.headers, json={'session_id': '../other'})
                self.assertEqual(r.status_code, 422)
                r = await c.post('/api/voice-session/bind', headers=self.headers, json={'session_id': 'sess_other'})
                self.assertEqual(r.status_code, 409)
                r = await c.post('/api/voice-session/resume-token', headers=self.headers)
                self.assertEqual(r.status_code, 409)

    async def test_foreign_provider_session_cannot_be_bound_to_a_new_scope(self):
        with (patch.object(main.live, 'inline_session_active', return_value=True),
              patch.object(main, 'provider_belongs_to_scope', return_value=False),
              patch.object(main.live, 'bind_provider_session') as bind):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as c:
                r = await c.post('/api/voice-session/bind', headers=self.headers, json={'session_id': 'sess_other'})
                self.assertEqual(r.status_code, 403)
                bind.assert_not_called()

    async def test_history_is_admin_only_and_excludes_resolved_secrets(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as c:
            r = await c.get('/api/voice-history/sess_other', headers=self.headers)
            self.assertEqual(r.status_code, 401)
        original = httpx.AsyncClient
        def factory(**kwargs):
            return original(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
                'id': 'sess_own', 'config': {'secret': 'must-not-leak'}, 'artifacts': [], 'status': 'completed'})), **kwargs)
        with patch.object(main.httpx, 'AsyncClient', factory):
            response = await main.voice_history('sess_own', main.TOOL_SHARED_SECRET)
            self.assertNotIn('must-not-leak', response.body.decode())
            self.assertEqual(json.loads(response.body)['id'], 'sess_own')
            self.assertEqual(response.headers['cache-control'], 'no-store')

    async def test_microphone_config_excludes_write_tools_and_credentials(self):
        original = httpx.AsyncClient
        def factory(**kwargs):
            return original(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'token': 'short-lived'})), **kwargs)
        with (patch.object(main.httpx, 'AsyncClient', factory),
              patch.object(main, 'ASSEMBLYAI_API_KEY', 'private-key'),
              patch.object(main.live, 'voice_budget_left', return_value=10),
              patch.object(main.live, 'mint_session'), patch.object(main.live, 'save_agent'),
              patch.object(main.live, 'agents_to_clean', return_value=[]),
              patch.object(main, 'env', return_value='https://example.com')):
            result = await main.voice_token(microphone='headset')
            self.assertEqual(result['session_config']['input']['voice_focus'], 'near-field')
            self.assertEqual(result['session_config']['input']['language_codes'], ['en'])
            self.assertFalse(voice_tools.WRITE_TOOLS & {t['name'] for t in result['session_config']['tools']})
            catalog = {tool['name'] for tool in result['tool_catalog']}
            self.assertTrue({'prepare_email', 'send_email', 'prepare_call', 'place_call',
                             'prepare_note', 'save_note', 'find_colleague', 'suggest_follow_up'} <= catalog)
            self.assertNotIn('private-key', json.dumps(result))
