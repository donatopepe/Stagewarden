# Stagewarden Handoff Summary

## Current phase
Node-first MVP implementation and OmniRoute-free validation. Automatic bounded continuation loop active every 5 minutes (`stagewarden-mvp-continue`, task `c05d5335`). Full v3 remains incremental.

## Product direction
- One operational tree of nodes.
- Top-down planning; bottom-up execution.
- Serial execution default; parallelism only opt-in for isolated leaves.
- Parent→child delegation through versioned `WorkPacket`.
- Child→parent return through validated `ResultPacket` and `EvidencePacket`.
- Lateral free-form messaging denied by default.
- Node purpose, context, history, evidence, status and ownership persist.
- Terminal always shows active tree/node/parent/purpose/work/status/context and real tool/file/test events; JSONL/replay required.

## Node Knowledge Store
Target RAG must contain:

- node-scoped context/history and compaction summaries;
- work packets, results, decisions, blockers, recovery;
- tool/file/test/provider evidence;
- code-aware index of files, modules, classes, procedures, functions, methods, tests and relations with path, lines, hash and freshness.

CodeGraph is auxiliary only. It cannot replace node context/history/evidence/ownership/retrieval.

## Documents rewritten
- `TODO.md` — sole plan/backlog.
- `docs/specs/stagewarden-v3.md` — canonical specification draft.
- `docs/architecture.md` — target architecture.
- `README.md`, `README_IT.md`, `ROADMAP.md`, `docs/README.md`.
- `AGENT_MANIFESTO.md`, `AGENT_POLICY.md`, `AGENT_POLICY.json`.
- `.pi/prompts/*.md` — packetized bottom-up node workflow.
- Legacy/reference docs and model examples aligned or marked non-authoritative.

## Latest bounded iteration
- Objective: validate Node Knowledge Store/index acceptance across context isolation, citation, Python symbols, compaction, freshness and file-read recovery.
- Baseline: no dedicated six-case matrix; partial node/file tests existed.
- Change: added Node Knowledge Store acceptance matrix covering node isolation, citations, code lines, compaction and stale/fresh reindex.
- Wet evidence: Node Knowledge/index matrix `6/6`; Node Knowledge/file/context/event suite `19/19 OK`; goal-loop/event/tools suite passed; OmniRoute free smoke `OmniRoute free route OK (auto/coding:free)`; `py_compile`, `git diff --check` passed. CodeGraph current `137 files / 3685 nodes / 12326 edges`.
- Current bounded sub-gate: Node Knowledge relation/freshness matrix `6/6`; targeted MVP now `104/104`; unified fixed-order runner remains `6/6`. Simulation `29/29`; full discovery `588/588 OK (5 skipped)`; CLI JSON `3/3`; OmniRoute direct smoke green; docs `17/17`, `0` link errors. External multi-node OmniRoute malformed/wrong-contract blocker remains fail-closed; full v3 approval remains pending.

## Full v3 approval gate
MVP runtime testing is authorized. User must still review v3 section 21 before full v3 extensions on:

- bottom-up exceptions;
- serial/parallel policy;
- RAG retention and backend;
- code-index language scope;
- prompt visibility;
- one active node vs multiplexer;
- dynamic child creation;
- repeated forwarding attempts;
- v2 superseded-document handling.

No runtime feature work before approval.

## Validation state
- Bounded objective: extend MutationJournal idempotency/recovery to `insert_text_file` without duplicate insertion or provider/model changes.
- Metric/threshold: insert mutation recovery cases pass at 100%; baseline `6` mutation journal/execution tests; post-change focused suite `72/72` green.
- Fixed cases: insert records in_flight; terminal completion recorded; repeated same action replays without modifying file; existing write/patch recovery remains green.
- Wet validation: focused suite `72 OK`; direct OmniRoute free smoke green; CodeGraph `137/3637/11744`; Markdown UTF-8/no-BOM and diff checks passed.

