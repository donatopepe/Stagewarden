---
description: Structured communication protocol between nodes
argument-hint: "<message-context>"
---
# Node-to-Node Communication

Formato messaggio:

FROM: <node-id>
TO: <node-id>
TYPE: status | dependency | conflict | decision | blocker | result
SUMMARY: <1-2 frasi>
DETAILS:
- ...
- ...
ACTIONS REQUIRED:
- ...
PRIORITY: low | medium | high | critical
TOLERANCE IMPACT: none | minor | moderate | severe

Regole:
- messaggi brevi
- niente rumore
- niente speculazioni non marcate
- ogni decisione deve indicare reversibilità
- ogni blocker deve indicare il passo successivo