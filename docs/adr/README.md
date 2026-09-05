# Architecture Decision Records

Short records of the decisions that shaped GlovesOn: the context, the options that
were actually on the table, what was chosen, and what that choice costs.

A decision belongs here if reversing it later would be expensive.

| # | Decision | Status |
|---|---|---|
| [0001](0001-gateway-between-agent-and-erp.md) | A gateway sits between the voice agent and the ERP | Accepted |
| [0002](0002-confirm-before-write.md) | Writes require a spoken read-back and explicit confirmation | Accepted |
| [0003](0003-mock-erp-behind-a-faithful-contract.md) | The ERP is mocked behind a faithful SAP field contract | Accepted |
| [0004](0004-browser-first-not-telephony.md) | Browser microphone first, telephony deferred | Accepted |

Format: [MADR](https://adr.github.io/madr/), trimmed.
