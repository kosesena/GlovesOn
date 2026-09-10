# lablab submission — draft form fields

Updated 10 September 2026. This is draft copy, not a submitted entry. Complete
the live voice demonstration and verify the deployed revision before submission.
The repository stays private for now at the user's request.

## Project title

GlovesOn — hands-free warehouse work with AssemblyAI

## Short description

A warehouse voice agent that turns spoken requests into confirmed mock SAP
records, with visible results and simulated colleague follow-up.

## Long description

**The problem.** A warehouse operator has gloves on and a delivery to handle.
Looking up materials, recording a receipt and reporting an exception can each
interrupt the physical job. GlovesOn explores how much of that work can be
completed through a conversation.

**The workflow.** Ask for a material by name or number. The agent retrieves its
description, unit and bin, prepares a goods receipt and reads the details back.
Correct the quantity if needed, then explicitly confirm. A successful tool call
creates a numbered document and updates stock in the mock ERP. A wrong receipt
can be reversed; the original and reversal both remain in the record.

**Visible work.** Conversation stays on the left. On the right, tool requests and
results appear as an ERP page, Lena's work phone or her email/notes screen. When
the worker reports a shortage or damage, the agent can suggest a supervisor
call, an email or an incident note. These are explicitly simulated: calls save
logs, emails save to a demo outbox, and nobody is contacted. Each save requires
a separate read-back and fresh confirmation.

**Built on AssemblyAI.** Its Voice Agent API provides the streaming speech,
language-model conversation and voice output loop. Domain keyterms and
transcription instructions help convey warehouse vocabulary. Function calls
return to the browser and travel through a scoped capability to the gateway.
Write tools become available after preparation; the server binds a one-use,
expiring draft to the exact action and payload. Corrections require a new draft.
The workspace only marks an operation saved after its tool reports success.

**The focus.** GlovesOn connects unplanned warehouse requests, spoken corrections,
reversible records and exception follow-up in one workflow. Voice warehousing,
ERP assistants and confirmation are established ideas; our contribution is this
specific interaction and its inspectable execution boundary.

**Limits.** SAP is a mock reached through an S/4HANA-style OData contract; real
S/4HANA integration is unverified. Phone and email delivery are simulations.
Damage reports do not quarantine, scrap or adjust stock. Session scoping is not
employee authentication, and server checks do not independently prove spoken
consent. New communication flows need final live microphone validation; noise
robustness, productivity savings and production suitability are not established.

The repository includes gateway checks, browser lifecycle and result-state
checks, architecture decisions and a judge guide. Exact evidence and outstanding
delivery work are listed in `docs/agent-workspace.md` and
`docs/hackathon-readiness.md`.

## Technology & category tags

AssemblyAI Voice Agent API · Speech-to-Text · Voice Agents · SAP · S/4HANA ·
OData · Mock ERP · FastAPI · Python · Postgres · Logistics · Warehousing

## Links to verify before submission

- Application: https://gloveson.vercel.app
- Architecture: https://gloveson.vercel.app/how-it-works
- Repository: https://github.com/kosesena/GlovesOn — private for now
- Demo platform: Vercel + Neon Postgres
- PDF deck: `submission/GlovesOn-deck.pdf` — refresh and review
- Cover: `submission/cover-16x9.jpg` — review against final scope
- Pitch video: pending
