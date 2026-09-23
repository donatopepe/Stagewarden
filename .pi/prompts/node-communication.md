---
description: WorkPacket and ResultPacket protocol
argument-hint: "<packet>"
---
# Node packet protocol

Parent→child must use a versioned `WorkPacket` containing:

- tree/node/parent/work/correlation IDs;
- parent purpose and child purpose;
- atomic task and expected result;
- inputs and cited knowledge;
- file scope and tool permissions;
- provider/model/account and context budget;
- acceptance criteria, tolerances and retry policy;
- output schema.

Child→parent must use `ResultPacket` containing:

- status and summary;
- evidence references with path/line/hash/exit code where applicable;
- files, tests, tools and usage;
- decisions, risks, blockers and residual work;
- next-action recommendation.

Allowed responses: `accepted`, `needs_clarification`, `rejected`, `result`, `blocked`, `escalation`.

No free-form lateral communication. Every packet is persisted and visible in the terminal.
