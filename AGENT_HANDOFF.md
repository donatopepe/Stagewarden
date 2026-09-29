# Agent Handoff

## Current objective
Record one-hundred-sixty-second bounded iteration: TDD fix of a real, reachable defect — `MemoryStore.load` raised on corrupt persisted memory state and aborted the evidence path, because `record_external_io_evidence` and `record_system_evidence` call it with no error handling — plus `git_head` reconcile after external commit `76cbb64 -> eed8e76`. Preserve task-scoped node UUID, capsule isolation, node-scoped recovery, same-root ownership, serial execution, manual provider/model ownership and fail-closed OmniRoute handling. No further runtime scope is authorized until user decision gate or approved defect. Automatic bounded continuation loop remains active every 5 minutes (`stagewarden-mvp-continue`, task `c05d5335`). Full v3 extensions remain approval-gated.

## Current state
- Checkout: `/home/public/Stagewarden`, branch `main`; sole main worktree; HEAD `eed8e76c8fc2b4fda1379bc5dd5d5a77dafb0366` (external commit captured the cycle-162 fix; `.stagewarden_handoff.json` `git_head` reconciled in cycle 162).
- CodeGraph synced/current: 140 files, 3825 nodes, 13116 edges.
- Decision gate: unresolved TODO items are user approval for v3, approved extensions/subagents, and migration/compatibility; no runtime item selected.
- Baseline `/tmp/node-context-uuid-scope-baseline.log` = `1/3`; task-scoped UUID plus capsule-isolation TDD now green.
- `PlanStep` and goal-loop `NodeState` use deterministic task-scoped UUIDs; model context telemetry/prompt, WorkPacket, capsule, JSONL event and replay carry `node_uuid`; capsule load filters UUID, cache scope explicitly `node_uuid`.
- Wet evidence: **cycle 162 fixed a real reachable defect in persisted-state recovery, and the cycle-161 case-list self-check paid off immediately.** The probe `required` that every case label resolve to a real callable; it caught THREE method names I had invented (`MemoryStore.retrieve_recent`, `HandoffManager.save`, `HandoffManager.load`) BEFORE any finding was reported and aborted the run. Two more harness errors followed and were fixed: a stale `retrieve_recent` case body, and the false assumption that `HandoffManager` is a persisted-state reader when it is actually a model invoker (the persisted handoff is `ProjectHandoff`). Without that check I would have reported 3-4 phantom defects and built a cycle narrative on them. Defect, measured at the REAL caller: `record_external_io_evidence` and `record_system_evidence` in `stagewarden/tool_reports.py` both call `MemoryStore.load(config.memory_path)` with NO error handling, and `load` did `loads_text(...).get(...)` unguarded. Baseline 6 uncaught per caller, 12 total: not-JSON/empty/truncated -> `JSONDecodeError`; top-level list/string/number/null -> `AttributeError: no attribute 'get'`; `attempts` not a list -> `AttributeError: 'str' object has no attribute 'setdefault'`; and a MISSING file was already fine because it returns an empty store. So the contract was already 'missing degrades to empty' — corrupt simply crashed. Change, single variable: the body moved to `_load_payload`, and `load()` wraps it in one fail-closed boundary catching OSError, UnicodeDecodeError, TypeError, ValueError, KeyError and AttributeError, returning an empty store — the same signal a missing file already produced. It also requires a dict root, skips non-dict entries inside `attempts`/`tool_transcript`, and guards the `failures_by_step`/`models_by_step` maps against non-dict values. No change to the saved format; no provider/model/fallback/routing/scheduler/parallel change. TDD RED `10 failed, 9 passed` -> GREEN `9 passed, 10 subtests passed`; post-fix the real callers fail closed on 22/22 cases (11 x 2 callers) and a valid memory file still round-trips, both asserted by controls. Trade-off recorded honestly: a corrupt memory file now yields an EMPTY store, so that workspace's attempt/transcript history is dropped rather than recovered or surfaced. That is deliberate — it matches the pre-existing missing-file behaviour and keeps the evidence path alive — but it IS data loss and is recorded rather than hidden. Measured negative, NOT claimed as a defect: the probe still reports 6 cases in `record_attempt` (list/dict values -> `TypeError: unhashable`) and `recent_attempts` (non-int limit -> `TypeError`). Reachability checked: every call site passes internally derived values (`step.id`, `model`, integer `iteration`, literal strings) and `recent_attempts(step_id, limit=1)` passes a literal int, so a list or dict can never arrive from a model. Like cycle 156's `mutation_key` finding, this is unreachable in production, so it is recorded as a measured negative and not fixed. Tests added in `tests/test_memory.py`: `test_load_degrades_to_empty_store_on_corrupt_persisted_json` (10 subtests) and `test_load_missing_and_valid_files_behave_as_before` (controls). Regression: priority suite `260 passed, 204 subtests passed in 14.17s`; full suite with live flag `684 passed, 4 skipped, 204 subtests passed in 351.87s (0:05:51)`, 0 failures (was 682); live smoke `OmniRoute free route OK (auto/coding:free)` exit 0; unified validation `6/6` PASS exit 0; gate `/tmp/stagewarden-bounded-iteration-gate-2026-09-28gy.log` = `5/5`. Evidence `/tmp/stagewarden-memorystore-load-2026-09-28gy.log`; dual-self-check probe `/tmp/stagewarden_persisted_probe.py`. Prior classes: 147-152 persisted/external JSON; 153-155 action required/optional field types; 156 sequence element types; 157 non-object top-level payload; 158 pi-backend node contract; 159 test-integrity; 160 guard-pinning; 161 primitive-probe negative; 162 MemoryStore persisted state. Test count 654 -> 684 across cycles 145-162 with zero regressions. Environment in `/tmp/stagewarden-pytest-venv` (`pytest 9.1.1`), regenerate with `python3 -m venv --system-site-packages /tmp/stagewarden-pytest-venv && /tmp/stagewarden-pytest-venv/bin/python -m pip install pytest`. `main`/sole worktree, CodeGraph `140/3825/13116` current, JSON waiting/HEAD aligned.
- Open proposal, not applied: the probe is good fail-closed regression coverage and could become a permanent test under `tests/`. It was deliberately NOT added because no defect requires it and it would create a new test file with no justifying TDD change; it needs explicit authorization.
- Cycles 145-154 narrative: 145 restored the pytest environment; 146 verified every validation artifact wet; 147 fixed the exception boundary in `scripts/run_model_omniroute.py`; 148 fixed the nested `operations` shape in `stagewarden/executor.py` `_read_tool_operations` (both copies); 149 fixed `load_node_execution_capsule` to degrade to the `KeyError` contract `_restore_node_capsules` already catches; 150 fixed `search` and `code_relations` with the shared `_decode_source` helper; 151 fixed `code_search` and closed the `json.loads` audit; 152 closed that whole class with a runnable probe reporting 0 unguarded exceptions and no change; 153 fixed wrong-typed file-action fields; 154 replaced those per-file guards with one schema-driven generic guard covering all 33 actions. Test count 654 -> 671, zero regressions. Next queued item: matrix B, wrong-typed OPTIONAL action fields (70 uncaught across 15 field names).
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.
- Multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed blockers. Full v3 approval remains pending.

