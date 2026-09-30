# Voice reliability and MM references

Implemented on 9 September 2026. All conversation and source content is English.

## User experience

The agent retains its Eve voice and welcome. The transcription context is concise,
uses specialized warehouse terms, and is restricted to English. Tool schemas include
identifier examples, including spoken numeric sequences containing spaces. The gateway
joins numeric whitespace while preserving leading zeroes and alphanumeric codes.
Purchase-order and document hints expect the ten-digit identifiers in this integration;
material identifiers are not restricted to the four-digit demo catalog.

Records & help contains a laptop/headset selector. It selects far-field or near-field
Voice Focus for the next conversation. The listening mode remains `max_accuracy`.
Noise suppression and patience existed before this change; no unmeasured accuracy
improvement is claimed.

The initial voice configuration exposes lookup, knowledge and preparation tools.
Receipt/reversal writes become available only after their matching draft succeeds.
Corrections, expiry and dispatch remove that availability. The gateway's existing
one-use draft and confirmation checks remain authoritative; browser tool visibility
does not authenticate spoken consent. An uncertain write blocks further preparations
and writes for the remainder of that conversation while keeping record lookups open.

Relevant material identifiers and descriptions returned by lookup tools augment the
next recognition context. Arbitrary result text never becomes a system instruction.
Long hold-mode operations may trigger one short pending-status sentence after 4.5
seconds, only at an eligible reply boundary. A status sentence cannot claim success.

## MM knowledge

`search_mm_knowledge` searches four reviewed references: the demo's receiving procedure,
invoice verification, receipt reversal, and the limits of the stock tool. Results
include source URLs, review dates and applicability. The conversation shows source
links. Unknown topics return no match; the agent must acknowledge that limit.

These are curated explanations, not model training, a live SAP knowledge service,
tenant configuration advice or additional transaction authority. The ERP remains mock
S/4HANA. Invoice and purchasing changes are not executable tools.

## Session recovery and diagnostics

The browser retains its existing scope, queued outcomes and handled call IDs during a
short transport interruption. It requests a fresh token and attempts `session.resume`
within a 25-second local deadline. Duplicate call IDs reuse the captured outcome; they
never dispatch another ERP request. Intentional ending still sends `session.end` and
revokes the scope. Recovery does not automatically restart a failed session or replay
a write. Expired or rejected recovery tells the worker to check recent receipts.

Binding a provider session requires both the active scope capability and a matching
server-generated correlation reference in the provider's resolved configuration.
A supplied session ID alone cannot authorize a different conversation. Recovery token
minting is bounded to five attempts within the original five-minute session window.
The additive `voice_links` table retains correlation for at most one day, cleaned on
binding; it is not an independent audit ledger. No warehouse data migration/reset is
required.

**Provider limitation:** live inline configuration and session-history retrieval
succeeded. The documented resumption request returned `session_not_found`, including
after an abrupt transport loss. Adding the returned resume token to the message and
URL did not resolve it. The production browser uses the documented request and stops
safely if it is rejected. Native context resumption is therefore **implemented but not
verified working with this provider account**. Do not present it as a successful demo
feature until the opt-in probe passes. This is separate from the older stored-agent
lookup issue; neither is asserted to have the same root cause.

Records & help can download local session notes containing text and tool outcomes,
without audio or credentials. Notes may contain business data and remain a user's
explicit download. `/api/voice-history/{id}` requires the permanent administrator tool
secret and excludes resolved configuration. It is not available to anonymous clients
or ordinary voice capabilities. Provider artifact links remain private and expire.

To retrieve a selected session's timeline locally:

```sh
.venv/bin/python checks/review_voice_session.py sess_ID --output /private/tmp/voice-review.json
```

The command uses the local provider key, creates a private file without overwriting
an existing one, and removes credential fields from nested tool results. The provider
stores its own audio; this implementation does not automatically download or replay it.

## Local evaluation without Bluejay

```sh
.venv/bin/python checks/run_voice_checks.py
```

This runs actual browser session/policy code in a fake-transport harness and offline
gateway contract tests. Offline tests fail immediately on an unmocked database access.
CI also runs the browser checks. These are protocol/logic tests, not speech benchmarks.

`checks/voice_cases.json` contains ten English caller scenarios with expected outcomes:
pauses, paired numbers, correction, refusal, incomplete/unknown identifiers, explanations,
ambiguous consent and connection loss during a write. Expected answers must never be
fed to the agent as conversation context.

For an explicit paid recognition test, provide a nonempty mono PCM16 24 kHz WAV:

```sh
.venv/bin/python checks/evaluate_voice_audio.py sample.wav --expect-tool get_stock --expect-material 4711
```

The runner streams recorded audio to the actual provider and checks the first tool
intent. It **never executes tools**, so it cannot validate successful writes. It uses
neither a microphone nor a database and limits sample/session duration. A synthetic
English stock-query sample was recognized as material 4711 and selected `get_stock`.
This is a smoke check, not evidence of noise robustness or a measured improvement.

The paid protocol probe tests inline configuration, resumption, and history:

```sh
.venv/bin/python checks/probe_voice_provider.py
```

The full ERP suite requires the separately configured `TEST_DATABASE_URL`. Never
point it at the demonstration database: it resets its own test schema. Bluejay account
integration is intentionally not activated; it stays local until an account exists.

## Scope decisions

Turkish support is excluded by request. Custom LLM migration, telephony, PII processing
and automatic summaries were deferred options in the research, not dependencies of
these improvements. They are not silently enabled or represented as completed.

References: [AssemblyAI tools](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/tools/overview),
[transcription context](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/transcription-prompt),
[Voice Focus](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/noise-suppression),
[events](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/events-reference),
[history](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/session-history).
