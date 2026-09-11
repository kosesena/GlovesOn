"""A persistent, session-scoped demo outbox and call log. No external delivery."""
import json
import secrets
import time

from . import confirmation, store

COLLEAGUES = (
    {"id": "alex", "name": "Alex Morgan", "role": "Warehouse supervisor", "area": "Receiving bay",
     "email": "alex.morgan@gloveson.example", "extension": "201"},
    {"id": "jamie", "name": "Jamie Chen", "role": "Receiving operator", "area": "Receiving bay",
     "email": "jamie.chen@gloveson.example", "extension": "202"},
    {"id": "sam", "name": "Sam Patel", "role": "Maintenance technician", "area": "Storage aisles",
     "email": "sam.patel@gloveson.example", "extension": "203"},
    # A short delivery is answered off the floor, not on it: without somebody in
    # purchasing the shortage scenario ends at a name the directory does not have.
    {"id": "dana", "name": "Dana Ruiz", "role": "Purchasing officer", "area": "Purchasing office",
     "email": "dana.ruiz@gloveson.example", "extension": "204"},
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS demo_communications (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    readback TEXT NOT NULL,
    user_confirmation TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS demo_communications_scope ON demo_communications (scope, created_at);
"""


def init():
    with store.schema_lock() as conn:
        conn.execute(SCHEMA)


def directory():
    """Everyone who exists. A screen that cannot say who is reachable sends the
    worker guessing at names, and a name nobody has is a dead end in a demo."""
    return [dict(person) for person in COLLEAGUES]


# Who a follow-up belongs to. The words are matched against what the worker
# actually said, not against a category the agent invented, and a miss lands on
# the supervisor rather than on nobody. A wrong guess here costs a suggestion
# the worker declines; it can never cost a record, because every message still
# needs its own draft, read-back and spoken yes.
INCIDENT_WORDS = ('broke', 'broken', 'damag', 'dropped', 'crack', 'leak', 'faulty', 'torn', 'split', 'unsafe')
SUPPLY_WORDS = ('missing', 'short', 'fewer', 'shortage', 'wrong item', 'wrong material',
                'supplier', 'purchase order', 'not delivered', 'never arrived', 'overdelivered',
                # A count that does not match is rarely said with the word
                # "shortage": it is said as "only twelve", "instead of twenty".
                'only', 'instead of', 'not enough', 'less than', 'discrepanc', 'mismatch')


def follow_up_recipient(reason, worker_role=''):
    people = {person['id']: dict(person) for person in COLLEAGUES}
    text = (reason or '').lower()
    if any(word in text for word in INCIDENT_WORDS):
        person, because = people['sam'], 'damaged or broken goods go to maintenance'
    elif any(word in text for word in SUPPLY_WORDS):
        person, because = people['dana'], 'a delivery that does not match its order goes to purchasing'
    else:
        person, because = people['alex'], 'anything else goes to the shift supervisor'
    # Nobody is told to report to themselves: the maintenance technician who
    # reports the broken pallet escalates instead of calling their own extension.
    if worker_role and worker_role.strip().lower() == person['role'].lower() and person['id'] != 'alex':
        person, because = people['alex'], 'the worker holds that role, so it escalates to the supervisor'
    return person, because


def find_colleague(query):
    terms = query.lower().split()
    matches = [dict(person) for person in COLLEAGUES if all(
        term in ' '.join(person.values()).lower() for term in terms)]
    # A miss returns the whole directory rather than nothing, so the agent can
    # read the real options back instead of dead-ending on a name that does not
    # exist. matches stays exact: the list is offered, never selected from.
    return {"simulated": True, "matches": matches, "directory": directory(),
            "message": "Fictional demo directory. Choose the intended colleague; never guess when ambiguous."
            if matches else
            "No colleague matched. These are the only people in the fictional demo directory; ask which one is meant."}


def text_field(body, key, maximum, required=True):
    value = body.get(key, '')
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValueError(f"{key} must be text between {1 if required else 0} and {maximum} characters.")
    return value.strip()


def details_for(kind, body):
    if kind == 'note':
        return {"kind": kind, "simulated": True, "title": text_field(body, 'title', 160),
                "body": text_field(body, 'body', 3000)}
    person = next((person for person in COLLEAGUES if person['id'] == body.get('colleague_id')), None)
    if person is None:
        raise ValueError('Find and select a colleague from the demo directory first.')
    details = {"kind": kind, "recipient": dict(person), "simulated": True}
    if kind == 'email':
        details.update(subject=text_field(body, 'subject', 160), body=text_field(body, 'body', 3000))
    else:
        details['purpose'] = text_field(body, 'purpose', 500, required=False)
    return details


def prepare(scope, kind, body):
    if not scope:
        return {"prepared": False, "simulated": True, "message": "Start a private voice session first."}
    # Invalid replacement drafts must not leave a previous action executable.
    confirmation.invalidate(scope)
    try:
        details = details_for(kind, body)
    except ValueError as error:
        return {"prepared": False, "simulated": True, "message": str(error)}
    token = confirmation.prepare(scope, 'demo_' + kind, details)
    return {"prepared": True, "simulated": True, "draft_token": token,
            "details": details, "expires_in": 120,
            "message": "Read back the note, or recipient and email content/call purpose. Explain this is the demo. Wait for a fresh spoken confirm. Nothing saved, sent or called yet."}


def commit(scope, kind, body):
    try:
        details = details_for(kind, body)
        readback = text_field(body, 'confirmed_utterance', 5000)
        response = text_field(body, 'user_confirmation', 80)
    except ValueError as error:
        confirmation.invalidate(scope)
        return {"completed": False, "simulated": True, "message": str(error)}
    error = confirmation.consume(scope, body.get('draft_token'), 'demo_' + kind, details, response)
    if error:
        return {"completed": False, "simulated": True, "message": error}
    record = {"id": {'email': 'MAIL-', 'call': 'CALL-', 'note': 'NOTE-'}[kind] + secrets.token_hex(5).upper(),
              "kind": kind, "details": details, "created_at": time.time(),
              "status": {'email': 'saved_to_demo_outbox', 'call': 'simulated_call_logged', 'note': 'saved_to_demo_notes'}[kind]}
    # The token is consumed first. A failed/uncertain insert must be reconciled
    # with history, never retried blindly. A fresh process reads the same rows.
    with store.db() as conn:
        conn.execute('INSERT INTO demo_communications (id,scope,kind,payload,readback,user_confirmation,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                     (record['id'], scope, kind, json.dumps(record), readback, response, record['created_at']))
    return {"completed": True, "simulated": True, "record": record,
            "message": 'Saved to the demo outbox. No email was delivered.' if kind == 'email'
            else 'Saved to demo notes.' if kind == 'note'
            else 'Simulated call saved to the call log. No phone was dialled and nobody answered.'}


def history(scope):
    if not scope:
        return {"simulated": True, "records": [], "message": "Start a private voice session first."}
    with store.db() as conn:
        rows = conn.execute('SELECT payload FROM demo_communications WHERE scope=%s ORDER BY created_at DESC LIMIT 20', (scope,)).fetchall()
    return {"simulated": True, "records": [json.loads(row['payload']) for row in rows]}
