# Stagewarden roadmap

**Canonical plan:** [`TODO.md`](TODO.md)
**Canonical specification:** [`docs/specs/stagewarden-v3.md`](docs/specs/stagewarden-v3.md)
**Status:** documentation/specification redesign; runtime frozen pending user approval.

This file is intentionally a short navigation page. It is not a second backlog.

## Delivery sequence

1. P0 — baseline, gap analysis, decisions.
2. P1 — node-first specification and contracts.
3. P2 — documentation and policy rewrite.
4. User approval gate.
5. P3 — event/node stores, bottom-up scheduler, packet protocol, terminal stream, Node Knowledge Store, code-aware index, context/compaction, provider ownership.
6. P4 — acceptance matrix, wet-run validation, migration and legacy removal.

See [`TODO.md`](TODO.md) for every task, dependency, owner, gate and validation command.

## Design outcome

Stagewarden plans top-down and executes bottom-up. Default execution is serial. Parent-to-child work uses `WorkPacket`; child-to-parent completion uses `ResultPacket` and verified `EvidencePacket`. Node history, context and code retrieval live in the Node Knowledge Store. The terminal always shows active node, purpose, work, evidence and context state.
