# Stagewarden v2 specification — superseded

This document is retained as historical design context only.

The canonical specification is now [`stagewarden-v3.md`](stagewarden-v3.md). The v3 redesign changes the work model from a generic multi-agent/goal-loop surface to:

- tree-first node identity and purpose;
- top-down planning with bottom-up execution;
- serial execution by default;
- typed parent→child `WorkPacket` forwarding;
- typed child→parent `ResultPacket` and `EvidencePacket` return;
- node-scoped context and history;
- Node Knowledge Store with code-aware index;
- terminal purpose/activity observability;
- per-node context accounting and automatic compaction;
- explicit user ownership of provider, model, account, credentials, costs and fallback.

Do not implement from this file. Use [`../../TODO.md`](../../TODO.md) and [`stagewarden-v3.md`](stagewarden-v3.md).
