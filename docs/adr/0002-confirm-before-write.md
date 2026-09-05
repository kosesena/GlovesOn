# 2. Writes require a spoken read-back and explicit confirmation

**Status:** Accepted · **Date:** 2026-09-05

## Context

Reads and writes are not symmetric. A wrong stock figure read aloud is corrected by
asking again. A wrong goods receipt is a posted material document, a wrong stock
level, and a reversal someone has to perform later.

Speech makes this worse than a form does. There is no field to re-read before
submitting, the worker is in a noisy warehouse, and "twenty" and "twelve" are one
misheard vowel apart.

## Options considered

**A. Post immediately, offer undo.** Fastest, and the pattern most voice assistants
use. But undo in an ERP is not undo — it is a reversal document, itself a posting.
And the worker has already walked away.

**B. Confirm every write.** Costs one conversational turn on every posting. In a
40-receipts-per-shift job, that is 40 extra turns.

**C. Confirm only above a threshold.** Cheap for small quantities. But the threshold
is arbitrary, and the failure it is meant to catch — a misheard number — is exactly
what makes the quantity look small or large in the first place.

## Decision

**B.** Before `post_goods_receipt` is called, the agent must read back four things in
one sentence — quantity, unit of measure, material *description* (not just the
number), and destination bin — and receive an unmistakable confirmation.

The material description is the load-bearing part. Reading back "twenty of 4711"
only confirms that the agent heard the digits the same way twice. Reading back
"twenty pieces of hex bolt M8" lets the worker catch that they are holding nuts.

`execution_mode: "hold"` is used on this tool so the agent waits for the ERP write
to complete rather than talking over it, and reports the resulting material document
number.

## Consequences

**Good**

- The failure this system could plausibly cause — silently wrong stock — needs two
  independent errors to happen, not one.
- The read-back doubles as the demo's most convincing moment.

**Bad**

- One extra turn per posting. Real cost in a high-volume shift; worth measuring
  against the cost of one reversal.
- The rule lives in a prompt, and prompts are probabilistic. Mitigated, not solved,
  by the gateway's own validation (ADR-0001). A deterministic mitigation — the
  gateway rejecting a posting that no read-back preceded — would close this properly
  and is not built.
- Ambiguous confirmations ("okay", "yeah, and also…") are a real failure mode. The
  prompt treats a bare "okay" mid-sentence as not a confirmation. This needs
  adversarial testing, not reasoning.

## Follow-up

Confirming before a write does not help when the write itself is ambiguous — a posting
that timed out may or may not have landed, and a worker who repeats the sentence would
double the stock. The gateway now refuses an identical posting inside a 120-second
window and hands the already-posted document back to the agent, which reads it out and
asks whether this is a second delivery. See `docs/nfr.md` for what that still does not
cover.
