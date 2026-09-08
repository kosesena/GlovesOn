# Deploying the gateway on Vercel

**Why Vercel, given that it does not run processes:** the subscription was already
being paid. `docs/adr/0005` records what that costs and which cheaper options were
turned down. What follows is the runbook.

---

## What has to exist first

**A Postgres database.** The mock S/4HANA keeps its data there — Vercel functions have
no persistent disk. Vercel dashboard → *Storage* → *Neon*, free plan, region **`iad1`
(Washington D.C.)** to match the default function region; a database in another
continent adds a round trip to every ERP read. Turn *Auth* off; it provisions a user
system this project does not use.

Take the **pooled** connection string (the host contains `-pooler`). Serverless means
the number of instances is not under our control, and the unpooled endpoint runs into
Postgres connection limits.

---

## Steps

**1. Import the repository.** *Add New → Project → Import* `kosesena/GlovesOn`.
Vercel detects the Python runtime, installs `requirements.txt`, and loads the ASGI app
through `asgi.py`, which exists only to point at `gateway.main:app`.

**2. Connect the database to the project.** From the Neon store page, *Connect to
Project*. This sets `DATABASE_URL` in the project's environment; the code reads it (or
`POSTGRES_URL`) at runtime.

**3. Set the remaining environment variables** — *Settings → Environment Variables*:

| Variable | Value |
|---|---|
| `ASSEMBLYAI_API_KEY` | your key |
| `TOOL_SHARED_SECRET` | a value of your own — **the gateway refuses to start without one** |
| `AGENT_ID` | legacy published agent id (browser sessions create their own agent) |
| `GATEWAY_PUBLIC_URL` | HTTPS URL of this gateway, required for session tool callbacks |
| `GLOVESON_ENABLE_RESET` | `0` on any day strangers have the address |

Optional: `SAP_BASE_URL` to point at a real S/4HANA, `MOCK_SAP_BASE_URL` to reach the
mock over a real socket instead of in-process, `VOICE_TOKEN_MAX_PER_HOUR` to move the
session ceiling. Do not set `PORT`; nothing listens on one.

**4. Deploy, then check it came up** before touching the agent:

```bash
curl https://<your-deployment>/health
```

`sap_base_url` should read `in-process ASGI (mock S/4HANA)`. If it names a URL,
something is configured that should not be. A 500 here is almost always a missing
`DATABASE_URL` or `TOOL_SHARED_SECRET` — both fail loudly on purpose.

**5. Point the agent at it, once.** Put the deployment address in
`GATEWAY_PUBLIC_URL` in your local `.env`, keep `TOOL_SHARED_SECRET` identical to the
Vercel value, then:

```bash
./publish.sh
```

`publish.py` rejects an `http://` or `localhost` address before it calls the API, so a
half-filled `.env` fails here rather than in the middle of a demo.

After this, `./tunnel.sh` is only needed when you want the agent to reach code running
on your laptop.

---

## Things worth knowing before they surprise you

**An imported variable is not a filled-in variable.** Vercel reads `.env.example`
on import and creates every name it finds with an empty value. An empty value is not
the same as an absent one — `os.getenv(name, default)` hands back the empty string and
the default never runs — which crashed the first deployment on `float('')`. The code
now treats blank as absent, but `DATABASE_URL` still has to hold a real string:
delete the empty one and let the Neon integration's *Connect to Project* write it,
rather than leaving a name that looks configured and is not.

**Changing an environment variable does nothing until you redeploy.** The running
deployment keeps the values it was built with. After connecting the database or
editing a secret, redeploy — a push does it, and so does *Redeploy* on the latest
deployment.

**Do not put a bare `pyproject.toml` at the root.** Vercel takes its presence as a
signal to build with `uv`, which then fails on `No project table found` if the file
carries only tool configuration. Two deployments broke this way while the health check
kept answering — the *previous* build was still serving. Tool settings live in
`pytest.ini` and `ruff.toml` for that reason, and dependencies stay in
`requirements.txt`.

**A green CI badge does not mean the deployment succeeded.** They are different systems:
CI ran the tests on the same commit that Vercel refused to build. Check the deployment
state, or ask the live URL for something only the new code answers.

**The demo database is shared by every deployment.** Preview deployments and
production point at the same Neon database unless you branch it. A `/api/reset` from a
preview URL wipes what production is showing.

**Cold starts are real.** A tool call arriving at an idle deployment pays function
start-up plus a database connection. It is well inside the agent's patience, but the
first sentence of a demo is the slowest one — say something to the agent before the
judges are watching.

**The live screen is half a second behind.** Events travel through a table now, polled
by the SSE stream. If it ever feels slow, `EVENT_POLL_SECONDS` in `gateway/main.py` is
the dial, and every poll is a database query.

**The secret has to match in two places**: the Vercel environment variable and the
local `.env` value that `publish.sh` bakes into the agent definition. When they differ,
every tool call comes back 401 and the agent says it cannot reach the system — which
sounds like a network problem and is not.

**Publishing the agent is a separate act from deploying the gateway.** Changing
`agent/agent.json` and redeploying does nothing; AssemblyAI holds its own copy of the
definition. `./publish.sh` is what moves it.

**Going back to a process host is cheap.** The code still runs unchanged on an
always-on machine — Fly.io, Render, a Replit Reserved VM. Set `DATABASE_URL` and it
works; that is the whole difference, and ADR-0005 records what such a move would buy
back.

## Private browser sessions

The gateway now creates a stored AssemblyAI agent for each browser session from
`agent/agent.json`. Include that file in the deployment bundle. Tool authentication
and signed event-routing headers are configured server-side; the browser receives
an agent id and expiring scope token, never the shared tool secret.

`live.init()` adds `scoped_agents` without resetting warehouse data. Normal browser
teardown deletes the temporary agent; failed deletions are retried after expiry on
later token requests. There is no scheduled sweep when the app is idle. The scope
expires after ten minutes; provider voice sessions are limited to five minutes.

Preview deployments must point GATEWAY_PUBLIC_URL to their own reachable gateway
when testing scoped results; a production callback URL routes events to production.