- Documentation/specification rewrite remains baseline; canonical plan is `TODO.md`.
- MVP runtime changes now exist in `stagewarden/goal_loop_orchestrator.py`, `stagewarden/goal_loop_views.py`, and `stagewarden/node_knowledge.py`.
- Goal loop executes one ready node at a time, emits node/parent/purpose/work events, builds WorkPacket and ResultPacket, and supports `STAGEWARDEN_GOAL_LOOP_BACKEND=omniroute`. Live multi-node OmniRoute remains blocked on repeated malformed/truncated, wrong-contract and prose-wrapped output; adapter remains fail-closed.
- Each node now carries bounded local-cycle state: `cycle_id`, `cycle_phase`, `context_revision`, `last_checkpoint`, and cycle budgets; cycle start/checkpoint events are emitted in JSONL. Serial execution unchanged.
- `NodeExecutionCapsule` is persisted node-scoped in Node Knowledge Store after node events and restored on orchestrator reopen; capsule contains cycle state, checkpoint, budget, status, purpose and packet reference.
- File mutation recovery now recognizes `in_flight` journal entries, emits `mutation_recovery`, resumes execution once, and appends terminal status without duplicating the in-flight marker.
- `allow_paid_provider` is enforced at `ModelRouter` catalog boundary: paid/unknown-priced providers are skipped without authorization; persisted policy propagates through `Agent`, model views and goal-loop WorkPacket.
- Goal-loop tree validator enforces one `root.scope`, known parent/dependency edges, root dependency absence and cycle rejection before capsule restore; blueprint now assigns explicit parent edges.
- Ready-node selection is deterministic by parent depth then `node_id`; dependency completion remains mandatory and execution remains serial.
- ResultPacket edge MVP is parent-scoped with evidence list; successful child results are forwarded only to declared parent through typed result message.
- EventStream replay now projects cycle_id, cycle_phase, context_revision and last_checkpoint from node snapshots, plus context_compaction metadata and mutation failure/recovery/replay key/status.
- `file_chunk` events now record available input tokens, prompt chars before/after and auto-compaction state for context-aware replay.
- `context_compaction` events now record available input tokens, max_chars and prompt chars before/after.
- Goal-loop control path rejects lateral/unknown sender-target messages; only declared parent↔child edges can append node message state.
- WorkPacket delegation fails closed for non-root nodes without known parent or acceptance criteria; valid packet carries parent edge, dependencies and acceptance contract.
- Child completion forwards exactly one typed result message to declared parent with work ID and evidence list.
- Blocked node requeue emits bounded `node_retry` event with retry_count/max_retries; retry cap remains fail-closed.
- `insert_text_file` now participates in MutationJournal in_flight/completed recovery and completed replay.
- Canonical formal protocol stack documented across TODO, architecture, v3 spec, README and README_IT: Markdown, JSON/Schema, Tree/DAG, FSM, invariants/gates, NodeExecutionCapsule, JSONL and Node Knowledge Store.
- Node Knowledge Store persists SQLite node context/events and indexes Python classes/functions with source lines.
- OmniRoute adapter unit path passes; live route is available through `scripts/run_model_omniroute.py` but full live multi-node run is currently blocked by free-model malformed/truncated JSON output after initial nodes.
- Context-aware file reading now persists checkpoints in Node Knowledge Store: session, content hash, chunk offsets, next offset, completion status and reconstruction after reopen.
- `read_file_chunk` caps chunk by remaining budget and auto-compacts when no budget remains; `read_file_complete` reconstructs full file outside model prompt and returns persistent content reference.
- Terminal JSONL event stream and deterministic replay MVP now exist in `stagewarden/event_stream.py`; CLI commands `events` and `events replay` expose them.
- Executor now emits JSONL events for tool results, file chunks, complete-file reads and automatic context compaction.
- Node Knowledge Store connections now close explicitly and via destructor safety path; resource leak warnings removed in focused suite.
- `events` and `events replay` are now registered in command catalog/help metadata.
- Event stream/replay supports node filtering via `events node <id>` and `events replay <id>`.
- `EventStream.follow(node_id)` now exposes ordered node-filtered events for live/polling multiplexer consumers.
- File mutation idempotency MVP now exists via `MutationJournal`: completed `write_file` and `apply_patch` actions replay safely by stable key and emit `mutation_replay` event.
- Model selection policy MVP now persists `selection_mode`, `allow_provider_fallback`, and `allow_paid_provider`; fallback is blocked by default.
- CLI `model policy` now shows/updates ownership and fallback authorization explicitly; `model limits --json` includes selection policy.
- Capability baseline now includes `model policy` in provider/model control.
- Mutation journal inspection is available through CLI `mutations`, `mutations completed`, and `mutations failed`.
- Full v3 remains incremental; richer live multiplexer/UI remains open. Unified runner reports bounded stdout/stderr tails while evaluating complete machine-readable output.
- Provider suspension fix: transient network and usage-limit failures are classified before manual fallback denial; fail-closed ownership remains unchanged and resumable handoff persists `waiting`.
- Status CLI expectation now matches persisted manual policy; full discovery is green at 588 tests with 5 intentional skips.

