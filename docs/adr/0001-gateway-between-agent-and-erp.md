# 1. A gateway sits between the voice agent and the ERP

**Status:** Accepted · **Date:** 2026-09-05

## Context

The AssemblyAI Voice Agent API can call arbitrary HTTP endpoints as tools. SAP
systems expose OData services over HTTP. So the agent *could* be pointed straight
at the ERP, with tool definitions mapping onto OData entity sets.

The system writes to an ERP. A goods receipt posted in error is not a bad chat
reply — it is a material document that has to be reversed, and stock that was wrong
for however long nobody noticed.

## Options considered

**A. Agent calls SAP OData directly.** Fewest moving parts, no service to deploy or
operate. But: SAP credentials would live in the agent's tool headers on a third-party
platform; every OData quirk (18-char MATNR padding, CSRF tokens for writes, `$batch`
semantics, error payloads written for developers rather than for speech) would have to
be absorbed by prompt engineering; and the only thing standing between a
mis-generated tool call and a posted document would be the model's own judgement.

**B. A gateway service in between.** One more service to write, deploy and keep up —
and one more hop in the latency budget.

## Decision

**B.** The agent talks only to the gateway. The gateway owns ERP credentials, field
translation and write validation.

## Consequences

**Good**

- ERP credentials never leave infrastructure we control. The agent platform holds
  only a shared secret scoped to this gateway.
- Validation is enforced twice, independently. The prompt asks for confirmation; the
  gateway separately rejects unknown materials, non-integer and non-positive
  quantities, and any unauthenticated call. A prompt injection or a model mistake
  still cannot corrupt stock — the strongest argument for this decision.
- Tool responses are shaped for speech, not for developers. `"Material 4711 not found
  in plant 1000"` is something the agent can say out loud; an OData fault envelope
  is not.
- The ERP behind the gateway is swappable (see ADR-0003).

**Bad**

- One more network hop inside the turn budget (see `docs/nfr.md`). Measured, not
  assumed.
- A service to deploy, monitor and keep online. If the gateway is down, the agent
  degrades to apologising.
- Two places now know the tool contract: `agent/agent.json` and the gateway routes.
  They can drift. Contract tests would fix this; not built yet.

## Notes

The gateway is also the natural place for the things a production deployment would
need and this one does not have: per-worker identity and authorisation (who is allowed
to post a receipt at all), an audit trail linking each material document to a session
recording, and rate limiting.
