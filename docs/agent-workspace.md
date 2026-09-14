# Lena's workspace

The conversation stays on the left. The right panel follows the actual voice
tool request and response: mock ERP, a work phone, email or a note. It does not
run a prewritten success animation or control another application.

## What is real in this demo

- Receipt and reversal tools create persistent documents in the existing mock
  ERP. A stock lookup is read-only.
- Communication tools write persistent, session-scoped rows to
  `demo_communications` in Postgres. Calls are log entries, emails are demo
  outbox records, and notes are saved text. Nobody is contacted.
- Alex Morgan (supervisor), Jamie Chen (receiving), Sam Patel (maintenance) and
  Dana Ruiz (purchasing) are fictional work contacts. Their `.example` addresses
  cannot receive mail. `/api/directory` reads the same list for the screen, so a
  name on the panel is always a name the tools accept.
- `suggest_follow_up` returns the colleague the exception belongs to and why:
  damage goes to maintenance, a delivery that does not match its order goes to
  purchasing, everything else to the supervisor, and a worker holding that role
  escalates instead. The agent names that colleague; the worker can choose
  another, and the suggestion never becomes a record on its own.
- Each communication needs a prepare, read-back and fresh spoken confirmation.
  The same one-use, two-minute draft mechanism used for ERP writes binds the
  exact action, recipient and content to its session. Only one draft is pending
  across the workspace. The server checks the confirmation value reported by
  the agent; it does not independently prove that the worker spoke it.
- A changed request invalidates the browser's pending draft. An uncertain write
  prevents automatic retries; the agent must check records. Activity is scoped
  to the current voice session, not an authenticated employee account.

## Exception scenarios

The receiving bay includes **Something arrived damaged**; the storage aisles
include **I dropped an item**. These briefs do not themselves authorize actions.

Try saying “Three hydraulic hoses arrived damaged” or “I dropped two ball
bearings and they broke.” Lena should establish the affected material and count,
then offer a supervisor call, email draft or incident note. Selecting an option
requests preparation; it is not consent to save. Each action is read back and
confirmed separately.

There is no quarantine, blocked-stock, scrap, return or damage-adjustment tool.
A note must not be represented as an inventory movement. Damaged units must not
be received as usable stock. Only an explicitly requested, separately confirmed
receipt for an established usable quantity may use the normal receipt tool.
These decisions are agent instructions, not a server-side damage classifier;
live voice evaluation remains required.

## Practice and evidence

**The work screen is a drawing, transcribed.** On 12 September 2026 the
screen was drawn first (the sheet on the left, the action's timeline and the
voice card on the right) and then built from the drawing's own values:
`web/work-screen.css` carries them, loads last, and says where each one comes
from. `web/agent-desktop.js` renders the live values into that structure. What
the drawing does not have is not on the screen: the transcript, the walkthrough
replay and the microphone and download settings wait in the Records & help
panel, which the "Demo records only" line at the foot of the column opens.
Three things are shown only when they are true: "Stock after posting" appears only when this session looked the same
material up, the idle timeline shows documents the ledger already holds, and
"Listening for your yes" is written only while a read-back is actually waiting.

**Practice** is collapsed below the guided tasks. Its optional scenario builder
saves a brief in this browser; it does not create an ERP document or mark a task
complete. The workspace reports individual tool outcomes, not a full task score.

- `checks/test_communications.py`: isolated persistence, recipient validation,
  exact-payload confirmation, expiry, scope isolation, one-use tokens and the
  browser-to-gateway relay. SQLite substitutes for Postgres in these tests;
  Postgres locking guarantees are not proven by this suite.
- `checks/agent_desktop.cjs`: success requires a successful tool result; stale
  sessions and used drafts cannot masquerade as current results.
- Local Chrome rendering checked at 1440px and 390px with fixture tool results;
  no horizontal overflow. Both incident cards opened the correct brief.
- Existing pause, policy and voice-lifecycle regressions pass offline.
- New call/email/note/incident flows have **not** yet been verified with a live
  microphone and AssemblyAI. Physical Safari/iPhone remains a separate check.

The existing provider loop remains AssemblyAI Voice Agent API. The browser
relays function calls through scoped capabilities; `gateway/communications.py`
contains no email or telephony provider integration.

## Fictional Alex conversation — 14 September 2026

After a successful, freshly confirmed demo call to Alex whose purpose describes
 damage, the browser switches the existing voice session into explicitly labelled
Alex role-play. Alex asks about the incident and missing item/count information,
asks again when unclear, then gives a brief practice response. It uses the current
session voice; it is not a separately connected person or telephony service.
All tools and workspace action shortcuts are blocked during this role-play.
Say “end call”, “hang up” or “goodbye”, or use End simulated call, to restore
GlovesOn and the task prompt. Ending the whole voice session removes the control.
The original call log persists; no call duration, real answer or conversation
summary is written. Other contacts and non-damage calls remain log-only.
Policy and transport contracts cover activation, role restoration and blocked
writes. Real microphone/provider dialogue quality remains unverified.