## Recent changes
- `TODO.md`: single re-engineering/MVP plan; MVP node/RAG/OmniRoute tasks marked.
- `stagewarden/goal_loop_orchestrator.py`: serial bottom-up execution, visible purpose events, WorkPacket/ResultPacket, OmniRoute free backend.
- `stagewarden/node_knowledge.py`: SQLite Node Knowledge Store, node-scoped retrieval, same-root code-index ownership, Python code index, module/import/call/read/write relations, file version/freshness metadata and deterministic compaction helper.
- `stagewarden/tools/files.py`: context-aware chunk iterator and complete-file reconstruction boundary.
- `stagewarden/executor.py`: new read actions, model context budget, automatic chunk capping/compaction and persistent complete-file references; provider suspension classification now preserves resumable `waiting` state.
- Unified runner separates full evaluator stdout from bounded report tails; no runtime/provider/model policy mutation.
- Code index remains node-scoped; normalized roots have one node/tree owner; relation rows carry source path/lines/hash/freshness and stale symbols are removed on changed reindex.
- Goal loop validates mode at boundary; only `mock`, `auto`, `pi` accepted and all paths execute one ready node serially.
- Context events now carry provider/model, context window/input limit and reserved-output/safety-margin metadata alongside node and available-token fields.
- Replay projects context identity metadata; event redaction tests ensure API-like values remain absent while node filters remain scoped.
- Mutation family audit confirms completed replay, in-flight recovery and failed terminal tests remain present for all remaining action families; runtime unchanged.
- Mutation replay/recovery events now project key/status in node replay while redaction and node filtering remain scoped.
- Pause/resume matrix composes existing capsule, file checkpoint/hash and provider waiting→resume contracts; no new pause/cancel API introduced.
- Context selection matrix uses explicit provider identity only; no router selection, fallback or ownership policy mutation.
- Context budget boundary matrix confirms zero available input, unknown catalog limits and exact boundary compaction remain fail-closed/observable.
- Retry checkpoint matrix confirms retry event fields, capsule persistence/reopen and bounded retry ceiling; no retry algorithm change.
- `tests/test_file_read_recovery.py`: reopen/resume, offset integrity and content-hash recovery tests.
- `stagewarden/event_stream.py`: append-only redacted JSONL events and replay projection.
- `tests/test_event_stream.py`: redaction and replay tests.
- `tests/test_trace_cli.py`: status/default-policy compatibility and CLI smoke coverage.
- `tests/data/unified_validation_matrix.json`, `scripts/run_unified_validation.py`, `scripts/check_unified_validation.py`: fixed-order scenario manifest, bounded runner and docs/diff hygiene checker.
- `tests/test_node_knowledge.py`: node isolation, same-root ownership, capsule, citation, code relations/freshness, and compaction regressions.
- `tests/test_goal_loop_orchestrator.py`: three-case serial execution-mode gate; unsupported parallel modes rejected at orchestrator boundary.
- `tests/test_context_file_reading.py`: three-case provider/node context-budget identity matrix for budget, file-chunk and compaction events.
- `tests/test_event_stream.py`: three-case metadata redaction/replay/node-filter matrix.
- `tests/test_mutation_execution.py`: twelve-case remaining mutation family audit across range, encoding, path and permission families; three-case mutation replay/recovery safety matrix.
- `tests/test_goal_loop_orchestrator.py`, `tests/test_file_read_recovery.py`, `tests/test_agent_integration.py`: three-case pause/resume checkpoint safety matrix.
- `tests/test_context_file_reading.py`: three-case explicit cheap/chatgpt context-provider selection matrix and three-case zero/unknown/exact-boundary budget matrix.
- `tests/test_goal_loop_orchestrator.py`: three-case retry checkpoint/replay safety matrix; retry_count/max_retries now persist in `NodeExecutionCapsule`.
- `tests/test_executor_event_stream.py`: tool/chunk/compaction event coverage.
- `stagewarden/mutation_journal.py`, `tests/test_mutation_journal.py`, `tests/test_mutation_execution.py`: idempotent mutation journal and recovery tests for all 16 declared mutation actions.
- `tests/test_modelprefs.py`: manual model ownership and fallback policy round-trip/validation tests.
- `tests/test_model_policy_cli.py`: explicit policy CLI show/update/invalid-input tests.
- `tests/test_goal_loop_orchestrator.py`, `tests/test_node_knowledge.py`: MVP acceptance tests.
- `docs/specs/stagewarden-v3.md`: new canonical node-first specification.
- `docs/specs/stagewarden-v2.md`: reduced to superseded pointer.
- `docs/architecture.md`: rewritten for tree/node scheduler, packets, Node Knowledge Store, code-aware index, event terminal and trust boundaries.
- `README.md`, `README_IT.md`, `ROADMAP.md`, `docs/README.md`: rewritten as product/navigation docs; roadmap now points to TODO only.
- `AGENT_MANIFESTO.md`, `AGENT_POLICY.md`, `AGENT_POLICY.json`: aligned to bottom-up/packet/evidence/node/RAG/terminal/context ownership rules; machine-readable policy now includes required author/framework/principle IDs.
- `docs/source_references.md`, `docs/status_research.md`, `examples/stagewarden_settings.example.json`: restored required KiloCode research markers and safe example environment/command references; no secrets.
- `.pi/prompts/*.md`: rewritten to prohibit implicit delegation/lateral messaging and define WorkPacket/ResultPacket flow.
- `models/*`, `examples/stagewarden_settings.example.json`, `docs/*` references: marked legacy/reference or aligned to v3.

## Important files
- `TODO.md`: only project plan/backlog.
- `docs/specs/stagewarden-v3.md`: canonical product contract pending approval.
- `docs/architecture.md`: target architecture.
- `stagewarden/goal_loop_orchestrator.py`: legacy parallel goal loop; must be redesigned, not treated as v3 behavior.
- `stagewarden/rag.py`: legacy DesignRag; target is Node Knowledge Store.
- `stagewarden/project_handoff.py`: legacy recovery/audit state; target runtime state moves to node/event stores.
- `stagewarden/project/`: legacy role/tree views; source evidence for migration.
- `stagewarden/executor.py`: legacy prompt/tool executor; target must attach work/context/evidence to nodes.
- `.pi/prompts/`: prompt references aligned with target model.

## Technical decisions
- Decision: tree is primary work unit.
  - Reason: reduces multi-agent dispersion and makes scope, purpose, context, evidence and ownership observable.
  - Trade-off: scheduler and persistence become explicit architectural components.
- Decision: top-down planning, bottom-up execution.
  - Reason: leaves produce evidence before parents aggregate or delegate further work.
  - Trade-off: parent latency increases; this is accepted for traceability.
- Decision: serial by default; isolated parallel leaves opt-in only.
  - Reason: interleaved multi-agent work is hard to follow and risks conflicts/cost duplication.
  - Trade-off: lower peak throughput for safer supervision.
- Decision: parent→child `WorkPacket`; child→parent `ResultPacket` + `EvidencePacket`; lateral messages denied by default.
  - Reason: forwarding and return paths become typed, auditable and bounded.
- Decision: Node Knowledge Store replaces DesignRag as target RAG concept and includes node history plus code-aware index.
  - Reason: CodeGraph alone lacks purpose, context history, evidence, ownership, freshness and retrieval scope.
- Decision: terminal purpose/activity observability is mandatory.
  - Reason: user must always know node identity, purpose and current work.
- Decision: provider/model/context ownership remains explicit and user-controlled.
  - Reason: context size and provider/model/cost are essential user responsibilities.

