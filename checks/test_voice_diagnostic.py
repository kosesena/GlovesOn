"""Diagnostics reveal response shape, never echoed tool credentials."""
import json
import os
import unittest
from unittest.mock import patch

import httpx

os.environ.setdefault('TOOL_SHARED_SECRET', 'scope-test-secret')
from gateway import main, voice_diagnostic


class VoiceDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorized_probe_uses_invalid_tool_credentials_and_tracks_cleanup(self):
        posted = []
        def respond(request):
            if request.url.path.endswith('/token'):
                return httpx.Response(200, json={'token': 'short-lived-test-token'})
            if request.method == 'POST':
                posted.append(json.loads(request.content))
                return httpx.Response(201, json={'id': 'diagnostic-agent'})
            return httpx.Response(200, json={'id': 'diagnostic-agent'})
        original_client = httpx.AsyncClient
        def client(**kwargs):
            return original_client(transport=httpx.MockTransport(respond), **kwargs)
        with (patch.object(main.httpx, 'AsyncClient', client),
              patch.object(main, 'ASSEMBLYAI_API_KEY', 'test-api-key'),
              patch.object(main, 'env', return_value='https://example.com'),
              patch.object(main.live, 'voice_budget_left', return_value=1),
              patch.object(main.live, 'mint_session'),
              patch.object(main.live, 'agents_to_clean', return_value=[]),
              patch.object(main.live, 'save_agent') as saved):
            result = await main.voice_token(diagnostic=True, x_tool_secret=main.TOOL_SHARED_SECRET)
        self.assertEqual(result['diagnostic']['server_lookup']['status'], 200)
        saved.assert_called_once()
        self.assertEqual(len(posted), 1)
        for tool in posted[0]['tools']:
            values = {h['name']: h['value'] for h in tool['http']['headers']}
            self.assertEqual(values['X-Tool-Secret'], 'invalid-diagnostic-secret')
            self.assertEqual(values['X-Event-Scope'], 'invalid-diagnostic-scope')

    async def test_diagnostic_requires_auth_before_any_network_or_budget(self):
        with patch.object(main.live, 'voice_budget_left') as budget:
            with self.assertRaises(main.HTTPException) as denied:
                await main.voice_token(diagnostic=True, x_tool_secret='incorrect')
            self.assertEqual(denied.exception.status_code, 401)
            budget.assert_not_called()

    async def test_only_safe_metadata_survives_echoed_body(self):
        body = {'id': 'agent-test', 'tools': [{'secret': 'must-not-leak'}],
                'system_prompt': 'private prompt', 'error': 'Bearer private-key'}
        response = httpx.Response(201, json=body, headers={'set-cookie': 'private-cookie'})
        summary = voice_diagnostic.response_summary(response, {'tools': body['tools']})
        encoded = json.dumps(summary)
        for secret in ('must-not-leak', 'private prompt', 'private-key', 'private-cookie'):
            self.assertNotIn(secret, encoded)
        self.assertEqual(summary['identifiers'], {'id': 'agent-test'})
        self.assertTrue(summary['echoed_fields_match']['tools'])

    async def test_non_json_body_is_not_returned(self):
        summary = voice_diagnostic.response_summary(httpx.Response(502, text='secret proxy response'))
        self.assertFalse(summary['json'])
        self.assertNotIn('secret proxy response', json.dumps(summary))
