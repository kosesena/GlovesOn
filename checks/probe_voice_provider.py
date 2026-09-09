"""Opt-in paid protocol probe. No microphone, ERP calls, or database writes.

Run explicitly: .venv/bin/python checks/probe_voice_provider.py
Uses one short provider session to check current inline schemas, resumption and history.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from websockets.asyncio.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway.voice_tools import WRITE_TOOLS, inline_config


async def run():
    load_dotenv()
    key = os.environ['ASSEMBLYAI_API_KEY']
    template = json.loads(Path('agent/agent.json').read_text())
    config = inline_config(template, 'https://example.com')
    config['tools'] = [t for t in config['tools'] if t['name'] not in WRITE_TOOLS]
    config['greeting'] = 'Connection test.'
    result = {}
    async with httpx.AsyncClient(timeout=15) as client:
        async def token():
            response = await client.get('https://agents.assemblyai.com/v1/token',
                params={'expires_in_seconds': 60, 'max_session_duration_seconds': 60},
                headers={'Authorization': f'Bearer {key}'})
            response.raise_for_status()
            return response.json()['token']
        async def ready(ws):
            async with asyncio.timeout(20):
                async for raw in ws:
                    event = json.loads(raw)
                    if event['type'] == 'session.error':
                        raise RuntimeError(event.get('code', 'session.error'))
                    if event['type'] == 'session.ready':
                        return event
            raise RuntimeError('No session.ready')
        async with connect('wss://agents.assemblyai.com/v1/ws?token='+await token()) as ws:
            await ws.send(json.dumps({'type': 'session.update', 'session': config}))
            event = await ready(ws)
            session_id = event['session_id']
            resume_token = event.get('resume_token')
            result = {'session_id': session_id, 'inline_ready': True,
                      'input': event.get('config', {}).get('input', {}),
                      'resume_token_present': bool(event.get('resume_token'))}
            async with asyncio.timeout(15):
                async for raw in ws:
                    if json.loads(raw)['type'] == 'reply.done':
                        break
            ws.transport.abort()  # Emulate a network loss, not an intentional close handshake.
        try:
            async with connect('wss://agents.assemblyai.com/v1/ws?token='+await token()+'&resume_token='+quote(resume_token or '')) as ws:
                await ws.send(json.dumps({'type': 'session.resume', 'session_id': session_id, 'resume_token': resume_token}))
                event = await ready(ws)
                result['resumed_same_session'] = event['session_id'] == session_id
                await ws.send(json.dumps({'type': 'session.end'}))
                async with asyncio.timeout(10):
                    async for raw in ws:
                        if json.loads(raw)['type'] == 'session.ended':
                            result['ended_cleanly'] = True
                            break
        except Exception as error:
            result['resume_error'] = str(error)
        finally:
            response = await client.get(f'https://agents.assemblyai.com/v1/sessions/{session_id}',
                                        headers={'Authorization': key})
            result['history_http_status'] = response.status_code
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    asyncio.run(run())