## Validation evidence
- Objective: verify marker consistency latest rerun after latest green gate.
- Metric/threshold: fixed marker matrix `3/3`.
- Baseline: `/tmp/current-marker-consistency-baseline-latest.log` was `3/3`; reran docs, JSON, diff, OmniRoute and replay regression.
- Wet validation: marker `3/3`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; replay regression `1/1`; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: close MutationJournal recovery metadata safety acceptance.
- Metric/threshold: fixed safety matrix `3/3`.
- Baseline: `/tmp/next-mutation-safety-baseline.log` was `3/3` metadata declarations, but no fresh focused safety gate had been recorded for current handoff.
- Wet validation: safety matrix `3/3`; mutation/journal/event suite `61/61 OK`; docs `17/17`; handoff JSON and `git diff --check` pass; direct OmniRoute smoke green; CodeGraph `139/3760/12729`, up to date.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: verify marker cleanup final consistency after latest green gate.
- Metric/threshold: fixed cleanup matrix `3/3`.
- Baseline: `/tmp/current-marker-cleanup-final-baseline.log` was `3/3`; reran docs, JSON, diff, OmniRoute and replay regression.
- Wet validation: cleanup `3/3`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; replay regression `1/1`; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: verify final marker consistency after latest green gate.
- Metric/threshold: fixed final-marker matrix `3/3`.
- Baseline: `/tmp/current-marker-final-final-baseline.log` was `3/3`; reran docs, JSON, diff, OmniRoute and replay regression.
- Wet validation: final-marker `3/3`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; replay regression `1/1`; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: verify latest marker cleanup consistency after latest green gate.
- Metric/threshold: fixed cleanup consistency matrix `3/3`.
- Baseline: `/tmp/current-marker-cleanup-baseline.log` was `3/3`; reran docs, JSON, diff, OmniRoute and replay regression.
- Wet validation: cleanup `3/3`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; replay regression `1/1`; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: close final current-marker consistency after latest green gate.
- Metric/threshold: fixed final consistency matrix `3/3`.
- Baseline: `/tmp/current-todo-marker-final-baseline-2.log` was `3/3`; reran docs, JSON, diff, OmniRoute and replay regression.
- Wet validation: final consistency `3/3`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; replay regression `1/1`; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: verify current TODO marker/evidence consistency after latest green gate.
- Metric/threshold: fixed TODO consistency matrix `3/3`.
- Baseline: `/tmp/todo-current-marker-baseline.log` was `3/3`; reran docs, JSON, diff, OmniRoute and replay regression.
- Wet validation: TODO consistency `3/3`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; replay regression `1/1`; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: rerun current objective/evidence consistency after Event replay recovery closure.
- Metric/threshold: fixed consistency matrix `3/3`.
- Baseline: `/tmp/current-objective-evidence-final-baseline.log` was `3/3`; reran docs, JSON, diff, OmniRoute and replay regression.
- Wet validation: consistency `3/3`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; replay regression `1/1`; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: rerun current objective/evidence consistency after Event replay recovery closure.
- Metric/threshold: fixed objective/evidence matrix `3/3`.
- Baseline: `/tmp/current-handoff-objective-final-baseline.log` was `3/3`; reran docs, JSON, diff, OmniRoute and replay regression.
- Wet validation: consistency `3/3`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; replay regression `1/1`; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: verify current objective/evidence consistency across TODO, handoffs and JSON state.
- Metric/threshold: fixed objective/evidence matrix `3/3`.
- Baseline: `/tmp/current-handoff-objective-baseline.log` was `3/3` after prior refresh; reran docs, JSON, diff, OmniRoute and replay checks.
- Wet validation: consistency `3/3`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; replay regression `1/1`; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: reconcile current handoff metadata after Event replay recovery closure.
- Metric/threshold: fixed consistency matrix `3/3`.
- Baseline: `/tmp/current-event-handoff-baseline.log` was `3/3` after prior refresh; reran marker/objective/HEAD/CodeGraph and focused replay checks.
- Wet validation: consistency `3/3`; replay regression `2/2`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: close Event replay recovery lifecycle metadata with fixed node/retry assertions.
- Metric/threshold: fixed replay recovery closure matrix `3/3`.
- Baseline: `/tmp/event-replay-recovery-closure-baseline.log` behavior `3/3`, but closure acceptance metadata had no dedicated regression.
- TDD change: added recovery closure test for in-flight appearance, clear-on-recovery, recovered status, node scope and retry denial.
- Wet validation: closure `3/3`; targeted event/executor/adapter `15/15` with 1 skip; targeted MVP `121/121`; unified runner `6/6`; full discovery `610/610` with 5 skips; CLI `3/3`; docs `17/17`; direct OmniRoute smoke green; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: formalize Node Knowledge code-index retrieval scope without broadening retrieval semantics.
- Metric/threshold: fixed code retrieval scope matrix `2/2`.
- Baseline: `/tmp/next-node-knowledge-code-scope-baseline.log` was `1/2`; ancestor symbol leaked into child query after separate node indexes covered same root.
- TDD change: added isolated ancestor/child code-index regression using separate node roots; no runtime retrieval broadening.
- Wet validation: code scope `2/2`; Node Knowledge suite `8/8`; targeted MVP `120/120`; unified runner `6/6`; full discovery `609/609` with 5 skips; CLI `3/3`; docs `17/17`; direct OmniRoute smoke green; CodeGraph `139/3759/12725`, up to date; HEAD `9997681eeabd3dc3b3295f13df9855588022cde4`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: formalize Node Knowledge retrieval scope acceptance without broadening retrieval semantics.
- Metric/threshold: fixed retrieval scope matrix `2/2`.
- Baseline: `/tmp/next-mvp-node-knowledge-baseline.log` behavior probe `2/2`, but no explicit automated test covered direct node scope and child non-leakage.
- TDD change: added isolated ancestor/child retrieval regression test; runtime semantics unchanged.
- Wet validation: retrieval matrix `2/2`; Node Knowledge suite `7/7`; targeted MVP `119/119`; unified runner `6/6`; full discovery `608/608` with 5 skips; CLI `3/3`; docs `17/17`; direct OmniRoute smoke green; CodeGraph `139/3758/12719`, up to date; HEAD `7fea4ebebd1effc3888f26c967b7e8700bd5f662`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: maintain synchronized TODO/handoff evidence after latest green MVP validation.
- Metric/threshold: fixed consistency matrix `3/3`.
- Baseline: `/tmp/handoff-reconciliation-consistency-baseline.log` was already `3/3` after previous refresh; reran docs, JSON, diff, OmniRoute and CLI replay checks.
- Wet validation: consistency `3/3`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; CLI replay regression `2/2 OK`; CodeGraph `139/3757/12713`, up to date; HEAD `1d04548c725e4f1be6428a375f3adf14df87b66d`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: reconcile TODO/handoff metadata with latest green MVP evidence.
- Metric/threshold: fixed reconciliation matrix `3/3`.
- Baseline: `/tmp/unified-report-handoff-baseline.log` was `0/3`; latest report counts, HEAD/CodeGraph metadata and TODO current/archive labels were stale.
- Change: refreshed current labels, archived prior iteration names and synchronized evidence fields; runtime unchanged.
- Wet validation: reconciliation `3/3`; unified runner source `6/6`, targeted `118/118`, full discovery `607/607`; docs `17/17`; `git diff --check` and handoff JSON pass; CodeGraph `139/3757/12713`; HEAD `1d04548c725e4f1be6428a375f3adf14df87b66d`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: close CLI node-filtered replay scope over EventStream recovery metadata.
- Metric/threshold: fixed CLI replay matrix `3/3`.
- Baseline: `/tmp/cli-replay-scope-baseline.log` was `2/3`; direct replay and `events node` passed, `events replay <node>` included `node-b`.
- TDD change: CLI parser now recognizes `events replay <node>` as node filter; added CLI regression test. No runtime/provider/model/fallback/parallel change.
- Wet validation: CLI replay matrix `3/3`; CLI/event/adapter targeted `47/47` with 1 skip; targeted MVP `118/118`; unified runner `6/6`; simulation `29/29`; full discovery `607/607` with 5 skips; CLI `3/3`; docs `17/17`; direct OmniRoute smoke green; CodeGraph `139/3757/12713`, up to date; HEAD `1d04548c725e4f1be6428a375f3adf14df87b66d`.
- Blockers preserved: actual multi-node free route stability remains unproven; full v3 approval pending.

