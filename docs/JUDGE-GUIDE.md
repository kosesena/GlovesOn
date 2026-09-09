# Judge guide

Every claim this submission makes, and where to check it. File and line for
reading, a command for running, and — at the end — what this system does **not**
do, said before you find it.

**Live:** <https://gloveson.vercel.app> · no credentials, no sign-up, Chrome
· **CI:** [![CI](https://github.com/kosesena/GlovesOn/actions/workflows/ci.yml/badge.svg)](https://github.com/kosesena/GlovesOn/actions/workflows/ci.yml)

The first request of a session wakes a serverless function and a database
connection, so give the first sentence a couple of seconds. Everything after it
is warm.

---

## In sixty seconds, without speaking

The whole system is reachable over HTTP. `$S` is the shared tool secret — ask
for it, or run your own copy with one of your choosing.

```bash
# 1. it is alive, and it reaches its ERP in-process, not over the internet
curl -s https://gloveson.vercel.app/health

# 2. a stock question — quantity, unit, description and the bin, in one reply
curl -s -H "X-Tool-Secret: $S" \
  "https://gloveson.vercel.app/erp/stock?material=4711"

# 3. try to post a receipt the way a script would — and watch it refused
curl -s -X POST -H "X-Tool-Secret: $S" -H "Content-Type: application/json" \
  -d '{"material":"4711","quantity":20,
       "confirmed_utterance":"Twenty pieces of hex bolt M8x40 into bin A-03-02"}' \
  https://gloveson.vercel.app/erp/goods-receipt

# 4. so where do documents come from? the ones the voice demo has posted
curl -s -H "X-Tool-Secret: $S" https://gloveson.vercel.app/erp/recent-documents

# 5. why does that document exist? the sentence that caused it
curl -s https://gloveson.vercel.app/api/provenance/<MBLNR from step 4>
```

Step 3 is the one worth watching, and it is worth watching because it **fails**.
This guide used to post a document here; since the draft protocol it cannot:
a write is accepted only inside a verified voice session that first *prepared*
the exact details and then confirmed them, so the strongest thing a curl can
demonstrate is the refusal itself — valid input, correct secret, and still no
document. The full prepare→confirm dance, the duplicate refusal and the
reversal are all exercised end-to-end by the test suite below; the live posting
you can watch happen is the voice demo. (If step 4 returns an empty list,
nobody has spoken to the demo since its last reset — run one goods receipt by
voice and look again.)

---

## Claims, and where they are true

| Claim | Where it lives | How to check it |
|---|---|---|
| The agent never sees SAP; a gateway owns the write | [`gateway/main.py`](../gateway/main.py) tool endpoints · [`gateway/sap_client.py`](../gateway/sap_client.py) is the only file that speaks OData | [ADR-0001](adr/0001-gateway-between-agent-and-erp.md) |
| Every write is confirmed by a spoken read-back naming the material **description** | [`agent/agent.json`](../agent/agent.json) system prompt · the reply carries `MAKTX` ([`main.py`](../gateway/main.py) `post_goods_receipt`) | `test_the_reply_names_the_description_not_only_the_number` |
| A repeated receipt is refused, not posted twice | [`gateway/main.py`](../gateway/main.py) `_recent_identical`, `DUPLICATE_WINDOW_SECONDS = 120` | `test_an_identical_repeat_is_refused_and_writes_nothing` |
| The guard is ours, not the mock's | [`gateway/sap_mock.py`](../gateway/sap_mock.py) deliberately accepts repeats | `test_the_mock_accepts_the_same_receipt_twice` |
| Nothing is deleted; a wrong document is reversed | [`gateway/sap_client.py`](../gateway/sap_client.py) `reversal_payload` — 102 against 101, 502 against 501 | `test_a_reversal_posts_a_second_document_and_returns_the_stock` |
| A reversal cannot be reversed, and nothing is reversed twice | [`gateway/main.py`](../gateway/main.py) `reverse_goods_receipt` | `test_a_reversal_cannot_itself_be_reversed` · `test_a_document_is_not_reversed_twice` |
| It speaks SAP's real API, with the CSRF handshake | [`gateway/sap_client.py`](../gateway/sap_client.py) `_fetch_csrf` · [`sap_mock.py`](../gateway/sap_mock.py) refuses a write without a token | `test_a_write_without_a_csrf_token_is_refused` |
| Material numbers are 18-character MATNR | [`gateway/store.py`](../gateway/store.py) `norm_matnr` | `test_a_spoken_material_number_becomes_an_18_character_matnr` |
| Every document traces back to the sentence that caused it | [`gateway/audit.py`](../gateway/audit.py) · `/api/provenance/{mblnr}` · click any row in **Recent documents** | `test_a_document_can_be_traced_back_to_the_sentence_that_caused_it` |
| Swapping the mock for a real tenant is one environment variable | `SAP_BASE_URL` in [`gateway/sap_client.py`](../gateway/sap_client.py) — there is no second code path | [ADR-0003](adr/0003-mock-erp-behind-a-faithful-contract.md) |

Run the suite yourself:

```bash
pip install -r requirements.txt pytest
pytest checks/                               # 32 tests: no database, no keys, no setup
export TEST_DATABASE_URL=postgresql://…      # any empty Postgres; see below
pytest                                       # all 71
```

71 tests, in two suites. `checks/` (32) needs nothing at all: it exercises
the draft protocol itself — confirmation, one-use tokens, session scoping,
provider cleanup — against an in-memory app, so it is the part you can run
thirty seconds after cloning. `tests/` (39) needs a Postgres because the
mock's data lives in one
([ADR-0005](adr/0005-serverless-deployment-and-shared-state.md)) and because a
stubbed database would test none of what matters — the CSRF handshake, the
movement-type rules, the duplicate window. If you would rather not provide
one, the same suite runs on every push in
[CI](https://github.com/kosesena/GlovesOn/actions/workflows/ci.yml) against a
Postgres service container; the badge above is that run.

`conftest.py` refuses to run if `TEST_DATABASE_URL` equals `DATABASE_URL` —
every test drops and reseeds the schema.

---

## Where the reasoning is

Five decision records, each naming the options rejected and what the choice
costs — not a summary of what was built.

- [ADR-0001](adr/0001-gateway-between-agent-and-erp.md) — why a gateway between the agent and the ERP
- [ADR-0002](adr/0002-confirm-before-write.md) — why every write is confirmed out loud
- [ADR-0003](adr/0003-mock-erp-behind-a-faithful-contract.md) — why the mock is faithful rather than convenient
- [ADR-0004](adr/0004-browser-first-not-telephony.md) — why the browser came before telephony
- [ADR-0005](adr/0005-serverless-deployment-and-shared-state.md) — why the state left the process, and what that cost

Also: [`nfr.md`](nfr.md) latency, concurrency, failure modes, security posture,
cost · [`clean-core.md`](clean-core.md) where this complies with SAP Clean Core
and, at greater length, where it does not · [`market.md`](market.md) the
competitive landscape, fact-checked, including the claims we may **not** make.

---

## What this is not

Said here rather than left for you to find.

**Nobody is authenticated.** The deployed page is a public voice terminal:
anyone who finds the URL can speak to the agent and cause a real posting. The
spoken read-back is a **mistake** control — it stops a worker posting the wrong
document — and never an **authorisation** control. Acceptable only because the
ERP behind it is a mock.

**SAP cannot say who did it.** The posting is made by a service user, not by the
worker. Closing that needs principal propagation through SAP BTP; it is the
largest gap in [`clean-core.md`](clean-core.md) and it is not implemented.

**The ERP is a mock.** The contract is faithful and the protocol is real, but no
claim is made that this has been proven against a live tenant. The gap between
"speaks the API correctly" and "works against S/4HANA" is real: CSRF behaviour
behind a reverse proxy, `$batch` for multi-item documents, and error payloads
considerably less tidy than a mock's.

**Untested with real accents and real noise.** `turn_detection` is pinned at
`min_silence: 800` / `max_silence: 2000` because adaptive pacing cut a
non-native speaker off mid-sentence — a first attempt, not a measurement. Noise
robustness is listed as untested in [`nfr.md`](nfr.md) and no claim is made
about it. Incumbent voice systems beat this on both counts; see
[`market.md`](market.md) §5 for what they do better.

**One process, one session.** The duplicate guard reads documents back from SAP
so it does not depend on process memory, but two people speaking at once would
share a voice-session reference. Demo scale, and stated as such.
