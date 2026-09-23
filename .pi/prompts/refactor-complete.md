---
description: Plan a safe node-scoped refactor
argument-hint: "<node-scope>"
---
# Node-scoped refactor

Before editing:

1. identify parent purpose and child work packet;
2. retrieve code map entries for files/classes/procedures/functions/tests;
3. record current contracts and dependencies;
4. define smallest change and acceptance evidence;
5. confirm file/tool/provider/model/context policy.

During work:

- stay inside scope;
- emit file/tool/test events;
- keep one active mutation or use explicit lock;
- update Node Knowledge Store with decisions and evidence;
- compact node context before budget exhaustion.

After work:

- run wet tests;
- verify diff and behavior;
- return ResultPacket/EvidencePacket;
- let parent aggregate; do not claim whole-tree completion.
