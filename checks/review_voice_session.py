"""Download an explicitly selected session's timeline for private local review.

Usage: .venv/bin/python checks/review_voice_session.py sess_ID --output /private/tmp/review.json
Uses the local provider key; never prints keys, resolved configuration or signed artifact URLs.
"""
import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session_id')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', args.session_id):
        parser.error('Invalid session identifier')
    load_dotenv()
    with httpx.Client(timeout=20) as client:
        response = client.get(f'https://agents.assemblyai.com/v1/sessions/{args.session_id}',
            headers={'Authorization': os.environ['ASSEMBLYAI_API_KEY']})
        if not response.is_success:
            raise SystemExit(f'Provider history unavailable: HTTP {response.status_code}')
        session = response.json()
        artifact = next((a for a in session.get('artifacts', []) if a['type']=='timeline'), None)
        if not artifact:
            raise SystemExit('No timeline yet; finish the conversation and try again later.')
        url = urlsplit(artifact['url'])
        if url.scheme != 'https' or url.username or url.password:
            raise SystemExit('Unexpected artifact URL')
        # No Authorization header follows the presigned URL to the storage provider.
        timeline = client.get(artifact['url'])
        if not timeline.is_success:
            raise SystemExit(f'Timeline download failed: HTTP {timeline.status_code}')
        data = timeline.json()
    def redact(value):
        if isinstance(value, dict):
            return {k: redact(v) for k, v in value.items() if not re.search(r'token|secret|capability|authorization', k, re.I)}
        if isinstance(value, list):
            return [redact(v) for v in value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, (dict, list)):
                    return redact(parsed)
            except ValueError:
                pass
        return value
    # Exclusive creation avoids overwriting an existing investigation.
    with args.output.open('x') as file:
        os.chmod(args.output, 0o600)
        json.dump(redact(data), file, indent=2)
    print(f'Private timeline saved to {args.output}; {len(data.get("turns", []))} turns.')


if __name__ == '__main__':
    main()
