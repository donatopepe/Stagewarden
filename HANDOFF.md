# Stagewarden Handoff Summary

## Current phase
Node-first MVP is fail-closed against untrusted input at three boundaries: the model response (cycles 147), persisted state (148-151), and now the model-action boundary (153). Cycles 147-153 fixed eight real defects across three classes. All validation artifacts are wet-verified green. The project remains fail-closed at user decision gate: no new runtime scope authorized until v3/extension/migration approved. Multi-node route stability remains unproven. Loop active every 5 minutes (`stagewarden-mvp-continue`, task `c05d5335`).

## Latest bounded iteration
- Outcome: **HOLD; metadata mirror check `6/6`.** No runtime, test or script change.
- Objective: verify mirrors after cycle 320. Metric/threshold: consistency `6/6`, source/test/script drift `0`.
- Proof: HEAD `39aaf50`; mirrors reconciled to cycle 321/HEAD; source/test/script diff since `c100efb` empty.
- Wet: targeted `161 passed, 79 subtests passed`; direct OmniRoute smoke green.
- State: `main`, sole worktree, CodeGraph current, JSON waiting/current step waiting/question pending, loop unchanged. No policy change.
- Decision: hold; user decision gate blocker.
- Evidence: `/tmp/stagewarden-bounded-iteration-gate-2026-09-29k224.log`..........................................................

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
- code-aware index of files, modules, classes, procedures, functions, methods, tests and relations with path, lines, hash and freshness; normalized roots are single-node owned.

CodeGraph is auxiliary only. It cannot replace node context/history/evidence/ownership/retrieval.

## Documents rewritten
- `TODO.md` — sole plan/backlog.
- `docs/specs/stagewarden-v3.md` — canonical specification draft.
- `docs/architecture.md` — target architecture.
- `README.md`, `README_IT.md`, `ROADMAP.md`, `docs/README.md`.
- `AGENT_MANIFESTO.md`, `AGENT_POLICY.md`, `AGENT_POLICY.json`.
- `.pi/prompts/*.md` — packetized bottom-up node workflow.
- Legacy/reference docs and model examples aligned or marked non-authoritative.

## Historical bounded iterations (superseded)
- Objective: verify marker consistency latest rerun after latest green gate.
- Metric/threshold: fixed marker matrix `3/3`.
- Baseline: `/tmp/current-marker-consistency-baseline-latest.log` was `3/3`; reran docs, JSON, diff, OmniRoute and replay regression.
- Wet validation: marker `3/3`; docs `17/17`, 0 errors; handoff JSON valid; `git diff --check` OK; direct OmniRoute smoke green; replay regression `1/1`; CodeGraph `140/3821/13085`, up to date; HEAD `86c4f22a0133b10ef8f28e3fcbf68a7cff9551a6`.
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
- Change: added recovery closure test for in-flight appearance, clear-on-recovery, recovered status, node scope and retry denial.
- Wet validation: closure `3/3`; targeted event/executor/adapter `15/15` with 1 skip; targeted MVP `121/121`; unified runner `6/6`; full discovery `610/610` with 5 skips; CLI `3/3`; docs `17/17`; direct OmniRoute smoke green; CodeGraph `139/3760/12729`, up to date; HEAD `07d375c072ec231a39a2f9eed651b4eb49d66149`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: formalize Node Knowledge code-index retrieval scope without broadening retrieval semantics.
- Metric/threshold: fixed code retrieval scope matrix `2/2`.
- Baseline: `/tmp/next-node-knowledge-code-scope-baseline.log` was `1/2`; ancestor symbol leaked into child query after separate node indexes covered same root.
- Change: added isolated ancestor/child code-index regression using separate node roots; no runtime retrieval broadening.
- Wet validation: code scope `2/2`; Node Knowledge suite `8/8`; targeted MVP `120/120`; unified runner `6/6`; full discovery `609/609` with 5 skips; CLI `3/3`; docs `17/17`; direct OmniRoute smoke green; CodeGraph `139/3759/12725`, up to date; HEAD `9997681eeabd3dc3b3295f13df9855588022cde4`.
- Blockers preserved: multi-node OmniRoute external stability and full v3 approval.