- Bounded objective: recover interrupted file mutations from `in_flight` journal entries exactly once, preserving serial execution, packet contracts, provider ownership, and existing node/event behavior.
- Metric/threshold: mutation-recovery cases pass at 100%; baseline `4/4` mutation journal/execution tests; post-change focused suite `69/69` green.
- Fixed cases: visible `in_flight`; no completed replay; one resumed write; terminal `completed`; recovery event; existing idempotency preserved.
- Wet validation: focused goal/event/knowledge/file/context suite `72 OK` in mutation-focused run; direct OmniRoute free smoke green this cycle; CodeGraph `137/3637/11744`; diff/Markdown checks passed.
- OmniRoute smoke failed contract this cycle: prose-wrapped `Stagewarden_Free_OK` instead of exact marker. External route blocker recorded; adapter/parser unchanged.
- OmniRoute retry returned valid JSON with wrong contract (`summary/keyDecisions/taskProgress/activeEntities`, no required `STAGEWARDEN_FREE_OK`); recorded external route-contract blocker. Adapter/parser unchanged and fail-closed.
- Metric/threshold: capsule round-trip/reopen acceptance cases pass at 100%; baseline `28` focused goal/knowledge/file/event tests; post-change `30` focused tests green.
- Fixed cases: capsule survives SQLite reopen; orchestrator writes capsule on node event; reopen restores non-terminal status, cycle id and checkpoint; node scope remains isolated.
- Wet validation: focused suite `30 OK`; direct OmniRoute free smoke `OmniRoute free route OK (auto/coding:free)`; CodeGraph `137/3614/11615`; diff/Markdown checks passed.
- Metric/threshold: cycle-state acceptance cases green at 100%; baseline `24` focused goal/event/knowledge tests; post-change `26` focused tests green.
- Fixed cases: default cycle state serializes; cycle/context revisions survive projection; cycle-start/checkpoint events include purpose and cycle metadata; budget exhaustion blocks instead of looping indefinitely.
- Wet validation: `python3 -m unittest tests.test_goal_loop_orchestrator tests.test_event_stream tests.test_node_knowledge -q` → `26` tests, `OK`; CodeGraph synced at `137 files / 3606 nodes / 11557 edges`; `git diff --check` passed.
- Previous provider ownership enforcement remains in place; no provider/model selection changed and no parallelism enabled.
- Metric/threshold: fixed policy/router/executor/CLI cases pass at 100%; focused policy result `26/26` green after TDD change. Baseline before edit: `18/18` existing router/model-policy cases green, while manual mode was not wired to router.
- Fixed cases: manual preferred provider beats task heuristic; auto mode preserves heuristic; manual variants and fallback stay blocked; explicit authorization remains usable; CLI/report reflect state; executor performs no second provider call.
- CodeGraph current: 137 files, 3634 nodes, 11716 edges; documentation-only protocol alignment, index unchanged.
- Wet validation: focused executor/router/model suites passed; integration suite passed `90` with `1` intentional skip before final additions; direct `scripts/test_omniroute_free.sh` returned `OmniRoute free route OK (auto/coding:free)`.
- MVP node/RAG/packet test suite: `24` tests, `1` intentional live skip, green after implementation.
- Goal-loop/OmniRoute adapter subset: `21` tests, `1` intentional live skip, green.
- Direct OmniRoute free adapter smoke returns `FREE_OK`.
- Full live node-loop attempt: blocked after initial nodes because free model returned malformed/truncated JSON; fail-closed behavior preserved.
- Context-aware file-read MVP: chunk offsets, complete reconstruction beyond model context, automatic prompt compaction under configured budget, persistent SQLite checkpoint/resume and content-hash validation.
- Terminal JSONL event stream/replay MVP passes; `stagewarden events --json` and `stagewarden events replay --json` available.
- Executor emits tool result, file chunk, file complete and context compaction events.
- Node Knowledge Store connections now close explicitly; focused suite no longer emits SQLite ResourceWarning.
- File mutation idempotency MVP records stable mutation keys, completed status and safe replay events for write and patch actions; journal is inspectable via `mutations` CLI.
- Provider/model ownership policy MVP is explicit and persisted; manual router/executor enforcement now blocks task heuristics, automatic variants, and silent provider/account fallback unless authorized. `model policy` CLI and `model limits --json` expose policy. Baseline capability list includes `model policy`.
- `allow_paid_provider` now enforces catalog-aware routing: paid/unknown-priced providers skipped without authorization; explicit authorization keeps candidates. Policy propagates through Agent/model views and WorkPacket.
- Goal-loop tree validator enforces one `root.scope`, known parent/dependency edges, root dependency absence and cycle rejection; blueprint now assigns explicit parent edges.
- Ready-node selection is deterministic by parent depth then `node_id`; dependency completion remains mandatory and execution remains serial.
- ResultPacket edge MVP is parent-scoped with evidence list; successful child results are forwarded only to declared parent through typed result message.
- EventStream replay now projects cycle_id, cycle_phase, context_revision and last_checkpoint from node snapshots, plus context_compaction metadata and mutation_recovery key/status.
- `file_chunk` events now record available input tokens, prompt chars before/after and auto-compaction state.
- `context_compaction` events now record available input tokens, max_chars and prompt chars before/after.
- Goal-loop control path rejects lateral/unknown sender-target messages; only declared parent↔child edges can append node message state.
- WorkPacket delegation fails closed for non-root nodes without known parent or acceptance criteria; valid packet carries parent edge, dependencies and acceptance contract.
- Canonical formal protocol stack is now documented consistently: Markdown, JSON/Schema, Tree/DAG, FSM, invariants/gates, NodeExecutionCapsule, JSONL and Node Knowledge Store.
- `NodeExecutionCapsule` persistence and controlled orchestrator reopen are implemented.
- File mutation `in_flight` recovery is implemented. Non-file mutating actions and broader pause/resume crash recovery remain open.
- Event commands are present in command catalog/help metadata; node-filtered event/replay views are available, with `EventStream.follow` for live polling.
- Documentation UTF-8/no-BOM and diff checks remain required.
- Live multi-node OmniRoute free remains blocked by repeated malformed/truncated JSON after initial nodes; direct smoke now also returned prose-wrapped success marker. Parser/adapter remain fail-closed.

