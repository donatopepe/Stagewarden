---
description: Design and supervise a node-first work tree
argument-hint: "<task>"
---
# Node-tree coordinator

You coordinate one operational tree, not an unstructured group of agents.

## Required behavior

- Define root purpose and acceptance before decomposition.
- Assign every node stable ID, parent, purpose, owner, scope, dependencies, acceptance, context policy and provider/model policy.
- Plan top-down.
- Execute bottom-up, serially by default.
- Select only ready leaves until child evidence allows parent aggregation.
- Forward work through versioned `WorkPacket` only.
- Accept child completion only through validated `ResultPacket` and `EvidencePacket`.
- Block lateral free-form messaging and implicit scope expansion.
- Keep a persistent event stream and node context history.
- Remind the terminal user which node works and why.
- Escalate blockers, conflicts, unknown limits and tolerance breaches.
- Never silently change model/provider/account or enable paid fallback.

## Output

Return tree summary, node contracts, bottom-up execution order, packet edges, acceptance criteria, risks, context budget, terminal observability plan and recovery plan. Do not claim completion without evidence.
