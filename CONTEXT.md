# GlovesOn

A voice agent through which a warehouse worker with both hands full queries stock and posts goods receipts into SAP. The thing that makes the project what it is: it writes to a system of record, so every term below exists to keep a spoken sentence and a posted document honest with each other.

## The ledger

**Goods receipt**:
The posting that records goods arriving into stock. Movement type 501 without a purchase order, 101 against one.
_Avoid_: receipt (alone, in code or prose: it collides with the receipts/ directory), delivery, booking

**Material document**:
The numbered SAP document a goods receipt or a reversal creates. It is never edited or deleted; a mistake gets a second document.
_Avoid_: record, entry, transaction, MBLNR (the field name, fine in code, not in prose)

**Reversal**:
A material document posted against an earlier one to undo it: 102 against a 101, 502 against a 501. Both documents stay.
_Avoid_: delete, cancel (cancel means abandoning a draft that was never posted), rollback, undo

**Movement type**:
SAP's three-digit code for what a posting does to stock (101, 102, 501, 502). Named in full when spoken about; never "type".

**Material**:
The thing in stock, identified by its number (4711) and known to the worker by its description (Hex Bolt M8x40 Zinc Plated). In SAP the number is 18 characters, zero-padded; nobody says it that way.
_Avoid_: item, product, SKU, part, MATNR (in prose)

**Material description**:
The human name of a material from the material master. The read-back names it because it is what lets a worker notice they are holding nuts, not bolts.
_Avoid_: name, label, title

**Storage bin**:
The shelf position a material lives in, e.g. A-03-02 (aisle A, level three, position two). The system looks it up; the worker is never asked for it.
_Avoid_: bin (alone), location, slot, shelf

**Plant / storage location**:
SAP's site (1000) and sub-site (0001) for a posting. Defaults; the worker never says them.

**Unrestricted stock**:
The quantity of a material available for use, the number "how much do we have" answers.
_Avoid_: stock level (the "271 → 283" line is a stock level change, not the term), inventory, on hand (UI copy only)

**Mock S/4HANA**:
The in-process stand-in for a real SAP tenant. It implements the released OData contract exactly, sits opposite the gateway like any other system, and is the only reason the demo needs no tenant.
_Avoid_: fake SAP, stub, simulator, "the SAP" (it is a mock and is called one everywhere)

**Released OData contract**:
The public SAP API surface the gateway speaks: `A_MaterialDocumentHeader`, the `X-CSRF-Token: Fetch` handshake, SAP's error envelope. What makes a real tenant one environment variable away.
_Avoid_: SAP API, REST API, integration

## The write discipline

**Draft**:
A prepared, not yet posted, goods receipt or reversal: quantity, unit, description, bin, plant, all looked up. Exists for two minutes and for one use.
_Avoid_: pending write, proposal, plan, intent

**Draft token**:
The one-use credential the gateway mints with a draft. A write without a matching token does not exist as a request; a correction invalidates the token and prepares a new draft.
_Avoid_: confirmation token, nonce, ticket

**Read-back**:
The agent saying the draft aloud before asking for confirmation: quantity, unit, material description, bin. A mistake control, never an authorisation control.
_Avoid_: summary, repeat, echo, verification

**Spoken yes**:
The worker's unmistakable confirmation after a read-back, carried with the draft token as the sentence that caused the document. Reported by the agent, not measured from audio.
_Avoid_: approval, consent, confirmation (alone; say what confirms what)

**Duplicate guard**:
The gateway's refusal of an identical posting within two minutes of the last one. Lives in the gateway on purpose: real S/4HANA accepts the same goods receipt twice.
_Avoid_: idempotency (a property, not this mechanism), dedupe

**Provenance**:
The sentence the worker confirmed and the second it happened, kept with every posted document and served at `/api/provenance/{document}`.
_Avoid_: audit log (that is the wider trail), history, trace

**Receipts** (the directory):
`receipts/`: the request and response of every step of one real run against the deployment, kept in the repository so a judge sees the system worked without opening a microphone.
_Avoid_: fixtures, samples, examples (they are recorded, not written)

**Audit trail**:
Everything the gateway keeps about a write: the draft, the token, the spoken yes, the document, the provenance row. Not an identity: a session reference is not a worker.

## The voice loop

**Session**:
One connection to the AssemblyAI Voice Agent API: audio up, the agent's speech and tool calls down, over a single WebSocket the browser opens. Billed per connected second.
_Avoid_: call (that is a demo call, below), conversation, chat

**Inline session config**:
The agent definition (`agent/agent.json`: prompt, voice, tools, keyterms) sent with each session rather than stored at the provider. Nothing at AssemblyAI holds our address or our secret.
_Avoid_: agent registration, published agent, provider-side agent

**Tool bridge**:
The route a tool call takes since ADR-0006: down the same WebSocket that carries the audio, into the browser, posted to the gateway's `/api/voice-tools/*`, re-issued by the gateway against its own `/erp/*` with the real secret.
_Avoid_: webhook, callback, tunnel (the tunnel is gone), tool endpoint

**Capability**:
The per-session credential the browser carries when it posts a tool call. Minted by the gateway, valid for that session alone, and not a person: it says which session spoke, never who.
_Avoid_: token (alone), API key, auth, session key

**Allow-list**:
The set of tool names the gateway will re-issue, built from `agent/agent.json` on every request. A tool not on it is not callable however the agent asks.
_Avoid_: whitelist, registry, manifest

**Voice policy**:
`web/voice-policy.js`: which of the allowed tools the agent may see at this moment of the conversation. The write tools appear only while a draft is live.
_Avoid_: tool gating, permissions, feature flags

**Live screen**:
The ERP page the gateway pushes to over SSE as a posting happens: the material document, as it posts.
_Avoid_: dashboard, UI, ERP view

## The workspace

**Workspace**:
Lena's split screen: conversation on the left, the tool result on the right as an ERP page, a work phone or an email and notes screen.
_Avoid_: app, console, dashboard

**Scenario**:
A guided task in the workspace: receive a delivery, get the quantity right, something arrived damaged. Practice builds new ones without changing inventory.
_Avoid_: task, flow, use case, demo (a scenario is what a demo runs through)

**Demo call / demo outbox / incident note**:
The three communication writes: a logged call to a fictional colleague, an email saved to an outbox nobody reads, a note kept for the session. All three follow the draft protocol; none reaches a real person.
_Avoid_: phone call, email (without "demo"), message, notification

**Colleague directory**:
The fictional work phone: Alex Morgan the supervisor, Jamie Chen, Sam Patel, Dana Ruiz. Fictional, and said to be, everywhere.
_Avoid_: contacts, users, team

**Lena**:
The named worker: a receiving-dock operator with both hands under a box. Every surface (README, deck, film, form) uses her, because a category has no morning.
_Avoid_: the user, the operator, a warehouse worker (when a name will do)

**Slogan**:
"Work flows. Just speak." — settled 24 September 2026, on the cover and the site's eyebrow line.
It replaces "Built for hands that are busy", which stays only in old drafts under `output/`.
_Avoid_: "Voice. Woven into work." (a one-day draft), "hands-free SAP", any line that claims
the agent adapts to the speaker.

## The limits

**Principal propagation**:
The missing piece: the posting is made by a service user, so SAP cannot say which worker spoke. Closing it needs SAP BTP; it is named, not hidden.
_Avoid_: SSO, login, user auth

**Clean Core**:
SAP's rule set for extensions that survive upgrades. `docs/clean-core.md` says where GlovesOn complies and, at greater length, where it does not.
