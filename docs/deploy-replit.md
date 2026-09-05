# Deploying the gateway on Replit

**What this replaces:** `cloudflared` gives out a new hostname on every start. Because
AssemblyAI refuses to save an agent whose tool host does not resolve, every working
session cost a tunnel → `.env` → `./publish.sh` round trip, and a stale address failed
the publish with a 422 rather than failing quietly later. A fixed address ends that: you
publish the agent once and stop thinking about it.

**Reserved VM, not Autoscale.** Autoscale scales to zero between requests. Two things
break there. The mock's SQLite file does not survive the process, so postings vanish
between one sentence and the next. And the SSE stream that drives the live ERP screen is
a long-lived connection with nothing flowing through it most of the time — exactly what a
scale-to-zero platform treats as idle. Reserved VM keeps one machine up. It is not free;
that is the price of a demo whose state and screen both stay alive.

The deployment type is chosen in Replit's own UI. `.replit` carries the build command,
the run command and the port mapping, but it cannot pick the type for you, so this is the
one step nothing in this repository can enforce.

---

## Steps

**1. Get the code into Replit.** Create a Repl from `https://github.com/kosesena/GlovesOn`
(*Create Repl → Import from GitHub*). `.replit` is already in the repo, so the Python
module, the build command and the port mapping come with it.

**2. Fill in the Secrets pane.** Never a file — `.env` is gitignored and does not travel,
and that is the point.

| Secret | Value |
|---|---|
| `ASSEMBLYAI_API_KEY` | your key |
| `TOOL_SHARED_SECRET` | a value of your own — **the gateway refuses to start without one** |
| `AGENT_ID` | the id `./publish.sh` printed; leave empty on the very first deploy |
| `GLOVESON_ENABLE_RESET` | `0` on any day strangers have the address |

Optional: `SAP_BASE_URL` to point at a real S/4HANA, `GLOVESON_DB_PATH` to put the
mock's database on a disk that survives a redeploy, `VOICE_TOKEN_MAX_PER_HOUR` to raise
or lower the session ceiling. `PORT` is set by Replit; do not set it yourself.

**3. Deploy.** *Deploy → Reserved VM*. Smallest machine size is enough — this gateway
holds an HTTP client, a SQLite file and a handful of SSE queues. Replit will offer
Autoscale as the cheaper default; the paragraph above is why to say no.

**4. Check it came up** before touching the agent:

```bash
curl https://<your-deployment>/health
```

`sap_base_url` should read `http://127.0.0.1:<port> (mock S/4HANA)` — the gateway
reaching its own mock over loopback. If it names your public address instead, something
is running old code.

**5. Point the agent at it, once.** Put the deployment address in `GATEWAY_PUBLIC_URL`
in your local `.env`, keep `TOOL_SHARED_SECRET` identical to the Replit secret, then:

```bash
./publish.sh
```

`publish.py` rejects an `http://` or `localhost` address before it calls the API, so a
half-filled `.env` fails here rather than in the middle of a demo.

After this, `./tunnel.sh` is only needed when you want the agent to hit code running on
your laptop.

---

## Things worth knowing before they surprise you

**A redeploy resets the mock.** The code directory is rebuilt, and the SQLite file lives
in it unless `GLOVESON_DB_PATH` says otherwise. Seed data is rewritten on startup, so the
demo works — but yesterday's material documents are gone. Deploy before a rehearsal, not
between one and the demo.

**The secret has to match in two places.** The Replit secret and the local `.env` value
that `publish.sh` bakes into the agent definition. When they differ, every tool call
comes back 401 and the agent says it cannot reach the system — which sounds like a
network problem and is not.

**Publishing the agent is a separate act from deploying the gateway.** Changing
`agent/agent.json` and redeploying does nothing; AssemblyAI holds its own copy of the
definition. `./publish.sh` is what moves it.

**One machine means one process.** The duplicate guard reads recent documents back from
SAP rather than remembering anything, so it does not depend on that — but the SSE
subscriber list and the voice-token counter are per-process. Both are demo-scale
concerns, and `docs/nfr.md` records the ceiling.
