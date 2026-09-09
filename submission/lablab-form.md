# lablab submission — form fields

Copy-paste into the lablab submission form. Every claim traces to a repo file;
nothing here says more than docs/market.md and docs/business-case.md support.

---

## Project title
GlovesOn — a voice agent that writes to SAP

## Short description  (one line)
A hands-free warehouse voice agent that posts real goods receipts into SAP —
spoken, read back for confirmation, and reversible, never deleted.

## Long description

**The moment.** A pallet lands on Lena's receiving dock. Both hands are under
the box, gloves on. That delivery has to become a material document in
SAP — until it does, the company does not know it owns the goods. Today that
means gloves off and a walk to a shared terminal, for every delivery.

**What GlovesOn does.** Lena says one sentence — *"Forty M8 bolts
arrived."* The agent looks the material up itself (bin, unit, description),
reads the whole posting back aloud — *"Forty pieces of hex bolt M8x40 into bin
A-03-02, confirm?"* — and only on an unmistakable yes **posts a material
document**: a numbered goods receipt through SAP's released OData API, against
a mock S/4HANA that speaks that contract exactly. Stock moves on screen in the
moment. Click the document afterwards and it tells you the sentence that caused
it, and the second it was confirmed. A wrong receipt is corrected by voice too —
with a reversal document, never a deletion, so both records stay.

**Why it is different.** Voice in warehouses is decades old, but every incumbent
voice-*guides planned work*: the WMS issues a task, the worker answers fixed
prompts. The unplanned pallet has no voice path. SAP's own assistant (Joule)
does this by chat and has voice on its roadmap for its top cloud tiers — proof
the problem is real.

Plenty of voice agents now stop and ask before they act. What is rarer is
finishing the job inside an ERP's own rules and leaving something behind that
survives the demo: an 18-character material number, movement type 101 or 501,
a duplicate guard that lives in our gateway *because real S/4HANA will accept
the same receipt twice without complaint*, and a correction that is a 102
against the 101 rather than a delete. Both documents stay, because that is what
a ledger is. Every one of those claims maps to a file, a test and a command in
the repo's judge guide.

**Built on AssemblyAI.** The Voice Agent API runs the whole loop — streaming
speech-to-text, LLM routing, voice output, turn-taking — with JSON-Schema HTTP
tool calling into a gateway that owns every SAP guardrail. A `transcription_prompt`
and 56 keyterms tune recognition to SAP material numbers and warehouse
vocabulary; both write tools run in `execution_mode: hold` so the agent waits
for the ERP instead of narrating an optimistic success.

**Staged on purpose.** The demo wraps the console in a small warehouse — a
lobby, a guide, guided tasks — because you cannot ship a receiving floor to a
judge. The scenery is the only fiction: underneath sit SAP's released OData
contract, numbered documents, reversals and one-use write drafts, and pointing
one environment variable at a real tenant takes the costume off.

**Honest about limits.** The ERP behind this is a **mock** — faithful to the
released OData contract, CSRF handshake and all, and one environment variable
away from a real tenant, but not proven against one. The posting is made by a
service user, not the worker, so SAP cannot yet say who did it. Noise
robustness is set up but unmeasured. The demo serves one session at a time.
Nobody is authenticated. These are written up in the repo, not hidden — the
judge guide ends with them.

**Check it in ninety seconds.** `/how-it-works` on the live site is a map of the
system where every box names the file it lives in, the rule it cannot break and
the command that proves it — and every figure on it is computed at request time,
so the diagram cannot claim more than exists. The same evidence is in the repo's
judge guide, and 32 of the 71 tests run with no database and no keys at all.

## Technology & category tags
AssemblyAI Voice Agent API · Speech-to-Text · Voice Agents · SAP · S/4HANA ·
OData · ERP · FastAPI · Python · Postgres · Enterprise · Logistics · Warehousing

## Links
- Application URL: https://gloveson.vercel.app
- How it works (claim → file → rule → test): https://gloveson.vercel.app/how-it-works
- GitHub repository: https://github.com/kosesena/GlovesOn  (make public before submitting)
- Demo platform: Vercel (serverless) + Neon Postgres
