---
description: Handle node tolerance breach and recovery
argument-hint: "<node-exception>"
---
# Node exception policy

For every deviation record:

- tree/node/parent/work IDs;
- cause and first evidence;
- impact on scope, time, cost, context, safety, compatibility and acceptance;
- current purpose and state;
- options and reversibility;
- recommended recovery;
- owner decision;
- next packet/event.

Minor reversible local deviations may be handled inside scope. Scope expansion, provider/model/account change, cost change, data egress, security, architecture, evidence failure or irreversible action must block/escalate. Never hide a blocked node by marking it complete.