- Objective: add explicit fail-closed OmniRoute node-contract handling without changing direct smoke or provider/model policy.
- Metric/threshold: fixed contract matrix `3/3`.
- Baseline: `/tmp/omniroute-adapter-contract-baseline.log` was `1/3`; valid payload passed, wrong-contract and prose returned code 0.
- TDD change: added explicit `--node-contract`; goal-loop passes it; adapter validates allowed fields, summary, messages and JSON; configured free fallbacks remain same.
- Wet validation: contract matrix `3/3`; adapter/goal-loop targeted `39/39` with 1 intentional skip; unified runner `6/6`; full discovery `606/606` with 5 skips; CLI `3/3`; docs `17/17`; direct smoke green; CodeGraph `139/3755/12707`, up to date; HEAD `52079ce0abc860ae6f86a0c9b71f54131e9caa04`.
- Remaining blocker: actual multi-node free route behavior still externally unstable; adapter now rejects invalid output fail-closed. Full v3 approval remains pending.

- Objective: close node-scoped tool replay/recovery projection over persistent non-file recovery.
- Metric/threshold: fixed replay matrix `3/3`.
- Baseline: `/tmp/tool-replay-scope-baseline.log` was `2/3`; unfiltered and node-filtered in-flight sets passed, recovery projection absent.
- TDD change: EventStream replay now returns `tool_recoveries` with recovered status and `retry_authorized=false`, preserving node filter scope; added fixed replay matrix test.
- Wet validation: replay matrix `3/3`; targeted suite `118/118 OK`; targeted MVP `118/118 OK`; unified runner `6/6`; simulation `29/29`; full discovery `604/604` with 5 skips; CLI `3/3`; docs `17/17`; direct OmniRoute smoke green; handoff JSON and `git diff --check` pass; CodeGraph `139/3751/12690`, up to date; HEAD `a2b1fdc1676188ac2ac6a27e953685ddf8b22d06`.
- Blocker preserved: live multi-node OmniRoute remains fail-closed on malformed/truncated, wrong-contract and prose-wrapped output; full v3 approval remains pending.

- Objective: add automated direct shell lifecycle acceptance over persistent non-file recovery.
- Metric/threshold: fixed automated acceptance `3/3`.
- Baseline: `/tmp/nonfile-recovery-integration-baseline-valid.log` behavior probe `3/3`, but automated coverage was `2/3` because direct shell lifecycle had no dedicated assertion.
- TDD change: added direct-shell event/replay test; runtime unchanged.
- Wet validation: acceptance `3/3`; targeted suite `117/117 OK`; targeted MVP `117/117 OK`; unified runner `6/6`; simulation `29/29`; full discovery `603/603` with 5 skips; CLI `3/3`; docs `17/17`; `py_compile`, handoff JSON and `git diff --check` pass; direct OmniRoute smoke green; CodeGraph `139/3750/12685`, up to date; HEAD `43d1838c605e1d1294c35683a9f43761f75aaa61`.
- Blocker preserved: live multi-node OmniRoute remains fail-closed on malformed/truncated, wrong-contract and prose-wrapped output; full v3 approval remains pending.

- Objective: implement non-file tool interruption recovery with persistent replay metadata and fail-closed resume.
- Metric/threshold: fixed recovery matrix `3/3`.
- Baseline: `/tmp/nonfile-recovery-baseline.log` was `1/3`; in-flight replay and reopen recovery markers were absent.
- TDD change: added `tool_started`/`tool_recovery` lifecycle events, persistent `.stagewarden/tool_operations.json`, deterministic replay `in_flight_tools`, and `retry_authorized=false`; no automatic tool retry.
- Wet validation: recovery matrix `3/3`; unified runner `6/6`; simulation `29/29`; targeted MVP `116/116`; full discovery `602/602` with `5` skips; CLI `3/3`; docs hygiene `17/17`; handoff JSON valid; `git diff --check` pass; OmniRoute direct smoke green; CodeGraph `139/3749/12673`, up to date. Existing provider/model, fallback, serial and mutation policy unchanged.
- Blocker preserved: live multi-node OmniRoute remains fail-closed on malformed/truncated, wrong-contract and prose-wrapped output; full v3 approval remains pending.

- Objective: reconcile TODO/handoff metadata against completed node-first MVP evidence without changing runtime/provider/model policy.
- Metric/threshold: canonical unified validation `6/6` gate groups green.
- Baseline: `/tmp/stagewarden-state-reconcile-baseline.log` recorded unified runner `6/6` while TODO and handoff metadata still contained stale unchecked completions and old HEAD/CodeGraph values.
- Change: refreshed TODO completion checkboxes and current handoff summary; no runtime/API/provider/model/fallback/parallelism change.
- Wet validation: unified runner `6/6`; simulation `29/29`; targeted MVP `114/114`; full discovery `600/600` with `5` skips; CLI `3/3`; docs hygiene `17/17` with 0 errors; targeted rerun `114/114 OK`; handoff JSON valid; `git diff --check` OK; OmniRoute direct smoke `OmniRoute free route OK (auto/coding:free)`; CodeGraph `139/3735/12612`, up to date; HEAD `6fe50debf4a6b061e67a84ad4deca404a68ac2d9`.
- Blockers preserved: live multi-node OmniRoute malformed/truncated, wrong-contract and prose-wrapped outputs remain fail-closed; full v3 approval remains pending.

