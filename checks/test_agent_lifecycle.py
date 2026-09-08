"""Provider failures simulated over HTTP; no network, database or ERP writes."""
import unittest
from unittest.mock import patch

import httpx

from gateway import main, session_scope


class AgentLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_retains_failures_and_forgets_deleted_or_missing(self):
        rows = [{'scope': str(i), 'agent_id': str(i)} for i in range(4)]
        def respond(request):
            agent = request.url.path.rsplit('/', 1)[-1]
            if agent == '3':
                raise httpx.ReadTimeout('simulated timeout', request=request)
            return httpx.Response({'0': 204, '1': 404, '2': 503}[agent])
        with patch.object(main.live, 'agents_to_clean', return_value=rows), patch.object(main.live, 'forget_agent') as forget:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                self.assertFalse(await main.clean_scoped_agents(client))
            self.assertEqual({call.args[0] for call in forget.call_args_list}, {'0', '1'})

    async def test_cleanup_can_retry_retained_row(self):
        row = {'scope': 'retry', 'agent_id': 'temp'}
        statuses = iter([503, 204])
        with patch.object(main.live, 'agents_to_clean', return_value=[row]), patch.object(main.live, 'forget_agent') as forget:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(next(statuses)))) as client:
                self.assertFalse(await main.clean_scoped_agents(client, 'retry'))
                forget.assert_not_called()
                self.assertTrue(await main.clean_scoped_agents(client, 'retry'))
                forget.assert_called_once_with('retry')

    async def test_end_reports_pending_and_rejects_invalid_scope(self):
        token = session_scope.issue(main.TOOL_SHARED_SECRET)
        with patch.object(main, 'clean_scoped_agents', return_value=False) as clean:
            result = await main.close_voice_session({'scope_token': token})
            self.assertEqual(result, {'closed': False, 'cleanup_pending': True})
            self.assertEqual(clean.call_args.args[1], session_scope.verify(token, main.TOOL_SHARED_SECRET))
            with self.assertRaises(main.HTTPException) as denied:
                await main.close_voice_session({'scope_token': 'bad'})
            self.assertEqual(denied.exception.status_code, 401)
            self.assertEqual(clean.call_count, 1)

    async def test_failed_persistence_deletes_new_agent(self):
        requests = []
        def respond(request):
            requests.append((request.method, request.url.path))
            if request.url.path.endswith('/token'):
                return httpx.Response(200, json={'token': 'test'})
            if request.method == 'POST':
                return httpx.Response(201, json={'id': 'new-temp'})
            return httpx.Response(204)
        original_client = httpx.AsyncClient
        def factory(**kw):
            return original_client(transport=httpx.MockTransport(respond), **kw)
        with (patch.object(main.httpx, 'AsyncClient', factory),
              patch.object(main, 'ASSEMBLYAI_API_KEY', 'test'),
              patch.object(main.live, 'voice_budget_left', return_value=1),
              patch.object(main.live, 'mint_session'),
              patch.object(main.live, 'agents_to_clean', return_value=[]),
              patch.object(main.live, 'save_agent', side_effect=RuntimeError('DB unavailable')),
              patch.object(main.scoped_agent, 'build', return_value={}),
              self.assertRaisesRegex(RuntimeError, 'DB unavailable')):
            await main.voice_token()
        self.assertIn(('DELETE', '/v1/agents/new-temp'), requests)

    async def test_empty_cleanup_is_idempotent(self):
        with patch.object(main.live, 'agents_to_clean', return_value=[]):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: self.fail('Unexpected network request'))) as client:
                self.assertTrue(await main.clean_scoped_agents(client, 'already-cleaned'))


if __name__ == '__main__':
    unittest.main()
