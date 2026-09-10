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
| `AGENT_ID` | legacy; nothing on the session path reads it |
| `GATEWAY_PUBLIC_URL` | this gateway's own HTTPS URL — validated, not dialled; **must not be empty** |
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

**5. There is no step five.** Nothing has to be pushed to AssemblyAI. Since
[ADR-0006](adr/0006-tool-calls-return-to-the-browser.md) the session configuration is
assembled from `agent/agent.json` on every `/api/voice-token` request and sent inline
over the browser's socket, so a deploy is the whole release: the next session runs
whatever the commit says. `./publish.sh` and `./tunnel.sh` remain for the diagnostic
path only.

What still has to match is `TOOL_SHARED_SECRET`, because it is the key behind the
per-session capability the browser presents. Confirm both ends agree without printing
either:

```bash
curl -s https://<your-deployment>/health | python3 -m json.tool | grep -A4 configured
```

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

**A deploy is the whole release.** Changing `agent/agent.json` and redeploying is all
there is: browser sessions read that file per request, so the prompt, the voice, the
keyterms and the tool schemas ship with the commit. Nothing is held at AssemblyAI to
fall out of step with it.

**The two stale-copy traps below apply only to the diagnostic path**, which is the one
place a stored agent is still published. There, the secret has to match in two places —
the Vercel variable and the local `.env` value `publish.sh` bakes in — or every tool call
comes back 401 and the agent says it cannot reach the system, which sounds like a network
problem and is not. And there, `./publish.sh` is what moves a template change; a redeploy
alone does nothing.

**Going back to a process host is cheap.** The code still runs unchanged on an
always-on machine — Fly.io, Render, a Replit Reserved VM. Set `DATABASE_URL` and it
works; that is the whole difference, and ADR-0005 records what such a move would buy
back.

## Private browser sessions

The gateway supplies inline AssemblyAI session configuration from `agent/agent.json`.
Include that file in the deployment bundle. Browser sessions do not depend on a
stored agent ID. Tools use client-side function calls through the allowlisted
`/api/voice-tools/{name}` bridge. The browser receives an expiring signed scope and
a separate tool capability, never the shared tool secret. The bridge requires both
credentials and an active database session, then invokes the existing ERP routes
with server-side authentication. Existing validation and confirmation rules apply.

`live.init()` adds `scoped_agents` without resetting warehouse data. Inline sessions
store a local marker; browser teardown removes it and revokes tool access. Legacy
stored agents still receive provider cleanup, retried after expiry on later token
requests. There is no scheduled sweep when the app is idle. The scope expires after
ten minutes; provider voice sessions are limited to five minutes.

A preview deployment needs its own `GATEWAY_PUBLIC_URL` set to something — the variable
is validated on every session and an empty one answers 500 — but nothing calls it, so it
no longer has to be the preview's own address for results to arrive. The browser talks to
whichever origin served it.
