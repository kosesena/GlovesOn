# 4. Browser microphone first, telephony deferred

**Status:** Accepted · **Date:** 2026-09-05

## Context

The Voice Agent API deploys to a browser over WebSocket or to a phone line over a SIP
trunk. The user in the story — a warehouse worker with full hands — is arguably a
better fit for a headset on a phone line than for a browser tab.

## Options considered

**A. Telephony via SIP.** Closest to the real deployment. Needs a telephony account
and trunk configuration, and produces a demo where nothing visible happens: audio
only, no way to show the ERP changing as the worker speaks.

**B. Browser.** A starter path exists, no third-party account, and one page can hold
both the conversation and the live ERP state.

## Decision

**B**, with telephony kept as a second deployment target rather than a rewrite.

The deciding factor is not development effort — it is that the claim this project
makes ("a voice agent that actually writes to an ERP") is invisible in an audio-only
demo. Stock moving from 240 to 260 on screen, in the same second the worker says
"confirm", is the evidence. A phone call is a story about evidence.

## Consequences

**Good**

- The audit trail is visible: transcript, tool call, material document, new stock
  level, all in one frame.
- Nothing in the agent definition or the gateway is browser-specific, so adding
  telephony later is a deployment change, not a redesign.

**Bad**

- A browser tab is not what a worker with full hands would actually use. The demo
  argues the case; it does not embody it.
- Browser echo cancellation is being relied on to stop the agent hearing itself.
  A headset deployment would not need this, and the barge-in behaviour under
  speakerphone conditions is weaker as a result.
