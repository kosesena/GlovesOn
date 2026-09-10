# Clean Core

SAP's Clean Core principle says an extension must not make the core harder to
upgrade: no modifications to standard objects, no reaching into internals, only
released APIs, and the extension itself kept outside the ERP where possible.

This document states where GlovesOn complies, where it does not, and what would have
to change before it could run against a customer's system. The second list matters
more than the first.

---

## 1. Where it complies

**It is a side-by-side extension.** Both the agent and the gateway run entirely outside
SAP. No ABAP was written. No standard object was modified. No Z object exists in the
core. An S/4HANA upgrade cannot break this system, because there is nothing of ours
inside it to break.

**It talks only to released APIs.** No table reads, no RFC into internals, no scraping
of a Fiori UI:

| API | Entity | Use |
|---|---|---|
| `API_MATERIAL_DOCUMENT_SRV` | `A_MaterialDocumentHeader` | post and reverse goods movements |
| `API_MATERIAL_STOCK_SRV` | `A_MatlStkInAcctMod` | read unrestricted stock |
| `API_PRODUCT_SRV` | `A_ProductDescription` | read material descriptions |
| `API_PURCHASEORDER_PROCESS_SRV` | `A_PurchaseOrder` | read purchase order status |

**It respects the write protocol.** Every posting performs the `X-CSRF-Token: Fetch`
handshake first and carries the token on the POST, and honours the movement-type rules
the system enforces — `GoodsMovementCode` 01 against a purchase order, 05 without one.

**It duplicates no master data.** Material descriptions, units, storage bins and
movement types are read from the system on demand. There is no local copy to drift.

**It corrects rather than deletes.** A goods receipt posted in error is reversed with a
102 or 502 document. Both documents remain. The audit trail stays intact, which is a
Clean Core concern as much as a functional one.

**The gateway is stateless.** It remembers nothing between requests, including for the
duplicate check — it asks the system of record instead. So it scales horizontally and
holds no shadow state that could disagree with SAP.

---

## 2. Where it does not comply

**No principal propagation. This is the significant one.** The posting is not made *as*
the worker. SAP has no idea who spoke, and the worker's own authorizations are never
checked. Every material document this system creates would carry a single technical
user. In a real deployment that is not a rough edge, it is a blocker: an ERP posting
that cannot name the person who made it is not auditable.

**Authentication is a shared secret.** One header value stands between anything on the
network and the write endpoint. Single factor, no rotation, no per-worker identity. The
secret is at least no longer stored at the agent platform — since
[ADR-0006](adr/0006-tool-calls-return-to-the-browser.md) the browser presents a
session-scoped capability instead and the secret stays in the gateway — but a capability
identifies a session, not a person, and Clean Core cares about the person.

**No BTP connectivity model.** A real side-by-side extension reaches the backend through
the Destination service, with credentials held there and principal propagation
configured — not through a URL in an environment variable.

**No authorization check.** Nothing establishes that this worker may post to this plant
and storage location. SAP would enforce it if the call carried a real user; today the
call does not.

**It runs against a mock.** The contract is faithful and the protocol is real, but no
claim is made that this has been proven against a live tenant. The gap between "speaks
the API correctly" and "works against S/4HANA" is real: CSRF behaviour behind a reverse
proxy, `$batch` semantics for multi-item documents, and error payloads considerably less
tidy than a mock's.

**Clean Core has dimensions this project does not touch:** clean data, clean processes,
clean operations. Only clean extensibility and clean integration are addressed here.

---

## 3. Target architecture

What this would look like as a real side-by-side extension. Only the middle box changes.

```
   Warehouse worker (headset)
            │
            ▼
   ┌─────────────────────────┐     ┌─────────────────────────┐
   │  The page, signed in     │◀───▶│  AssemblyAI Voice Agent │
   │  against IAS             │     │  STT · turns · LLM · TTS│
   └───────────┬─────────────┘     └─────────────────────────┘
               │  the tool call, now bearing the worker's own token
               ▼
   ┌──────────────────────────────────────────────┐
   │  SAP BTP — Cloud Foundry or Kyma             │
   │                                              │
   │   GlovesOn gateway                           │
   │     · read-back and confirmation guard       │
   │     · duplicate protection                   │
   │     · SAP field translation                  │
   │                                              │
   │   Identity Authentication  ── worker signs in│
   │   Destination service      ── credentials    │
   │   Connectivity service     ── principal      │
   │                               propagation    │
   └───────────────────┬──────────────────────────┘
                       │  OData, as the worker
                       ▼
   ┌──────────────────────────────────────────────┐
   │  S/4HANA — released APIs only                │
   │  material documents · stock · products · POs │
   └──────────────────────────────────────────────┘
```

The gateway does not move and does not change shape. What arrives is identity: the
worker signs in, the call is made under their name, and SAP applies their
authorizations. The material document then carries who posted it — which is what makes
it auditable, and what makes the whole thing deployable.

One thing did get easier since this section was first written. Tool calls no longer
originate at AssemblyAI; they come back to the page and the page forwards them
([ADR-0006](adr/0006-tool-calls-return-to-the-browser.md)). The page is where a signed-in
worker's session would already live, so the token that has to reach SAP would be attached
at the point it already exists, rather than having to be smuggled into an agent
definition held by a third party. It removes an obstacle. It does not do the work: none
of the five steps below is implemented, and this section still describes a design, not a
deployment.

---

## 4. What it would take

In the order a real project would do it:

1. **Principal propagation.** Worker signs in against Identity Authentication; the
   gateway forwards their identity through the Destination and Connectivity services.
   Removes the shared secret and the missing-audit problem in one move.
2. **Deploy the gateway to BTP** (Cloud Foundry or Kyma) with the destination
   configured there rather than in an environment variable.
3. **Prove it against a real tenant.** A BTP trial with a live S/4HANA connection turns
   every claim in section 1 from designed to demonstrated.
4. **Authorization surfacing.** When SAP refuses a posting for lack of authorization,
   say so in words the worker can act on, not as an error code.
5. **Idempotency key per confirmed intent**, replacing the time-window heuristic the
   gateway uses today.

Items 1 and 2 are the difference between a prototype and something a customer could
run. Nothing above requires changing a line of the agent definition.