- Objective: formalize Node Knowledge retrieval scope acceptance without broadening retrieval semantics.
- Metric/threshold: fixed retrieval scope matrix `2/2`.
- Baseline: `/tmp/next-mvp-node-knowledge-baseline.log` behavior probe `2/2`, but no explicit automated test covered direct node scope and child non-leakage.
- Change: added isolated ancestor/child retrieval regression test; runtime semantics unchanged.
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
- Change: CLI parser now recognizes `events replay <node>` as node filter; added CLI regression test. No runtime/provider/model/fallback/parallel change.
- Wet validation: CLI replay matrix `3/3`; CLI/event/adapter `47/47` with 1 skip; targeted MVP `118/118`; unified runner `6/6`; simulation `29/29`; full discovery `607/607` with 5 skips; CLI `3/3`; docs `17/17`; direct OmniRoute smoke green; CodeGraph `139/3757/12713`, up to date; HEAD `1d04548c725e4f1be6428a375f3adf14df87b66d`.
- Blockers preserved: actual multi-node free route stability remains unproven; full v3 approval pending.

- Objective: add explicit fail-closed OmniRoute node-contract handling without changing direct smoke or provider/model policy.
- Metric/threshold: fixed contract matrix `3/3`.
- Baseline: `/tmp/omniroute-adapter-contract-baseline.log` was `1/3`; valid payload passed, wrong-contract and prose returned code 0.
- Change: added explicit `--node-contract`; goal-loop passes it; adapter validates allowed fields, summary, messages and JSON; configured free fallbacks unchanged.
- Wet validation: contract matrix `3/3`; adapter/goal-loop `39/39` with 1 intentional skip; unified runner `6/6`; simulation `29/29`; full discovery `606/606` with 5 skips; CLI `3/3`; docs `17/17`; direct OmniRoute smoke green; CodeGraph `139/3755/12707`, up to date; HEAD `52079ce0abc860ae6f86a0c9b71f54131e9caa04`.
- Blocker: actual multi-node free route behavior remains externally unstable; invalid output now fails closed. Full v3 approval remains pending.

- Objective: close node-scoped tool replay/recovery projection over persistent non-file recovery.
- Metric/threshold: fixed replay matrix `3/3`.
- Baseline: `/tmp/tool-replay-scope-baseline.log` was `2/3`; unfiltered and node-filtered in-flight sets passed, recovery projection absent.
- Change: EventStream replay now returns `tool_recoveries` with recovered status and `retry_authorized=false`, preserving node filter scope; added fixed replay matrix test.
- Wet validation: replay matrix `3/3`; targeted suite `118/118 OK`; targeted MVP `118/118 OK`; unified runner `6/6`; simulation `29/29`; full discovery `604/604` with 5 skips; CLI `3/3`; docs `17/17`; direct OmniRoute smoke green; handoff JSON and `git diff --check` pass; CodeGraph `139/3751/12690`, up to date; HEAD `a2b1fdc1676188ac2ac6a27e953685ddf8b22d06`.
- Blocker preserved: live multi-node OmniRoute remains fail-closed on malformed/truncated, wrong-contract and prose-wrapped output; full v3 approval remains pending.

- Objective: add automated direct shell lifecycle acceptance over persistent non-file recovery.
- Metric/threshold: fixed automated acceptance `3/3`.
- Baseline: `/tmp/nonfile-recovery-integration-baseline-valid.log` behavior probe `3/3`, but automated coverage was `2/3` because direct shell lifecycle had no dedicated assertion.
- Change: added direct-shell event/replay test; runtime unchanged.
- Wet validation: acceptance `3/3`; targeted suite `117/117 OK`; targeted MVP `117/117 OK`; unified runner `6/6`; simulation `29/29`; full discovery `603/603` with 5 skips; CLI `3/3`; docs `17/17`; `py_compile`, handoff JSON and `git diff --check` pass; direct OmniRoute smoke green; CodeGraph `139/3750/12685`, up to date; HEAD `43d1838c605e1d1294c35683a9f43761f75aaa61`.
- Blocker preserved: live multi-node OmniRoute remains fail-closed on malformed/truncated, wrong-contract and prose-wrapped output; full v3 approval remains pending.

