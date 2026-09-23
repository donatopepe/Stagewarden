---
description: Validate one node result with real evidence
argument-hint: "<node-work>"
---
# Node validation

1. Define acceptance and evidence before work.
2. Execute real tools/tests where possible.
3. Record command, exit code, path/line/hash, timestamp and node/work IDs.
4. Index evidence in the Node Knowledge Store.
5. Verify result against child and parent acceptance.
6. Reject completion without evidence.
7. If wet-run is blocked, record environment blocker separately from product failure and escalate.
8. Return a `ResultPacket`; do not write an unstructured completion claim.

Compaction, dry-run and model narrative are not validation evidence by themselves.
