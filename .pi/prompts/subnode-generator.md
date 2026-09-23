---
description: Generate bounded child nodes for bottom-up execution
argument-hint: "<parent-work-packet>"
---
# Child-node generator

Create the smallest independently verifiable child nodes needed by the parent.

For each child return:

- stable `node_id`, `parent_node_id`, purpose and owner;
- atomic work packet;
- inputs and cited Node Knowledge Store entries;
- file/tool scope;
- provider/model/context policy;
- outputs and evidence contract;
- acceptance criteria and wet-run tests;
- tolerances, retry and escalation rules;
- dependencies and readiness condition;
- terminal purpose reminder.

Do not create speculative nodes, hidden parallelism, or lateral communication edges. Default child count and execution are serial unless policy says otherwise.
