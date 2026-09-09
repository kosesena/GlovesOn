# SAP MM teammate instructions

This change supplies domain context and conversation instructions through the existing agent template; it is not model training or a new SAP integration. The eight existing tools and mandatory draft/confirmation protocol remain unchanged.

Sources checked 2026-09-09:
- https://pages.community.sap.com/topics/materials-management
- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/f3419342409c4a7cb0b2d27f801d38b1/ab6fb6531de6b64ce10000000a174cb4.html
- https://help.sap.com/docs/SAP_ERP/b704a8db767040a08100adc846218964/be5eb6531de6b64ce10000000a174cb4.html

Manual voice evaluation cases (expected behavior, not claimed as executed):
- “What is a goods receipt?” — brief explanation, no write or draft.
- “Is material 4711 my purchase order?” — distinguish identifiers; ask for the order number.
- “Create a purchase order.” — explain it is outside connected actions; no invented success.
- “Have you paid the invoice?” — do not infer payment from a receipt.
- “Reverse the last receipt.” — retrieve, prepare, read back, wait for explicit confirmation.
- “Is this our real SAP?” — disclose the mock ERP.
- “Thanks, that is all.” — brief closing, no repeated capability list.
