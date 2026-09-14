"""Alex token authorization and budget; no external requests or database."""
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from gateway import main


class AlexVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_confirmed_call(self):
        with patch.object(main, 'active_voice_scope', AsyncMock(return_value='scope')), patch.object(main.communications, 'history', return_value={'records': []}):
            with self.assertRaises(HTTPException) as error:
                await main.alex_voice_token(Mock())
            self.assertEqual(error.exception.status_code, 409)

    async def test_budget_and_voice(self):
        record = {'status': 'simulated_call_logged', 'details': {'recipient': {'id': 'alex'}}}
        with patch.object(main, 'active_voice_scope', AsyncMock(return_value='scope')), patch.object(main.communications, 'history', return_value={'records': [record]}), patch.object(main.live, 'voice_budget_left', return_value=0):
            with self.assertRaises(HTTPException) as error:
                await main.alex_voice_token(Mock())
            self.assertEqual(error.exception.status_code, 429)
        response = Mock(is_success=True)
        response.json.return_value = {'token': 'ephemeral'}
        client = AsyncMock()
        client.get.return_value = response
        with patch.object(main, 'active_voice_scope', AsyncMock(return_value='scope')), patch.object(main.communications, 'history', return_value={'records': [record]}), patch.object(main.live, 'voice_budget_left', return_value=1), patch.object(main.live, 'mint_session'), patch.object(main.httpx, 'AsyncClient') as factory:
            factory.return_value.__aenter__ = AsyncMock(return_value=client)
            factory.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await main.alex_voice_token(Mock())
            self.assertEqual(result, {'token': 'ephemeral', 'voice': 'james'})
            self.assertEqual(client.get.call_args.kwargs['params']['max_session_duration_seconds'], 180)
