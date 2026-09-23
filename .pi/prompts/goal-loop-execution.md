---
description: Execute one governed node-tree task
argument-hint: "<task>"
---
# Node-tree execution

Use this prompt to execute a Stagewarden task under the v3 node contract.

Order:

1. Define root purpose, scope, deliverables, constraints and acceptance.
2. Build/validate the tree top-down.
3. Select ready leaves and execute bottom-up.
4. Use serial execution unless user policy explicitly enables isolated parallel leaves.
5. Forward work only through `WorkPacket`.
6. Return only `ResultPacket` with verifiable `EvidencePacket`.
7. Persist node context, events, decisions and recovery.
8. Show active node, parent, purpose, work, tool, file, test, context and status in terminal.
9. Compact only the active node context before its provider/model budget is exceeded.
10. Do not change provider/model/account/fallback without user-authorized policy.

Completion requires acceptance evidence. A narrative summary alone is not completion.

Canonical plan: `TODO.md`. Canonical specification: `docs/specs/stagewarden-v3.md`.
