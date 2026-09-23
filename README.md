# Stagewarden

Stagewarden is a governed coding-agent runtime built around an operational tree of nodes.

**Current status:** v3 architecture and documentation are being re-engineered. Runtime implementation is frozen until the v3 specification is approved. The existing Python runtime remains legacy evidence, not the target architecture.

## Product model

Stagewarden does not treat work as an unstructured pool of agents. It treats work as a tree:

```text
root purpose
└── parent purpose
    ├── leaf work packet -> evidence
    └── leaf work packet -> evidence
        ^ result aggregation
    parent result
^ root decision
```

- Planning is top-down.
- Execution is bottom-up.
- Serial execution is default.
- Parallelism is opt-in and limited to isolated, independently verifiable leaves.
- A parent delegates through a typed `WorkPacket`.
- A child returns a typed `ResultPacket` containing verifiable `EvidencePacket` records.
- Lateral free-form communication is denied by default.
- A node cannot complete without acceptance evidence.

## Formal protocol stack

Stagewarden deliberately uses small set of formal structures:

```text
Markdown                 rules/specification
JSON + JSON Schema       WorkPacket/ResultPacket/EvidencePacket/tool actions
tree + DAG                decomposition and dependencies
FSM                       node/cycle lifecycle
invariants + gates       fail-closed completion
NodeExecutionCapsule     node context, cycle checkpoint and recovery
JSONL                     append-only audit and replay
SQLite Node Knowledge    node memory and code-aware retrieval
```

Prompt is inference input, not operational source of truth. No implicit blackboard, lateral messaging, or legacy parallelism.

## What user sees

Terminal output must always answer:

1. Which node is working?
2. What is that node's purpose?
3. What work packet did it receive?
4. What is it doing now?
5. Which files, tools, and tests are involved?
6. How much context remains?
7. Which evidence has been produced?
8. Why is it waiting, blocked, delegated, or complete?

The v3 terminal contract includes a persistent node banner, purpose reminders after resume/compaction, live activity events, JSONL events, and replay.

## Node Knowledge Store

The RAG becomes an operational Node Knowledge Store. It stores, with node scope and provenance:

- node purpose, work packets, results, decisions, blockers, and recovery;
- context snapshots and compaction summaries;
- tool, file, test, and provider evidence;
- files, modules, classes, procedures, functions, methods, tests, and code relations;
- source path, line range, content hash, freshness, and sensitivity.

CodeGraph can help inspect symbols, but it is only an auxiliary development index. It is not the source of truth for node context, history, evidence, ownership, permissions, or retrieval.

## Context and model ownership

Context window, input budget, output reserve, overhead, safety margin, measurement method, source, and freshness are first-class data.

Automatic compaction is core node behavior. It compacts the active node context before the selected provider/model limit is exceeded, persists and validates the summary, and never silently changes provider, model, account, or cost policy.

File reading is context-aware: Stagewarden reads files in chunks sized from remaining context. If the next chunk does not fit, it compacts the active context and resumes from a persisted offset. A file may be read completely even when it exceeds model context: full content stays outside the prompt in persistent cache/evidence and is reconstructed chunk by chunk without loss.

Provider, model, account, credentials, quotas, costs, and fallback authorization belong to the user. Stagewarden may display and enforce them; it must not silently choose a paid service or replace the selected model.

## Documentation

- [`TODO.md`](TODO.md) — single project plan and only backlog.
- [`docs/specs/stagewarden-v3.md`](docs/specs/stagewarden-v3.md) — canonical specification draft.
- [`docs/architecture.md`](docs/architecture.md) — node-first architecture and trust boundaries.
- [`AGENT_MANIFESTO.md`](AGENT_MANIFESTO.md) — operating principles.
- [`AGENT_POLICY.md`](AGENT_POLICY.md) — formal policy.
- [`AGENTS.md`](AGENTS.md) — agent continuity protocol.
- [`AGENT_HANDOFF.md`](AGENT_HANDOFF.md) — current handoff.
- [`docs/README.md`](docs/README.md) — documentation map.

Previous v2 specification is retained only as a superseded record: [`docs/specs/stagewarden-v2.md`](docs/specs/stagewarden-v2.md).

## Current implementation boundary

No v3 runtime feature is being implemented in this phase. Do not infer the v3 contract from current modules such as the legacy goal loop, router, project handoff, message bus, or `DesignRag`.

The migration plan is:

1. event and node state contracts;
2. tree validation;
3. serial bottom-up scheduler;
4. work/result/evidence packets;
5. observable terminal event stream;
6. Node Knowledge Store and code-aware index;
7. per-node context accounting and compaction;
8. controlled provider/model ownership;
9. legacy migration and removal of unsafe parallel/free-message paths.

## Install legacy runtime for inspection

```bash
python3 -m pip install -e .
```

The installed CLI is the current legacy runtime until the v3 approval gate is closed. Feature work must follow [`TODO.md`](TODO.md).

## Validation for documentation phase

```bash
codegraph status .
codegraph sync .
git diff --check
python3 - <<'PY'
from pathlib import Path
for path in Path('.').rglob('*.md'):
    data = path.read_bytes()
    data.decode('utf-8')
    assert not data.startswith(b'\xef\xbb\xbf'), path
print('markdown UTF-8/no-BOM: OK')
PY
```