## Current bounded evidence
- Status CLI fix: updated one stale test expectation from automatic routing to persisted manual provider policy; runtime policy unchanged.
- Unified runner: `python3 scripts/run_unified_validation.py --timeout 1800` → `6/6` gates green; bounded report tailing preserves JSON evaluation.
- Node Knowledge relation gate: `python3 -m unittest tests.test_node_knowledge -q` → `6/6 OK` including module/import/call/read/write relations, unchanged freshness and changed-version replacement. Targeted aggregate → `104/104 OK`.
- Full discovery: `/tmp/full-unittest-after-status-20260923.log` → `588` tests, `OK (skipped=5)`.
- CLI smoke: `baseline --json`, `model limits --json`, `events replay --json` all exit `0`; JSON output valid. `scripts/test_omniroute_free.sh` → `OmniRoute free route OK (auto/coding:free)`.
- Documentation/link audit: `17` Markdown files checked, `0` link errors, UTF-8/no-BOM pass.
- CodeGraph after runner and index additions: `139 files / 3723 nodes / 12503 edges`, up to date.
- Provider suspension sub-gate: `python3 -m unittest tests.test_agent_integration.AgentIntegrationTests.test_agent_resumes_suspended_network_session_from_persisted_handoff tests.test_agent_integration.AgentIntegrationTests.test_agent_resumes_after_token_reset_from_persisted_handoff -v` → `2/2 OK`.
- Regression targeted aggregate: Agent/executor/router/model-policy/policy-doc tests → `94` tests, `OK (skipped=1)`.
- Simulation wet total: `test_total_run_is_wet_and_fail_closed` → `1/1 OK`.
- CodeGraph: `137 files / 3685 nodes / 12331 edges`, up to date. `git diff --check`, JSON validation and `py_compile` pass.
- Remaining known failure: interactive status compatibility expects automatic chatgpt display while default persisted policy is manual; no policy change made.

## Next action
Extend event stream with richer tool/file checkpoint events and live multiplexer UI. Keep all future work in `TODO.md`.
