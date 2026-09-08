"""One-use, scoped write drafts. Spoken consent is still reported by the agent."""
import hashlib
import json
import secrets
import time
from . import store

SCHEMA = '''
CREATE TABLE IF NOT EXISTS write_drafts (
    scope TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    operation TEXT NOT NULL,
    payload TEXT NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL,
    state TEXT NOT NULL
);
'''

def init():
    with store.schema_lock() as conn:
        conn.execute(SCHEMA)

def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def valid_response(value):
    return isinstance(value, str) and value.strip().lower().rstrip('.!') in {
        'confirm', 'yes', 'yes confirm', 'yes, confirm', 'i confirm', 'onaylıyorum', 'evet'}

def rejection(row, token, operation, payload, response, now):
    if not row or row['state'] != 'pending':
        return 'No active draft. Prepare and read back a new draft.'
    if row['expires_at'] <= now:
        return 'Draft expired. Prepare and read back a new draft.'
    if not isinstance(token, str) or not secrets.compare_digest(row['token_hash'], hashlib.sha256(token.encode()).hexdigest()):
        return 'Draft token does not match.'
    if row['operation'] != operation or row['payload'] != canonical(payload):
        return 'Details changed. Prepare and read back a new draft before confirmation.'
    if not valid_response(response):
        return 'An explicit confirmation is required; prepare and read back again.'
    return None

def prepare(scope, operation, payload):
    if not scope:
        raise ValueError('Start a private voice session before preparing a write.')
    token = secrets.token_urlsafe(24)
    with store.db() as conn:
        conn.execute('''INSERT INTO write_drafts VALUES (%s,%s,%s,%s,%s,'pending')
            ON CONFLICT (scope) DO UPDATE SET token_hash=EXCLUDED.token_hash,
            operation=EXCLUDED.operation,payload=EXCLUDED.payload,
            expires_at=EXCLUDED.expires_at,state='pending' ''',
            (scope, hashlib.sha256(token.encode()).hexdigest(), operation, canonical(payload), time.time()+120))
    return token

def consume(scope, token, operation, payload, response):
    if not scope:
        return 'A private voice session and prepared draft are required.'
    with store.db() as conn:
        row = conn.execute('SELECT * FROM write_drafts WHERE scope=%s FOR UPDATE', (scope,)).fetchone()
        error = rejection(row, token, operation, payload, response, time.time())
        if row and row['state'] == 'pending':
            conn.execute('UPDATE write_drafts SET state=%s WHERE scope=%s',
                         ('invalid' if error else 'consumed', scope))
    return error


def invalidate(scope):
    if scope:
        with store.db() as conn:
            conn.execute("UPDATE write_drafts SET state='invalid' WHERE scope=%s AND state='pending'", (scope,))
