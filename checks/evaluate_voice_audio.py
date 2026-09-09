"""Opt-in paid recognition evaluation; captures tool intent but NEVER executes tools.

Input: mono PCM16 WAV at 24 kHz. Example:
.venv/bin/python checks/evaluate_voice_audio.py sample.wav --expect-tool get_stock --expect-material 4711
Use voice_cases.json for human recordings. Synthetic samples are not warehouse validation.
"""
import argparse
import asyncio
import base64
import json
import os
import sys
import wave
from pathlib import Path

import httpx
from dotenv import load_dotenv
from websockets.asyncio.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway.voice_tools import WRITE_TOOLS, inline_config, normalize_arguments


async def evaluate(args):
    with wave.open(str(args.wav), 'rb') as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 24000):
            raise SystemExit('Expected mono PCM16 WAV at 24 kHz.')
        pcm = audio.readframes(audio.getnframes())
    if not pcm or len(pcm) > 48000*45:
        raise SystemExit('Provide a nonempty sample under 45 seconds.')
    load_dotenv()
    config = inline_config(json.loads(Path('agent/agent.json').read_text()), 'https://example.com')
    config['tools'] = [t for t in config['tools'] if t['name'] not in WRITE_TOOLS]
    config['greeting'] = 'Ready.'
    observations = {'user': [], 'agent': [], 'tool_calls': [], 'erp_calls_executed': 0}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get('https://agents.assemblyai.com/v1/token',
            headers={'Authorization': 'Bearer '+os.environ['ASSEMBLYAI_API_KEY']},
            params={'expires_in_seconds': 60, 'max_session_duration_seconds': 90})
        response.raise_for_status()
        token = response.json()['token']
    async with connect('wss://agents.assemblyai.com/v1/ws?token='+token) as ws:
        await ws.send(json.dumps({'type': 'session.update', 'session': config}))
        async def speak():
            # Silence at the end allows the provider to complete the utterance.
            samples = pcm + bytes(48000*4)
            for pos in range(0, len(samples), 2400):
                await ws.send(json.dumps({'type': 'input.audio', 'audio': base64.b64encode(samples[pos:pos+2400]).decode()}))
                await asyncio.sleep(.05)
        sender = None
        try:
            async with asyncio.timeout(70):
                async for raw in ws:
                    event = json.loads(raw)
                    kind = event['type']
                    if kind == 'session.ready':
                        observations['session_id'] = event['session_id']
                    elif kind == 'session.error':
                        raise RuntimeError(event.get('code', 'session.error'))
                    elif kind == 'reply.done' and sender is None:
                        sender = asyncio.create_task(speak())
                    elif kind == 'transcript.user':
                        observations['user'].append(event.get('text', ''))
                    elif kind == 'transcript.agent':
                        observations['agent'].append(event.get('text', ''))
                    elif kind == 'tool.call':
                        observations['tool_calls'].append({'name': event['name'], 'arguments': normalize_arguments(event.get('arguments', {}))})
                        break
        except TimeoutError:
            observations['error'] = 'No tool intent within the evaluation window'
        finally:
            if sender:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
            await ws.send(json.dumps({'type': 'session.end'}))
    matched = any(call['name'] == args.expect_tool and (not args.expect_material or
                  call['arguments'].get('material') == args.expect_material)
                  for call in observations['tool_calls'])
    observations['passed'] = matched
    print(json.dumps(observations, indent=2))
    if not matched:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wav', type=Path)
    parser.add_argument('--expect-tool', required=True)
    parser.add_argument('--expect-material')
    asyncio.run(evaluate(parser.parse_args()))
