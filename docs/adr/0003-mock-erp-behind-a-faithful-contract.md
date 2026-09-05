# 3. The ERP is mocked behind a faithful SAP field contract

**Status:** Accepted · **Date:** 2026-09-05

## Context

The project needs an ERP to talk to. Three were available: a real S/4HANA system
reachable through an employer's network, a SAP BTP trial with a small OData service
built on it, or a mock.

The build window is 25 days, part-time.

## Options considered

**A. An employer's SAP system.** Rejected outright, and not on technical grounds.
Company data and company credentials do not belong in a public hackathon submission.
This is not a trade-off to weigh; it is a line.

**B. SAP BTP trial with a real OData service.** Honest end-to-end story. Also trial
account setup, service definition, CORS, principal propagation and OAuth — days of
work whose failure mode is having nothing to demo.

**C. A mock.** Fast and reliable, and risks building an agent that only works against
a toy: a mock that accepts `{"id": 4711, "qty": 20}` teaches nothing about a system
where the material number is `000000000000004711` and a goods receipt is a movement
type against a material document.

## Decision

**C, with the contract taken seriously.** The mock speaks SAP's data language:
`MATNR` (18-character, zero-padded, with normalisation from spoken digits), `MAKTX`,
`WERKS`, `LGORT`, `LGPLA`, `LABST`, `MEINS`, and material documents in `MKPF` with
movement type **501** (receipt without purchase order) and **101** (receipt against a
purchase order).

The decision being made here is not "mock vs real" but **where the seam goes**. The
seam is the gateway's four ERP functions. Everything above the seam — the agent
definition, the tool schemas, the confirmation flow, the client — is unaware of what
is below it.

## Consequences

**Good**

- Swapping in a real OData service changes four functions and no agent
  configuration. That claim is the point of the decision and is falsifiable: if it
  turns out not to be true, the contract was not faithful enough.
- The awkward parts of the real integration are met now, while they are cheap. MATNR
  padding is the clearest example: it would have been discovered on day one against
  a real system and never at all against a naive mock.
- Demos do not depend on a trial system being up.

**Bad**

- Not proof. It demonstrates that the integration is *designed* correctly, not that
  it *works* against S/4HANA. This should be stated plainly rather than glossed —
  overselling a mock is worse than having one.
- The mock cannot teach what real SAP will: CSRF token handling on writes, session
  management, `$batch`, and error payloads that are considerably less tidy.
- Movement types beyond 101 and 501 are not modelled at all.

## Follow-up

Connecting a BTP trial is scheduled as optional work, time-boxed and abandoned if it
overruns. If it lands, the claim above stops being a claim.