- Objective: validate Node Knowledge Store/index acceptance across context isolation, citation, Python symbols, compaction, freshness and file-read recovery.
- Metric/threshold: 6/6 fixed Node Knowledge Store/index cases pass.
- Baseline: `/tmp/node-knowledge-coverage-baseline.log` recorded partial node/file tests but no explicit stale/fresh or cross-node matrix.
- TDD change: added Node Knowledge Store matrix case for node isolation, citations, code lines, compaction and stale/fresh reindex; retained checkpoint/reopen recovery tests.
- Wet validation: matrix `6/6`; Node Knowledge/file/context/event suite `19/19 OK`; goal-loop/event/tools suite passed; OmniRoute free smoke green; `py_compile`, `git diff --check` passed; CodeGraph `137/3685/12326`.
- Fixed cases: context remains node-scoped; citation/source metadata persists; Python symbols/line ranges retrieve; compaction deterministic; reindex surfaces fresh symbols; file-read checkpoint survives reopen.
- Next bounded gate: broader acceptance/full matrix.
- Metric/threshold: 6/6 fixed tree/packet cases pass.
- Baseline: `/tmp/tree-packet-coverage-baseline.log` recorded partial goal-loop coverage but no explicit six-case matrix.
- TDD change: added fixed goal-loop matrix for root/cycle invariants, ready ordering, WorkPacket rejection, ResultPacket evidence/parent scope, lateral message rejection and serial projection.
- Wet validation: matrix `6/6`; goal-loop `32/32 OK`; goal/event/node/context/recovery aggregate `115/115 OK`; executor-event + tools `56/56 OK`; OmniRoute free smoke green; `py_compile`, `git diff --check` passed; CodeGraph `137/3684/12316`.
- Fixed cases: root/cycle invariants fail closed; ready ordering deterministic; unknown parent WorkPacket rejected; ResultPacket remains parent-scoped with evidence; lateral messages rejected; serial run/replay projection remains intact.
- Next bounded gate: Node Knowledge Store/index acceptance matrix.
- Metric/threshold: 6/6 fixed context cases pass: provider budget, node/user prompt budget, chunk cap, compaction reduction, JSONL metadata/replay and recovery persistence.
- Baseline: `/tmp/context-budget-coverage-baseline.log` recorded base context tests but no explicit six-case matrix.
- TDD change: added context budget matrix case covering user budget, node-scoped prompt, chunk event metadata and replay projection; retained existing file recovery/compaction tests.
- Wet validation: matrix `6/6`; `python3 -m unittest tests.test_context_file_reading tests.test_executor_event_stream tests.test_event_stream tests.test_file_read_recovery -q` → `15/15 OK`; executor/goal/node knowledge suite passed; OmniRoute free smoke green; `py_compile`, `git diff --check` and handoff checks passed; CodeGraph `137/3683/12305`.
- Fixed cases: available budget preserves reserved output/safety margin; node prompt budget compacts/caps chunks; file_chunk/context_compaction metadata measurable; replay retains node event projection; persisted file-read recovery remains intact.
- Next bounded gate: broader tree/packet acceptance matrix.
- Objective: extend MutationJournal idempotency/recovery to `chown_path_file` without repeated chown or provider/model changes.
- Metric/threshold: 3/3 fixed chown-path cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/chown-path-journal-baseline.log`; existing branch repeated chown, left `in_flight` open and did not record unknown-owner failure.
- Wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `43/43 OK`; aggregate mutation/executor/event/file-recovery → `111/111 OK`; `tests.test_executor_event_stream tests.test_tools` → `56/56 OK`; `scripts/test_omniroute_free.sh` → `OmniRoute free route OK (auto/coding:free)`; `git diff --check` and `py_compile` passed; CodeGraph `137/3676/12231` current.
- Fixed cases: repeated `chown_path_file` returns `replayed`; existing `in_flight` resumes and closes `completed`; unknown owner records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: coverage audit for all 14 declared mutation action types.
- Objective: extend MutationJournal idempotency/recovery to `chmod_path_file` without repeated chmod or provider/model changes.
- Metric/threshold: 3/3 fixed chmod-path cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/chmod-path-journal-baseline.log`; existing branch repeated chmod, left `in_flight` open and did not record invalid-mode failure.
- Historical wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `40/40 OK`; aggregate mutation/executor/event/file-recovery → `108/108 OK`; tools/event → `56/56 OK`; OmniRoute free smoke green; CodeGraph `137/3673/12194`.
- Fixed cases: repeated `chmod_path_file` returns `replayed`; existing `in_flight` resumes and closes `completed`; invalid mode records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: `chown_path_file`, then remaining path mutations.
- Objective: extend MutationJournal idempotency/recovery to `delete_path_file` without repeated deletion or provider/model changes.
- Metric/threshold: 3/3 fixed delete-path cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/delete-path-journal-baseline.log`; existing branch deleted once then replay failed on missing path, left `in_flight` open and did not record failure.
- Historical wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `37/37 OK`; aggregate mutation/executor/event/file-recovery → `105/105 OK`; tools/event → `56/56 OK`; OmniRoute free smoke green; CodeGraph `137/3670/12157`.
- Fixed cases: repeated `delete_path_file` returns `replayed`; existing `in_flight` resumes and closes `completed`; missing target records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: `chmod_path_file`, then remaining path mutations.
- Objective: extend MutationJournal idempotency/recovery to `move_path_file` without repeated moving or provider/model changes.
- Metric/threshold: 3/3 fixed move-path cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/move-path-journal-baseline.log`; existing branch moved once then replay failed on missing source, left `in_flight` open and did not record failure.
- Historical wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `34/34 OK`; aggregate mutation/executor/event/file-recovery → `102/102 OK`; tools/event → `56/56 OK`; OmniRoute free smoke green; CodeGraph `137/3667/12120`.
- Fixed cases: repeated `move_path_file` returns `replayed`; existing `in_flight` resumes and closes `completed`; missing source records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: `delete_path_file`, then remaining path mutations.
- Objective: extend MutationJournal idempotency/recovery to `copy_path_file` without repeated copying or provider/model changes.
- Metric/threshold: 3/3 fixed copy-path cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/copy-path-journal-baseline.log`; existing branch copied once then failed replay, left `in_flight` open and did not record missing-source failure.
- Historical wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `31/31 OK`; aggregate mutation/executor/event/file-recovery → `99/99 OK`; tools/event → `56/56 OK`; OmniRoute free smoke green; CodeGraph `137/3664/12082`.
- Fixed cases: repeated `copy_path_file` returns `replayed`; existing `in_flight` resumes and closes `completed`; missing source records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: `move_path_file`, then remaining path mutations.
- Objective: extend MutationJournal idempotency/recovery to `normalize_line_endings_file` without repeated normalization or provider/model changes.
- Metric/threshold: 3/3 fixed normalize-line-endings cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/normalize-line-endings-journal-baseline.log`; existing branch repeated no-op normalization, left `in_flight` open and did not record invalid-newline failure.
- Historical wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `28/28 OK`; aggregate mutation/executor/event/file-recovery → `96/96 OK`; tools/event → `56/56 OK`; OmniRoute free smoke green; CodeGraph `137/3661/12044`.
- Fixed cases: repeated normalization returns `replayed`; existing `in_flight` resumes and closes `completed`; invalid newline records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: `copy_path_file`, then remaining path mutations.
- Objective: extend MutationJournal idempotency/recovery to `convert_encoding_file` without repeated conversion or provider/model changes.
- Metric/threshold: 3/3 fixed convert-encoding cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/convert-encoding-journal-baseline.log`; existing branch had no journal, UTF-8 readback failed after Latin-1 output, and unknown encoding raised `LookupError`.
- Historical wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `25/25 OK`; aggregate mutation/executor/event/file-recovery → `93/93 OK`; tools/event → `56/56 OK`; OmniRoute free smoke green; CodeGraph `137/3658/12007`.
- Fixed cases: repeated conversion returns `replayed`; existing `in_flight` resumes and closes `completed`; unknown encoding records `failed` without propagating; encoding-aware verification and serial/provider policy unchanged.
- Next bounded mutation gate: `normalize_line_endings_file`, then remaining path mutations.
- Objective: extend MutationJournal idempotency/recovery to `replace_range_file` without repeated replacement or provider/model changes.
- Metric/threshold: 3/3 fixed replace-range cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/replace-range-journal-baseline.log`; existing branch repeated a no-op replacement, left `in_flight` open and did not record failures.
- Historical wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `22/22 OK`; aggregate mutation/executor/event/file-recovery → `90/90 OK`; tools/event → `56/56 OK`; OmniRoute free smoke green; CodeGraph `137/3655/11968`.
- Fixed cases: repeated `replace_range_file` returns `replayed`; existing `in_flight` resumes and closes `completed`; invalid line range records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: `convert_encoding_file`, then remaining range/path mutations.
- Objective: extend MutationJournal idempotency/recovery to `delete_backward_file` without repeated deletion or provider/model changes.
- Metric/threshold: 3/3 fixed delete-backward cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/delete-backward-journal-baseline.log`; existing branch reapplied deletion, left `in_flight` open and did not record failures.
- Historical wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `19/19 OK`; aggregate mutation/executor/event/file-recovery → `87/87 OK`; tools/event → `56/56 OK`; OmniRoute free smoke green; CodeGraph `137/3652/11931`.
- Fixed cases: repeated `delete_backward_file` returns `replayed`; existing `in_flight` resumes and closes `completed`; invalid anchor records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: `replace_range_file`, then remaining range/path mutations.
- Objective: extend MutationJournal idempotency/recovery to `delete_range_file` without repeated deletion or provider/model changes.
- Metric/threshold: 3/3 fixed delete-range cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/delete-range-journal-baseline.log`; existing branch repeated deletion, left `in_flight` open and did not record failures.
- Historical wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `16/16 OK`; aggregate mutation/executor/event/file-recovery → `84/84 OK`; tools/event → `56/56 OK`; OmniRoute free smoke green; CodeGraph `137/3649/11894`.
- Fixed cases: repeated `delete_range_file` returns `replayed`; existing `in_flight` resumes and closes `completed`; invalid line range records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: `delete_backward_file`, then remaining range/path mutations.
- Objective: extend MutationJournal idempotency/recovery to `patch_files` without repeated multi-file application or provider/model changes.
- Metric/threshold: 3/3 fixed patch-files cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/patch-files-journal-baseline.log`; existing branch applied the first multi-file patch, then failed replay, left `in_flight` open and did not record failures.
- Historical wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `13/13 OK`; aggregate mutation/executor/event/file-recovery → `81/81 OK`; tools/event → `56/56 OK`; OmniRoute free smoke green; CodeGraph `137/3646/11857`.
- Fixed cases: repeated `patch_files` returns `replayed`; existing `in_flight` resumes and closes `completed`; invalid multi-file patch records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: remaining range/path mutations.
- Objective: extend MutationJournal idempotency/recovery to `patch_file` without repeated application or provider/model changes.
- Metric/threshold: 3/3 fixed patch-file cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/patch-file-journal-baseline.log`; existing branch reapplied valid patches, left `in_flight` open and did not record failures.
- Historical wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `10/10 OK`; aggregate mutation/executor/event/file-recovery → `78/78 OK`; `tests.test_executor_event_stream tests.test_tools` → `56/56 OK`; OmniRoute free smoke green; CodeGraph `137/3643/11818`.
- Fixed cases: repeated `patch_file` returns `replayed`; existing `in_flight` resumes and closes `completed`; invalid patch records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: `delete_range_file`, then remaining range/path mutations.
- Objective: extend MutationJournal idempotency/recovery to `search_replace_file` without repeated replacement or provider/model changes.
- Metric/threshold: 3/3 fixed search-replace cases pass: completed replay, `in_flight` recovery and failed terminal status.
- Baseline: 0/3 in `/tmp/search-replace-journal-baseline.log`; existing branch lacked journal writes for this action.
- Wet validation: `python3 -m unittest tests.test_mutation_execution -q` → `10/10 OK`; aggregate `tests.test_mutation_execution tests.test_mutation_journal tests.test_executor tests.test_event_stream tests.test_file_read_recovery` → `78/78 OK`; `tests.test_executor_event_stream tests.test_tools` → `56/56 OK`; `scripts/test_omniroute_free.sh` → `OmniRoute free route OK (auto/coding:free)`; `git diff --check` and `py_compile` passed; CodeGraph `137/3643/11818` current.
- Fixed cases: repeated `search_replace_file` returns `replayed` and does not apply second replacement; an existing `in_flight` entry resumes and closes `completed`; execution failure records `failed`; serial execution and provider/model policy unchanged.
- Next bounded mutation gate: `patch_file(s)` and remaining range/path mutations.
- Objective: extend MutationJournal idempotency/recovery to `insert_text_file` without duplicate insertion or provider/model changes.
- Metric/threshold: insert mutation recovery cases pass at 100%; baseline `6` mutation journal/execution tests green; post-change focused mutation/executor/event/file suite `72/72` green.
- Fixed cases: insert records in_flight; completion records terminal status; repeated same action replays without modifying file; existing write/patch recovery remains green.
- Fixed cases: blocked node requeues once within max_retries; retry_count/max_retries emitted; second completion emits no duplicate retry; serial scheduler unchanged.
- Fixed cases: completed child yields one parent-targeted result; FROM/TO and work ID are correct; evidence is list; lateral/control guards remain green.
- Fixed cases: all canonical documents name same stack; prompt is not source of truth; NodeExecutionCapsule and event/knowledge layers are distinct; no blackboard/lateral/implicit parallelism added.
- Wet validation: `python3 -m unittest tests.test_goal_loop_orchestrator tests.test_event_stream tests.test_node_knowledge tests.test_context_file_reading tests.test_file_read_recovery -q` → `45` tests, `OK`; CodeGraph `137/3634/11716`; Markdown UTF-8/no-BOM and diff checks passed.
- Metric/threshold: delegation-contract acceptance cases pass at 100%; baseline `44` focused goal/event/knowledge/file/context tests green; post-change `45/45` green.
- Fixed cases: valid child packet contains known parent/dependencies/acceptance; unknown parent rejects; missing acceptance rejects; root remains executable; lateral guard and result packet tests remain green.
- Metric/threshold: lateral-message acceptance cases pass at 100%; baseline `43` focused goal/event/knowledge/file/context tests green; post-change `44/44` green.
- Fixed cases: lateral sender/target rejected; unknown endpoints rejected; authorized edge remains admissible; rejection does not alter target messages; serial execution unchanged.
- Metric/threshold: compaction-event metadata acceptance cases pass at 100%; baseline `12` context/file/event/executor tests green; post-change `13/13` focused tests green.
- Fixed cases: compaction event records available input tokens, max chars and prompt chars before/after; after < before; file-chunk/recovery/redaction tests remain green.
- Metric/threshold: context-event metadata acceptance cases pass at 100%; baseline `11` context/file/event tests green; post-change `12/12` focused tests green.
- Fixed cases: file_chunk records available input tokens, prompt chars before/after and auto_compacted; existing compaction/file recovery/redaction tests remain green.
- Metric/threshold: replay metadata acceptance cases pass at 100%; baseline `35` focused event/executor/goal/knowledge tests green; post-change `36/36` green.
- Fixed cases: replay keeps context revision, summary reference and remaining input budget; mutation recovery exposes key/status; secret redaction remains intact; existing cycle projection remains green.
- Metric/threshold: replay projection acceptance cases pass at 100%; baseline `30` event/executor/goal tests green; post-change `35/35` focused event/executor/goal/knowledge tests green.
- Fixed cases: replay preserves cycle id, phase, context revision and checkpoint; redaction and node filtering remain intact; existing file/goal event paths remain green.
- Metric/threshold: packet-edge acceptance cases pass at 100%; baseline `34` focused goal/event/knowledge/file-recovery tests green; post-change `35/35` green.
- Fixed cases: ResultPacket carries declared parent/child IDs; evidence is list; packet has no lateral messages; successful child result reaches only declared parent; existing ordering/tree tests remain green.
- Metric/threshold: ordering acceptance cases pass at 100%; baseline `33` focused goal/event/knowledge/file-recovery tests green; post-change `34/34` green.
- Fixed cases: root is first; child becomes ready only after dependency completion; same-depth ready nodes sort by `node_id`; parent-cycle detection remains fail-closed; valid blueprint runs unchanged.
- Metric/threshold: tree invariant acceptance cases pass at 100%; baseline `29` focused goal/event/knowledge tests green; post-change `33/33` focused goal/event/knowledge/file-recovery tests green.
- Fixed cases: one root; explicit parent edges; dependencies/parents exist; root has no dependency; dependency/parent cycles reject before execution; valid blueprint still runs serially.
- Wet validation: focused suite `33 OK`; direct OmniRoute free smoke green; CodeGraph `137/3625/11670`; diff/Markdown checks passed.
- Metric/threshold: paid-policy acceptance cases pass at 100%; baseline `25` policy/router tests green before change; post-change focused policy/goal/mutation/executor suite `115/115` green.
- Fixed cases: paid/unknown-priced provider skipped without authorization; explicit authorization retains route candidates; persisted policy reaches router; WorkPacket includes selection policy; existing manual/fallback and mutation tests remain green.
- Metric/threshold: fixed policy/router/executor/CLI cases pass at 100%; result `26/26` focused policy cases green after TDD change. Baseline before edit: `18/18` existing router/model-policy cases green, with manual mode not wired to router.
- Fixed cases: manual preferred provider beats task heuristic; auto mode preserves heuristic; manual variants and fallback stay blocked; explicit authorization remains usable; CLI/report reflect state; executor performs no second provider call.
- Wet validation: `python3 -m unittest tests.test_executor tests.test_router tests.test_modelprefs tests.test_model_policy_cli tests.test_agent_integration -q` passed `90` with `1` intentional skip before final test additions; focused policy suite passed `26`; `scripts/test_omniroute_free.sh` returned `OmniRoute free route OK (auto/coding:free)`.

