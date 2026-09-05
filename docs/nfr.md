# Non-functional requirements

What this system has to be true about itself, beyond working in a demo.

Targets were set before measuring. The **Measured** column is filled in during
tuning; an empty cell means unverified, not met.

---

## 1. Latency

The number the worker feels is the gap between finishing their sentence and hearing
the first syllable back. Everything below adds up inside that gap.

| Segment | Budget | Measured | Note |
|---|---|---|---|
| End of speech → turn detected | — | | Adaptive by default; owned by the platform |
| Transcription finalised | — | | Platform |
| LLM first token | — | | Platform |
| **Tool round trip (gateway)** | **≤ 150 ms p95** | | **Ours. The only segment we control** |
| First audio byte played | — | | Platform |
| **Total, read-only question** | **≤ 1500 ms p95** | | Target for the felt gap |
| **Total, write with hold** | **≤ 2500 ms p95** | | `execution_mode: "hold"` — agent waits |

The gateway is the only segment this project owns, so it is the only one with a hard
budget. SQLite reads are sub-millisecond; against a real OData service this segment
becomes the dominant risk and the budget will need revisiting.

**Design consequence:** tool timeouts are set at 10 s for reads and 20 s for the
write. Those are not targets — they are the point at which giving up beats leaving
the worker in silence.

## 2. Concurrency

| | Target | Note |
|---|---|---|
| Concurrent voice sessions | 1 (demo) · 10 (plausible small site) | Untested above 1 |
| Gateway requests/sec | ~2 per active session | Speech is slow; this is a low-throughput system |

**Known ceiling:** the mock uses SQLite with a single writer. Concurrent goods
receipts against the same material would serialise, and beyond a handful of writers
would start failing on lock contention. Acceptable for a mock; disqualifying for
production. A real ERP behind the gateway removes this entirely — the gateway itself
is stateless and scales horizontally.

**Not implemented:** rate limiting. A stateless gateway with an unbounded write
endpoint is a gap, mitigated only by the shared secret.

## 3. Availability and failure modes

| What fails | Worker experiences | Data risk | Handled |
|---|---|---|---|
| Gateway down | Agent apologises, cannot answer | None — no write happens | Yes, tool error surfaces to the model |
| Gateway slow (> timeout) | Agent reports it could not complete | **Yes — see below** | Partially |
| ERP rejects the write | Agent states the reason | None | Yes |
| AssemblyAI unavailable | No session at all | None | No fallback exists |
| Network drops mid-session | Session interrupted | None | `session.resume` exists; not implemented |
| Model calls the write tool without confirming | Stock changes unasked | **Yes** | Gateway validates inputs but cannot see whether a read-back happened |

**The unresolved one:** a write that times out is ambiguous. The gateway may have
posted the document and been too slow to say so. The agent reports failure, the
worker says it again, and stock is now double-counted. The fix is an idempotency key
per confirmed intent, rejected on replay. Not built. This is the most serious known
defect in the design and is recorded here rather than left for someone to find.

## 4. Security and data protection

| Concern | Position |
|---|---|
| ERP credentials | Never leave the gateway. The agent platform holds only a shared secret (ADR-0001) |
| API key exposure | Never reaches the browser; short-lived session tokens are minted server-side |
| Tool endpoint auth | Shared secret header, stored encrypted by the platform. **Single factor — a leaked secret is full write access** |
| Transport | HTTPS only; the platform refuses private and loopback hosts and does not follow redirects |
| Worker identity | **Not implemented.** Anyone who can reach the page can post stock. Production needs per-worker authorisation |
| Voice recordings | Sessions are retained by the platform. Under GDPR/KVKK a worker's voice is personal data: retention, purpose and consent are unresolved and would block a real deployment |
| Company data | No employer system is connected, by decision (ADR-0003) |

## 5. Cost

Structure first; rates from the provider's current pricing page.

```
per shift = (voice minutes × voice rate)
          + (LLM tokens × token rate)
          + gateway hosting (fixed, negligible at this scale)
```

The variable that matters is **voice minutes**, and the confirmation turn from
ADR-0002 adds to it on every posting. The trade-off is explicit: some seconds of
audio per receipt against the cost of one reversal.

Worth measuring before claiming a return on investment: mean session duration per
receipt, and receipts per shift. Both are unmeasured; no ROI figure should be quoted
until they are.

## 6. Accessibility and environment

| | Position |
|---|---|
| Noise | Voice focus / noise suppression enabled; tested against warehouse-floor audio |
| Interruption | Barge-in on; the client flushes queued agent audio on `input.speech.started` |
| Hands-free | Session start still needs a button press — the one non-hands-free moment |
| Accents and non-native speakers | Untested. A real warehouse floor is multilingual; this is a significant gap for the stated user |
| Turkish | Supported for input, not yet for speech output, so the agent cannot answer in Turkish today |
