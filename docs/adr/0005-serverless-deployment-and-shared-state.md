# 5. The gateway runs serverless, so its state moves out of the process

**Status:** Accepted · **Date:** 2026-09-06

> **Since superseded in part.** The first paragraph below describes what was true on
> 2026-09-06. AssemblyAI no longer calls anything of ours: see
> [ADR-0006](0006-tool-calls-return-to-the-browser.md). The hosting decision stands on
> the rest of this record, which is unaffected.

## Context

The gateway needed a stable public HTTPS address. AssemblyAI calls tool endpoints
from its own servers, so a `cloudflared` tunnel — a new random hostname on every
start — cost a tunnel → `.env` → `./publish.sh` round trip every working session.

The gateway as written is a **process**: the mock's data sits in a SQLite file next to
the code, the live screen is fed from a list of subscriber queues in memory, and the
voice-token counter is a module-level list. Those three facts are what a hosting
decision has to survive.

The deployment budget was the deciding constraint. A Vercel Pro subscription was
already being paid for other projects; every alternative was new money.

## Options considered

**A. Replit Reserved VM.** An always-on machine: the code runs exactly as written,
no changes at all. Requires Replit Core at ~$20/month on top of Vercel. Rejected on
cost, after being recommended and prepared for: a runbook and a `.replit` file existed
and were deleted once this decision was taken, because a repository that carries the
configuration of two platforms invites someone to follow the wrong one. Both are in
the history if that day comes.

**B. Fly.io or Render.** Also always-on processes, also zero code changes,
~$2–7/month. Technically the cheapest correct answer. Rejected because it adds a
fourth platform to an account that already pays for Vercel, and because the person
running this system would rather maintain one.

**C. Render's free tier.** A real process, but it sleeps after 15 minutes and takes
about a minute to wake. A tool call arriving at a sleeping gateway times out, and the
agent reports it cannot reach the ERP — a failure that looks like a bug in the demo.

**D. Vercel.** Already paid for. But Vercel does not run processes: its own
documentation is explicit that each instance takes a request, returns a response, and
keeps nothing between calls — no always-on servers, no persistent disks, no in-memory
state shared across instances. All three of the facts above break.

## Decision

**D, with the state moved out of the process.** Three changes, each replacing
something the platform cannot provide:

1. **The mock's data moved from SQLite to Postgres** (Neon, in the same region as the
   functions). `store.py` keeps its shape — schema, seed data, migrations — and
   changes dialect.

2. **The live event stream moved into the database** (`live.py`). The browser's SSE
   connection may be held by one instance while a tool call lands on another; an
   in-memory subscriber list would have written the document to SAP and never shown it
   on screen. Events are rows now; the stream polls them. The same table holds the
   voice-token counter and the current voice-session reference, for the same reason.

3. **The gateway reaches the mock over an in-process ASGI transport.** With no
   listening port there is no loopback, and routing through our own public address
   would push every ERP call out of the data centre and back.

## Consequences

**What this costs.**

- **The live screen is no longer instant.** It updates within about half a second,
  the event poll interval. Next to a spoken sentence this is invisible; a lost
  document would not have been.
- **No offline development.** The mock's data lives in a hosted database, so even a
  local run needs a network and a `DATABASE_URL`. The SQLite file that made this
  project runnable on a plane is gone.
- **Every ERP read now costs a database round trip** rather than a local file read.
  The latency budget in `docs/nfr.md` is written against the old shape and needs
  re-measuring.
- **ADR-0003's seam is narrower than it was.** The mock is still reached by HTTP verb
  and OData path, still performs the CSRF handshake, still returns SAP's error
  envelope — but when it is in-process the bytes do not cross a socket. Pointing
  `SAP_BASE_URL` at a real tenant remains the whole migration, and
  `MOCK_SAP_BASE_URL` still forces a real network hop when one is wanted.
- **Cold starts are real.** A tool call arriving at an idle deployment pays function
  start-up plus a database connection.

**What it buys.** A stable address on infrastructure already paid for, and — not
nothing — a mock that now runs on the kind of database a real deployment would use.

**What would reverse it.** If the poll interval or the cold starts show up in a
demo, an always-on machine (option A or B) restores the original design exactly:
the code that runs on Vercel still runs unchanged on a process host, because
`DATABASE_URL` and `MOCK_SAP_BASE_URL` are the only things that differ.