## Validation evidence
- Objective: recover an interrupted file mutation from an `in_flight` journal entry exactly once, with terminal journal status and recovery event, without changing serial execution or provider/model routing.
- Metric/threshold: fixed mutation-recovery cases pass at 100%; baseline `4/4` mutation journal/execution tests green; post-change focused mutation/recovery suite `69/69` green.
- Fixed cases: `in_flight` entry is visible; rerun does not replay as completed; write executes once; journal becomes `completed`; `mutation_recovery` event is emitted; existing completed idempotency remains green.
- Wet validation: `python3 -m unittest tests.test_goal_loop_orchestrator tests.test_event_stream tests.test_node_knowledge tests.test_file_read_recovery tests.test_context_file_reading -q` → `45` tests, `OK`; `scripts/test_omniroute_free.sh` returned `OmniRoute free route OK (auto/coding:free)`; CodeGraph `137/3634/11716`; diff/Markdown checks passed.
- OmniRoute smoke failed contract this cycle: prose-wrapped `Stagewarden_Free_OK` instead of exact expected marker. External route blocker recorded; adapter/parser unchanged.
- OmniRoute retry in this iteration returned structurally valid but semantically wrong JSON (`summary/keyDecisions/taskProgress/activeEntities` instead of required `STAGEWARDEN_FREE_OK`); recorded as external route-contract blocker. No adapter/parser weakening.
- Metric/threshold: capsule round-trip/reopen acceptance cases pass at 100%; baseline `28` focused goal/knowledge/file/event tests green before this change; post-change `30` focused tests green.
- Fixed cases: capsule survives SQLite reopen; orchestrator writes capsule on node event; reopen restores non-terminal status, cycle id and checkpoint; node scope remains isolated.
- Wet validation: `python3 -m unittest tests.test_node_knowledge tests.test_goal_loop_orchestrator tests.test_event_stream tests.test_file_read_recovery -q` → `30` tests, `OK`; `scripts/test_omniroute_free.sh` returned `OmniRoute free route OK (auto/coding:free)`; CodeGraph `137/3614/11615`; `git diff --check` and Markdown UTF-8/no-BOM passed.
- Metric/threshold: cycle-state acceptance cases green at 100%; baseline `24` focused goal/event/knowledge tests green before change; post-change `26` focused tests green.
- Fixed cases: default cycle state serializes; cycle/context revisions survive projection; cycle-start and checkpoint events include node purpose, cycle and context metadata; cycle budget exhaustion blocks rather than loops indefinitely.
- Wet validation: `python3 -m unittest tests.test_goal_loop_orchestrator tests.test_event_stream tests.test_node_knowledge -q` → `26` tests, `OK`; CodeGraph synced at `137/3606/11557`; `git diff --check` passed.

