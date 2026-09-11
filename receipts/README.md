# Receipts — what the system actually did, on the deployed address

`/erp/recent-documents` is empty until somebody talks to the demo, so a judge
who opens the deployment after a quiet week sees a system with no history of
ever having worked. These files are that history, kept in the repository: the
real request and the real response for every step of one run, recorded on
**11 September 2026** against **https://gloveson.vercel.app**.

Nothing here is written by hand. Re-record the whole set with:

```bash
.venv/bin/python -m checks.record_receipts --base https://gloveson.vercel.app
```

## The run

Material **4711**, Hex Bolt M8x40 Zinc Plated, bin A-03-02, plant 1000.

| # | Step | Outcome |
|---|---|---|
| 1 | Voice session opened | A scoped capability, valid for ten minutes |
| 2 | `get_stock` | 271 EA in bin A-03-02 |
| 3 | `prepare_goods_receipt` 40 | Draft only: *"Nothing recorded."* |
| 4 | Post **41** against the draft for **40** | **Refused** — *"Details changed."* |
| 5 | `prepare_goods_receipt` 40 | A new draft, because a correction invalidates the old one |
| 6 | Post 40, confirmed | **Material document 4922857164**, movement 501, stock 271 → 311 |
| 7 | `prepare_goods_receipt` 40 again | Draft prepared |
| 8 | Post the same 40 again, confirmed | **Refused** — the duplicate guard names 4922857164 |
| 9 | `/api/provenance/4922857164` | The sentence that caused the document, and the session it belonged to |
| 10 | `prepare_reversal` | Draft for the reversal |
| 11 | Reverse 4922857164, confirmed | **Material document 4914312408**, movement 502, stock 311 → 271. Both documents stay |
| 12 | `get_stock` | 271 EA, back where it started |
| 13 | Voice session closed | `closed: true` |

Step 4 is the one worth reading first. The read-back said forty; the
confirmation named forty-one; the write did not happen. Step 8 is the second:
real S/4HANA accepts the same goods receipt twice without complaint, and the
refusal comes from the gateway on purpose.

## Verify it yourself, without a secret

The provenance endpoint reads only and needs no credential:

```bash
curl -s https://gloveson.vercel.app/api/provenance/4922857164
```

If that returns 404, the demo database has been reset since this run. The row
goes with it; these files stay, which is the reason they exist.

## What this is not

**Nobody spoke.** The tool calls went through `/api/voice-tools/{tool}`, the
same door the browser uses, carrying a real per-session capability, so the
draft protocol, the route allow-list, the duplicate guard and the audit trail
are all the production ones. But the arguments came from
`checks/record_receipts.py`, not from a worker and an agent, and there was no
microphone and no AssemblyAI session. The confirmation text says exactly that,
in the audit trail itself:

> yes, confirm — typed by checks/record_receipts.py, no microphone and no
> spoken turn in this run

A receipt that implied a microphone nobody switched on would be worth less than
no receipt at all. When the spoken rehearsal is recorded, its receipts belong
next to these, and the difference between the two sets should stay visible.

**The ERP is a mock.** Faithful to the released OData contract — the CSRF
handshake, the 18-character material number, movement types 501 and 502 — and
one environment variable away from a real tenant, but not proven against one.
See [`docs/clean-core.md`](../docs/clean-core.md) for what that still lacks.

Session tokens, the capability and draft tokens are redacted in these files.
They are short-lived, and a receipt is a record, not a credential store.
