# VoxERP — Hands-Free Warehouse Operator

> Voice agent that lets a warehouse worker query and **write to** an SAP ERP system
> without touching a screen. Built for the AssemblyAI Voice Agent Hackathon (Sept 2026).

Ask *"how many of material four seven one one do we have?"* and get an answer.
Say *"post a goods receipt, twenty pieces"* and — after the agent reads the line back
and you confirm — a material document is actually posted and stock changes on screen.

---

## Architecture

```
Browser mic ──PCM16/24kHz──> AssemblyAI Voice Agent API ──HTTP tools──> VoxERP Gateway ──> SAP
                             (STT · turn detection ·                    (FastAPI)          (mock today,
                              LLM · TTS · barge-in)                                         OData tomorrow)
                                                                              │
                                                                              └──SSE──> live warehouse screen
```

The agent never talks to the ERP directly. The gateway owns authentication, SAP field
translation and the write guardrails.

## AssemblyAI features used

| Feature | Where |
|---|---|
| Voice Agent API (browser deployment) | `web/index.html` |
| HTTP tools | `agent/agent.json` — 4 tools |
| `execution_mode: "hold"` | goods receipt — agent waits while the ERP write completes |
| Turn detection & barge-in | left on adaptive defaults; client flushes audio on `input.speech.started` |
| Noise suppression (voice focus) | warehouse floor noise |
| Session token minting | `GET /api/voice-token` — the API key never reaches the browser |

## SAP fidelity

The mock speaks real SAP: `MATNR` (18-char zero-padded), `MAKTX`, `WERKS`, `LGORT`,
`LGPLA`, `LABST`, `MEINS`, and material documents in `MKPF` with movement types
**501** (receipt without purchase order) and **101** (receipt against a PO).
Swapping in a real S/4HANA OData service means changing four functions in
`gateway/main.py` — the agent config does not change at all.

---

## Design decisions

The reasoning behind this system is written down, not left in the code:

- **[docs/adr/](docs/adr/)** — why a gateway sits between the agent and the ERP, why
  every write is confirmed out loud, why the ERP is mocked behind a faithful field
  contract, and why the browser came before telephony.
- **[docs/nfr.md](docs/nfr.md)** — latency budget, concurrency ceiling, failure modes,
  security posture and cost model, including the known defects.

Start with [ADR-0001](docs/adr/0001-gateway-between-agent-and-erp.md) if you only
read one.

## Setup

```bash
pip install -r gateway/requirements.txt
cp .env.example .env          # fill in ASSEMBLYAI_API_KEY and TOOL_SHARED_SECRET

# 1) run the gateway
uvicorn gateway.main:app --reload --port 8000

# 2) expose it over public HTTPS — AssemblyAI tools cannot reach localhost
cloudflared tunnel --url http://localhost:8000
#    → put the https://... address into GATEWAY_PUBLIC_URL in .env
#    (local development only — see Deployment below)

# 3) publish the agent
python agent/publish.py
#    → copy the returned agent id into AGENT_ID in .env, restart uvicorn

# 4) open http://localhost:8000 and press "Start talking"
```

> **The tunnel is not optional.** AssemblyAI calls your tool endpoints from its own
> servers: HTTPS and public hosts only, private and loopback addresses are blocked,
> redirects are not followed.

## Deployment

The gateway is deployed on **Replit**, which gives it a stable public HTTPS address.
That address is not a convenience: AssemblyAI invokes tool endpoints from its own
servers over HTTPS to public hosts only, so a locally-running gateway is unreachable
no matter what else is configured.

Replit also runs the service as written — FastAPI, SQLite and a long-lived SSE
connection all work unchanged. A serverless target would have required replacing the
storage layer and rethinking the event stream for no gain at this scale.

Set `ASSEMBLYAI_API_KEY`, `TOOL_SHARED_SECRET` and `AGENT_ID` as secrets there, point
`GATEWAY_PUBLIC_URL` at the deployment's own URL, and re-run `agent/publish.py` so the
tool definitions carry the new address.

## Try saying

- "How many of material four seven one one do we have?"
- "Where are the ball bearings stored?"
- "What's the status of purchase order four five zero zero zero zero one two three five?"
- "Post a goods receipt, twenty pieces of four seven one one" → then **"confirm"**
- Interrupt the agent mid-sentence — barge-in is on.

## Layout

```
agent/agent.json     agent definition: system prompt + 4 HTTP tools
agent/publish.py     publishes it to POST /v1/agents (placeholders from .env)
gateway/main.py      tool endpoints, SSE feed, token minting, mock SAP (SQLite)
web/index.html       voice client + live ERP screen, single file, no dependencies
PLAN.md              25-day hackathon plan (Turkish)
```

## Safety design

Reads are free; the write is not. `post_goods_receipt` is only reachable after the
agent reads back quantity, unit, material description **and** destination bin and the
worker confirms. The gateway independently rejects unknown materials, non-integer and
non-positive quantities, and any call without the shared tool secret — so a
mis-behaving prompt still cannot corrupt stock.
