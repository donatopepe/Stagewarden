# Agent runtime research — design input

**Status:** research reference, not current implementation contract.

Research into Codex CLI, Claude Code, KiloCode and Pi identified useful patterns. KiloCode remains runtime-supported as an adapter/reference boundary, not an authorization source:

- structured status cards are more useful than unstructured logs;
- model/provider identity and limits need explicit source and freshness;
- approvals and sandbox boundaries must be visible;
- usage and rate-limit data belong in runtime state;
- extensions need capability boundaries;
- compaction must preserve resumable task state;
- parallel agent output needs a deliberate UI rather than interleaved text.

Stagewarden v3 applies these findings through a different primary abstraction: the operational node tree.

## Mapping to v3

| Research signal | v3 response |
|---|---|
| status card | pinned tree/node/purpose banner |
| usage metadata | per-node context accounting |
| model discovery | provider/model handshake with user ownership |
| approvals | node work packet, permission and escalation gate |
| compaction | node-scoped automatic compaction with persisted summary |
| agent hierarchy | parent→child packet forwarding and child→parent evidence |
| parallel output | serial default; isolated opt-in streams and replay |
| extension capability | core/adapter/plugin/defer classification |

Do not use this file to infer command names or runtime APIs. See [`specs/stagewarden-v3.md`](specs/stagewarden-v3.md) and [`../TODO.md`](../TODO.md).
