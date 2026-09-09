"""Voice connection and capability boundary, without external services or DB writes."""
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

os.environ.setdefault('TOOL_SHARED_SECRET', 'scope-test-secret')
from gateway import main, session_scope, voice_tools


class InlineVoiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.scope = session_scope.issue(main.TOOL_SHARED_SECRET)
        self.headers = {'X-Event-Scope': self.scope,
                        'X-Voice-Capability': voice_tools.capability(self.scope, main.TOOL_SHARED_SECRET)}

    async def test_config_contains_no_permanent_credentials_or_http_tools(self):
        template = json.loads((main.ROOT/'agent/agent.json').read_text())
        before = json.dumps(template)
        result = voice_tools.inline_config(template, 'https://example.com')
        self.assertEqual(before, json.dumps(template))
        self.assertNotIn('agent_id', result)
        self.assertEqual(result['system_prompt'], template['system_prompt'])
        self.assertEqual(result['output']['type'], 'audio')
        for tool in result['tools']:
            self.assertNotIn('http', tool)
            self.assertEqual(tool['type'], 'function')
        self.assertNotIn(main.TOOL_SHARED_SECRET, json.dumps(result))

    async def test_scope_only_forgery_cross_session_and_closed_are_rejected(self):
        other = session_scope.issue(main.TOOL_SHARED_SECRET)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as c:
            with patch.object(main.live, 'inline_session_active', return_value=False) as active:
                for headers in ({}, {'X-Event-Scope':self.scope},
                                {**self.headers,'X-Event-Scope':other}, self.headers):
                    response=await c.post('/api/voice-tools/get_stock',json={'material':'4711'},headers=headers)
                    self.assertEqual(response.status_code,401)
                self.assertEqual(active.call_count,1)

    async def test_allowlist_and_original_erp_validation_remain_in_force(self):
        fake=AsyncMock()
        fake.get_stock.return_value=[{'StorageLocation':'0001','MaterialBaseUnit':'PC','StorageBin':'A-03-02','MatlWrhsStkQtyInMatlBaseUnit':'240'}]
        fake.get_description.return_value={'ProductDescription':'Hex bolt'}
        with (patch.object(main.live,'inline_session_active',return_value=True),
              patch.object(main,'sap',return_value=fake),patch.object(main,'publish'),
              patch.object(main.confirmation,'consume',return_value='A fresh confirmed draft is required') as consume):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as c:
                denied=await c.post('/api/voice-tools/reset',json={},headers=self.headers)
                self.assertEqual(denied.status_code,404)
                missing=await c.post('/api/voice-tools/get_stock',json={},headers=self.headers)
                self.assertEqual(missing.status_code,422)
                result=await c.post('/api/voice-tools/post_goods_receipt',json={'material':'4711','quantity':20},headers=self.headers)
                self.assertEqual(result.status_code,200)
                self.assertFalse(result.json()['posted'])
                self.assertEqual(consume.call_args.args[0],session_scope.verify(self.scope,main.TOOL_SHARED_SECRET))
                fake.post_material_document.assert_not_called()

    async def test_inline_session_close_never_deletes_a_provider_agent(self):
        with (patch.object(main.live,'agents_to_clean',return_value=[{'scope':'s','agent_id':voice_tools.INLINE_AGENT}]),
              patch.object(main.live,'forget_agent') as forget):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:self.fail('Unexpected provider call'))) as c:
                self.assertTrue(await main.clean_scoped_agents(c,'s'))
                forget.assert_called_once_with('s')
