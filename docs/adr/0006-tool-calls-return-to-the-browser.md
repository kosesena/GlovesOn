# 6. Tool calls return to the browser, and the secret stays home

**Status:** Accepted · **Date:** 2026-09-09 · **Recorded:** 2026-09-10

Written after the fact, from the code and the history, because the change went in
under time pressure while live sessions were broken (`f134dcb`). The decision is
sound; it was simply never argued on paper, and this file is the argument.

## Context

Until this change, a browser session worked like this. The gateway took the
template in `agent/agent.json`, filled `{{GATEWAY_PUBLIC_URL}}` into every tool's
URL, attached `X-Tool-Secret` and `X-Event-Scope` as literal header values, and
**created a new agent at AssemblyAI** for that one session. The browser was given
only the agent's id. AssemblyAI then called `/erp/*` on our gateway from its own
servers, and the gateway deleted the agent when the session closed.

`gateway/scoped_agent.py` is still in the tree and still says what that cost, in
its own first line: *"Never return this payload to a browser: it contains the
existing tool credential."* Three things follow from that design.

**The permanent shared secret lived at a third party.** Not derived, not
short-lived, not scoped — the same `TOOL_SHARED_SECRET` the gateway checks on
every ERP route, written into an agent definition, once per session. Every
session left another copy of it there until cleanup ran.

**The gateway had to be publicly reachable.** AssemblyAI dials in, so local
development needed a `cloudflared` tunnel, a new random hostname each start, and
a tunnel → `.env` → `./publish.sh` round trip before any voice work could begin.
That round trip is the top entry in this repository's list of things that waste
time, and it is why `docs/adr/0005` chose a hosting platform partly to escape it.

**Every session depended on provider-side agent lifecycle.** Create, track,
delete. When creation or lookup misbehaved the session did not degrade, it
failed: `/api/voice-token` returned 500 and the demo had no voice at all. That
is what was actually broken on 9 September.

## Options considered

**A. Keep the per-session agent and fix the lifecycle.** The smallest change, and
it leaves the architecture alone. Rejected because it fixes the symptom and keeps
all three costs, including the one that matters most — our long-lived write
credential sitting in someone else's database.

**B. Mint a short-lived secret per session and put *that* in the agent.** The
credential stops being permanent, which is a real improvement. Rejected because
the gateway still has to be publicly reachable, the agent lifecycle stays, and
the tools an agent carries are still fixed for the whole session: an agent
created with `post_goods_receipt` on it has that tool from its first word,
whether or not anything has been prepared.

**C. Send the session configuration inline and let tool calls come back to the
browser.** No agent is created. The gateway builds the config from
`agent/agent.json` at request time, strips the `http` block off every tool so
each becomes a plain `function`, and hands the browser the config plus two
short-lived values: a scope token and a **capability**, which is an HMAC over
that scope token under a domain-separated key (`voice-tools-v1\0`). The agent's
tool call arrives at the browser over the same WebSocket that carries the audio.
The browser posts it to `/api/voice-tools/{name}` with those two headers, and the
gateway — having verified the capability, checked the session is still live, and
looked the name up in an allow-list built from `agent/agent.json` — re-issues the
call against its own `/erp/*` route over the in-process ASGI transport, adding
the real secret there.

## Decision

**C.** `gateway/voice_tools.py` builds the config and mints the capability;
`/api/voice-tools/{name}` is the only door the browser has; the ERP routes,
schema validation, draft protocol and audit path are untouched and unaware.

It also made something possible that option B could not do. The write tools are
**removed from the configuration the agent receives** and kept in a separate
catalogue the browser holds. `web/voice-policy.js` puts `post_goods_receipt`
back into the agent's toolset only while a matching draft is live, and takes it
away again on any user turn that is not an unmistakable yes, on expiry, and for
the rest of the session once a write result has been lost. The agent does not
decline to write without a draft. For most of the conversation it has no such
tool at all.

## Consequences

**What this costs.**

- **The browser is in the write path now.** It relays the call and could relay
  one nobody asked for. What bounds that is unchanged and server-side: the
  capability is session-scoped and dies with the session, the route allow-list
  comes from `agent/agent.json` rather than the request, and the draft protocol
  still requires a prepared, one-use, exactly-matching token that only the
  gateway issues. But the page is no longer just a microphone, and
  `docs/JUDGE-GUIDE.md` already says nobody is authenticated. Both sentences have
  to be read together.
- **One rule, two implementations.** `voice-policy.js` decides which tools the
  agent may see; the gateway decides whether a write may happen. They agree today
  and can drift tomorrow. The gateway's copy is the one that counts, and the
  client's is a convenience that must never be the only thing standing between a
  sentence and a document.
- **There is no published agent to point at any more.** The configuration is
  assembled per request from a file, so "what was the agent running" is answered
  by a git commit rather than by a provider record. Better for iteration, worse
  for forensics.
- **`gateway/scoped_agent.py` still exists**, used only by the diagnostic path,
  which deliberately builds an agent with a deliberately invalid secret. Dead
  weight otherwise, kept because the diagnostic is how a provider-side fault gets
  distinguished from ours.

**What it buys.**

- **`TOOL_SHARED_SECRET` never leaves the process.** The browser holds a scope
  token and a capability, both minted for one session and both useless after it.
- **A write tool that does not exist until a draft does.** This is stronger than
  refusing to use one, and it is the part of this design worth showing.
- **No tunnel, no publish, no provider agent lifecycle.** Local voice work needs
  the gateway and a browser. Changing the voice or the prompt is a file edit and
  a reload; `./publish.sh` has left the working loop.

**What would reverse it.** Telephony. A phone call has no browser to return a
tool call to, so a SIP or PSTN front end brings option B back: a short-lived
per-session secret in a provider-held agent, with the route allow-list and the
draft protocol carrying the same weight they carry today. `docs/adr/0004`
already records that the browser came first and that telephony is the obvious
next surface; this is one more thing that changes when it arrives.