## Open issues
- Unified full runner now exists at `scripts/run_unified_validation.py` with manifest `tests/data/unified_validation_matrix.json`; fixed-order wet run passes 6/6: simulation 29/29, targeted MVP 105/105, full discovery 588/588 (5 skips), CLI 3/3, OmniRoute direct smoke, docs 17/17 with 0 link errors.
- User approval still required for `docs/specs/stagewarden-v3.md`.
- Open decisions are in v3 section 21: bottom-up exceptions, serial/parallel policy, retention, storage backend, code languages, prompt visibility, active-node UX, dynamic child creation, repeat forwarding, and v2 archival handling.
- Runtime v3 implementation not started.
- Full discovery now wet-validates 588 tests; remaining skipped cases are intentional environment/live-provider skips.
- Live multi-node OmniRoute free remains blocked by repeated malformed/truncated JSON after initial nodes; direct adapter smoke remains green. Parser stays fail-closed.
- Paid-provider authorization is persisted and surfaced but not yet enforced by catalog/provider price classification; this iteration enforced manual selection and fallback only.
- Live multi-node OmniRoute free remains blocked by repeated malformed/truncated JSON after initial nodes; direct adapter smoke remains green. Parser stays fail-closed.
- Paid-provider authorization is persisted and surfaced but not yet enforced by catalog/provider price classification; this iteration enforced manual selection and fallback only.
- Do not restart recurring implementation loops.
- Live free-route contract is currently unstable: direct smoke failed once with wrong JSON shape, in addition to prior multi-node malformed/truncated JSON.

## Next steps
1. Preserve same-root ownership guard while evaluating any future code-index freshness/relations work from `TODO.md`.
2. Keep parallel opt-in and broader ancestor/descendant retrieval approval-gated.
3. User reviews and approves/corrects `docs/specs/stagewarden-v3.md` and section 21 decisions.
4. After approval, derive implementation-level TODO entries from the approved spec; only then modify runtime.
5. Implement in order: event/node store, validator, serial bottom-up scheduler, packet protocol, terminal events, Node Knowledge Store/code index, per-node context/compaction, provider ownership, migration.

## Commands
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