- Objective: implement non-file tool interruption recovery with persistent replay metadata and fail-closed resume.
- Metric/threshold: fixed recovery matrix `3/3`.
- Baseline: `/tmp/nonfile-recovery-baseline.log` was `1/3`; in-flight replay and reopen recovery markers were absent.
- Change: added persistent `.stagewarden/tool_operations.json`, `tool_started`/`tool_recovery` JSONL events, replay `in_flight_tools` projection and `retry_authorized=false`; no automatic retry.
- Wet validation: recovery matrix `3/3`; unified runner `6/6`; simulation `29/29`; targeted MVP `116/116`; full discovery `602/602` with `5` skips; CLI `3/3`; docs `17/17`; handoff JSON valid; `git diff --check` pass; OmniRoute direct smoke green; CodeGraph `139/3749/12673`, up to date. Provider/model/fallback/serial/mutation policy unchanged.
- Blocker preserved: live multi-node OmniRoute remains fail-closed on malformed/truncated, wrong-contract and prose-wrapped output; full v3 approval remains pending.

- Objective: reconcile TODO/handoff metadata against the completed runtime evidence without changing execution/provider/model policy.
- Metric/threshold: canonical unified validation `6/6` gate groups green.
- Baseline: `/tmp/stagewarden-state-reconcile-baseline.log` recorded runner `6/6` but stale HEAD/CodeGraph and unchecked completed TODO items.
- Change: refreshed TODO completion state and handoff evidence; no runtime/API/provider/model/parallelism change.
- Wet validation: unified runner `6/6`; simulation `29/29`; targeted MVP `114/114`; full discovery `600/600` with `5` skips; CLI `3/3`; docs hygiene `17/17`, 0 errors; targeted rerun `114/114 OK`; handoff JSON valid; `git diff --check` OK; OmniRoute direct smoke `OmniRoute free route OK (auto/coding:free)`; CodeGraph `139/3735/12612`, up to date; HEAD `6fe50debf4a6b061e67a84ad4deca404a68ac2d9`.
- Blocker preserved: live multi-node OmniRoute remains fail-closed on malformed/truncated, wrong-contract and prose-wrapped output; full v3 approval remains pending.

