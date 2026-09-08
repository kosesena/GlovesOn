"""ASGI integration tests with an in-memory event bus; no DB lifespan or ERP calls."""
import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('TOOL_SHARED_SECRET', 'scope-test-secret')
import httpx

from gateway import main, session_scope


class ScopeRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_requests_and_streams_are_isolated(self):
        captured = []
        def record(kind, payload):
            captured.append((len(captured)+1, json.dumps({'type':kind,'data':payload})))
        async def probe():
            await asyncio.sleep(.002)
            main.publish('probe', {'ok':True})
            return {'ok':True}
        main.app.add_api_route('/_scope_test', probe)
        a = session_scope.issue(main.TOOL_SHARED_SECRET)
        b = session_scope.issue(main.TOOL_SHARED_SECRET)
        with patch.object(main.live, 'publish', record), patch.object(main.live, 'latest_id', side_effect=lambda:len(captured)), patch.object(main.live, 'since', side_effect=lambda cursor:[r for r in captured if r[0]>cursor]), patch.object(main, 'SSE_MAX_LIFETIME_SECONDS', .02), patch.object(main, 'EVENT_POLL_SECONDS', .001):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
                await asyncio.gather(client.get('/_scope_test',headers={'X-Event-Scope':a}),client.get('/_scope_test',headers={'X-Event-Scope':b}))
                ra, rb = await asyncio.gather(client.get('/events',params={'scope_token':a},headers={'Last-Event-ID':'0'}), client.get('/events',params={'scope_token':b},headers={'Last-Event-ID':'0'}))
                self.assertEqual(ra.status_code,200)
                self.assertEqual(rb.status_code,200)
                self.assertEqual(ra.text.count('data:'),1)
                self.assertEqual(rb.text.count('data:'),1)
                self.assertIn(session_scope.verify(a, main.TOOL_SHARED_SECRET),ra.text)
                self.assertNotIn(session_scope.verify(b, main.TOOL_SHARED_SECRET),ra.text)
                denied=await client.get('/events',params={'scope_token':'invalid'})
                self.assertEqual(denied.status_code,401)
                resumed=await client.get('/events',params={'scope_token':a},headers={'Last-Event-ID':'1'})
                # No event already delivered at id 1 can be replayed.
                self.assertNotIn('id: 1\n',resumed.text)

if __name__ == '__main__':
    unittest.main()