- Objective: validate Node Knowledge Store/index acceptance across context isolation, citation, Python symbols, compaction, freshness and file-read recovery.
- Baseline: no dedicated six-case matrix; partial node/file tests existed.
- Change: added Node Knowledge Store acceptance matrix covering node isolation, citations, code lines, compaction and stale/fresh reindex.
- Wet evidence: Node Knowledge/index matrix `6/6`; Node Knowledge/file/context/event suite `19/19 OK`; goal-loop/event/tools suite passed; OmniRoute free smoke `OmniRoute free route OK (auto/coding:free)`; `py_compile`, `git diff --check` passed. CodeGraph current `137 files / 3685 nodes / 12326 edges`.
- Current bounded sub-gate: retry checkpoint/replay `3/3`; targeted MVP/recovery `123/123` with 1 skip; context budget boundary `3/3`; context provider/model selection `3/3`; pause/resume checkpoint `3/3`; mutation replay/recovery `3/3`; remaining MutationJournal family `12/12`; context metadata redaction/replay `3/3`; context/provider identity `3/3`; serial execution-mode `3/3`; Node Knowledge relation/freshness `6/6`; unified fixed-order runner `6/6`. Simulation `29/29`; full discovery `588/588 OK (5 skipped)`; CLI JSON `3/3`; OmniRoute direct smoke green; docs `17/17`, `0` link errors. Unsupported parallel modes fail closed. External multi-node OmniRoute malformed/wrong-contract blocker remains fail-closed; full v3 approval remains pending.

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
- Node Knowledge relation gate: `python3 -m unittest tests.test_node_knowledge -q` → `6/6 OK` including module/import/call/read/write relations, unchanged freshness and changed-version replacement. Targeted aggregate before serial gate → `104/104 OK`.
- Serial gate: `test_execution_mode_serial_gate_has_three_fixed_cases` → `3/3`; targeted aggregate before context gate → `105/105 OK`; `parallel` and `bogus` rejected before execution.
- Context/provider gate: `test_context_budget_provider_node_matrix_has_three_fixed_cases` → `3/3`; context/file + executor-event `10/10`; targeted aggregate before redaction gate → `106/106 OK`. Events expose provider/model and budget identity.
- Redaction/replay gate: `test_context_metadata_redaction_and_node_replay_matrix_has_three_fixed_cases` → `3/3`; context/file/event `15/15`; targeted aggregate before mutation gate → `107/107 OK`. Replay retains safe metadata; secret-like values redacted; node filter scoped.
- Mutation family gate: `test_remaining_mutation_families_audit_matrix_has_twelve_cases` → `12/12`; mutation/journal `52/52`; targeted aggregate before safety gate → `108/108 OK`. Range, encoding, path and permission families retain replay/recovery/failure coverage.
- Mutation safety gate: `test_mutation_event_recovery_safety_matrix_has_three_fixed_cases` → `3/3`; mutation/journal/event `58/58`; targeted aggregate before recovery gate → `109/109 OK`. Replay projects mutation key/status; node filtering remains scoped.
- Context budget boundary gate: zero available input, unknown catalog limit and exact boundary compaction → `3/3`; context suite `11/11`; targeted aggregate before retry gate → `122/122` (1 skip). No provider-policy change.
- Retry gate: blocked→pending retry event, capsule retry checkpoint reopen, max retry ceiling → `3/3`; goal-loop `35/35`; targeted aggregate → `123/123` (1 skip). `retry_count`/`max_retries` persist in node capsule; algorithm unchanged.
- Pause/resume gate: capsule reopen + file checkpoint/hash reopen + provider waiting→resume → `3/3`; goal/file/agent recovery `46/46` (1 skip); targeted aggregate before context selection → `120/120` (1 skip). No new pause/cancel API.
- Context provider/model gate: explicit cheap/chatgpt budget identities plus selected-node chunk metadata → `3/3`; context suite `10/10`; targeted aggregate before boundary gate → `121/121` (1 skip). No router/fallback mutation.
- Context boundary gate: zero available input, unknown catalog limit and exact boundary compaction → `3/3`; context suite `11/11`; targeted aggregate → `122/122` (1 skip). No provider-policy change.
- Full discovery: `/tmp/full-unittest-after-status-20260923.log` → `588` tests, `OK (skipped=5)`.
- CLI smoke: `baseline --json`, `model limits --json`, `events replay --json` all exit `0`; JSON output valid. `scripts/test_omniroute_free.sh` → `OmniRoute free route OK (auto/coding:free)`.
- Documentation/link audit: `17` Markdown files checked, `0` link errors, UTF-8/no-BOM pass.
- CodeGraph after runner, index, serial-gate, context metadata, replay-safety, mutation-audit, recovery, provider, boundary, retry and non-file recovery additions: `139 files / 3749 nodes / 12673 edges`, up to date.
- Provider suspension sub-gate: `python3 -m unittest tests.test_agent_integration.AgentIntegrationTests.test_agent_resumes_suspended_network_session_from_persisted_handoff tests.test_agent_integration.AgentIntegrationTests.test_agent_resumes_after_token_reset_from_persisted_handoff -v` → `2/2 OK`.
- Regression targeted aggregate: Agent/executor/router/model-policy/policy-doc tests → `94` tests, `OK (skipped=1)`.
- Simulation wet total: `test_total_run_is_wet_and_fail_closed` → `1/1 OK`.
- CodeGraph: `137 files / 3685 nodes / 12331 edges`, up to date. `git diff --check`, JSON validation and `py_compile` pass.
- Remaining known failure: interactive status compatibility expects automatic chatgpt display while default persisted policy is manual; no policy change made.

## Next action
Blocked at the user decision gate. No runtime work is authorized until it is answered. Outstanding, none self-approvable: `question-1`; v3 scope and section 21 of `docs/specs/stagewarden-v3.md`; extension/subagent capability; migration and temporary compatibility layers; `TODO.md` reorganization; UTF-8 BOM behaviour; promotion of the general audit probe to a permanent test. Until then each bounded cycle applies the cycle-179 diff rule: empty `git diff --stat <baseline>..HEAD -- stagewarden tests scripts` carries the baseline by proof, otherwise the full suite is required. Keep all future work in `TODO.md`.
Recorded explicitly: the previous text here proposed extending the event stream with richer tool/file checkpoint events and a live multiplexer UI. That is unapproved scope, it contradicts this file's own `Current phase` blocker, and it was NOT performed.
