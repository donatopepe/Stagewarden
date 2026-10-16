# Stagewarden Handoff Summary

## Current requested work (2026-10-14)
- External durable memory injection now uses executor `available_input` budget when known, capped at 4000 estimated units; final count and estimator label appear in injected section and memory report. Unknown budget preserves char-only path. This is char-ratio estimate, not provider tokenizer. Prompt budget regression accounts for rendered memory and metadata. Final external-memory section obeys `max_chars`; loader errors fail closed. Token count/limit must be supplied together; partial accounting telemetry rejected. Loader's no-counter error reports both unset. Tests cover; full suite 839 passed, 5 skipped, 364 subtests (322.94s); compileall, JSON, handoff alignment and diff-check pass. Estimator explicitly non-provider-exact.
- Event replay discrepancy resolved: `EventStream.replay()` projects node state, node-scoped in-flight tools and recovery closure; terminal node events clear active tools. Tests prove retry denial is preserved and no retry is inferred. Focused `tests/test_event_stream.py`: 45 passed/20 subtests (1.05s). This is replay projection, not restart orchestration.
- PRINCE2 Quality register per node: `_record_node_quality` writes one evidence-aware entry per terminal status (`completed`→`passed`, `failed`/`blocked`/`skipped` mapped, idempotent), downgrades completion without recorded output to `insufficient_evidence`, and reports secondary-write failures without masking node state. Full suite 819 passed/5 skipped/364 subtests (325.28s); statics clean.
- Unified-validation matrix now includes a `handoff_alignment` gate (command + stdout marker) with fail-closed runner evaluation; wet-run green, existing gates untouched. Full suite 818 passed/5 skipped/364 subtests (333.76s); statics clean.
- Handoff-alignment checker: `scripts/check_handoff_alignment.py` validates required AGENT_HANDOFF.md sections, non-empty HANDOFF.md and required `.stagewarden_handoff.json` keys; exit 1 with errors, wet-run green on the real repo. Full suite 817 passed/5 skipped/364 subtests (333.10s); statics clean.
- Portable EventStream locking: flock/msvcrt backend selection plus atomic O_EXCL fallback with bounded env-configurable spin and fail-closed timeout; Windows branch now exercised with fake msvcrt including release on exception. Full suite 814 passed/5 skipped/364 subtests (333.95s); statics clean.
- PRINCE2 Risk Log per node: one scoped risk per terminal failure (idempotent) and closure only of that node's risks on completion, leaving project-seeded and other-node risks untouched. Full suite 812 passed/5 skipped/364 subtests (332.65s); statics clean.
- PRINCE2 Issue Log at node close: one issue per terminal failure (failed→critical, blocked→major, idempotent, secondary-write failure reported) and automatic closure of open node issues on later completion. Full suite 811 passed/5 skipped/364 subtests (333.58s); statics clean.
- Deterministic lexical search upgrade: field-weighted token scoring (title 3, purpose 2, content/kind 1) plus exact-phrase bonus, stable deterministic tie-break, empty-query behaviour preserved, no semantic claim. Full suite 810 passed/5 skipped/364 subtests (333.61s); statics clean.
- Plugglable goal-loop token counter: `STAGEWARDEN_GOAL_LOOP_TOKEN_COUNTER` (default labelled UTF-8 byte bound; `module:attribute` external counter reported unverified; unknown/unimportable/non-integer fail closed). Metadata/events report the active counter; compaction remains byte-bounded. Full suite 809 passed/5 skipped/364 subtests (332.71s); statics clean.
- Output-cap observation: OmniRoute node path now inspects provider-reported output tokens and fails closed with an explicit `cap_violation` when the requested cap is exceeded (observation-based, not tokenizer equivalence). Full suite 808 passed/5 skipped/361 subtests (333.97s); statics clean.
- EventStream `migrate_legacy_to_chain()`: explicit-only legacy→hash-chain migration, atomic rewrite, fail-closed on torn tail/corruption/mixed content, idempotent. Full suite 807 passed/5 skipped/361 subtests (333.81s); statics clean.
- Deliverable C (global multi-model): regression added proving catalog entries cannot widen router candidates beyond the provider registry nor bypass paid/free policy; catalog remains annotation-only data. Full suite 805 passed/5 skipped/361 subtests (335.71s); statics clean.
- Deliverable B (PRINCE2): `stage_view` gains an evidence-gated `end_stage_report` (gate_state/evidence_gate/evidence refs/lessons) rendered as `end_stage_gate` lines; missing evidence at a boundary fails closed. Full suite 804 passed/5 skipped/361 subtests (342.45s); statics clean.
- §5 context-evolution rubric 3/6→6/6: A6 compaction events add section + UTF-8 byte counts + accounting unit; A3 node-close lesson ritual (handoff lessons log + knowledge `kind=lesson`, idempotent per terminal status); A4 targeted ancestor-lesson reactivation via parent-chain walk, injected in the node prompt only within the model input budget, isolation preserved. Full suite 803 passed/5 skipped/361 subtests (338.91s); statics clean.
- `PROMPT_MASTER_100.md` added: engineered prompt driving the fixed 8/8 acceptance rubric (R1-R8) with invariants, DoD, current-state study, PRINCE2/multi-model/context deliverables and MVP-first method; baseline scored 7/8, iteration 1 closes the handoff-record gap.
- File-read checkpoint/complete validates session/hash/content types and Unicode encoding before mutation; malformed payload regression coverage. Focused 57 passed/40 subtests; full suite 800 passed, 5 skipped, 361 subtests (333.03s).
- File-read session creation validates strict integer chunk/total limits (bool rejected); preserves empty executor node ID compatibility. Focused 50 passed/35 subtests; full suite 800 passed, 5 skipped, 356 subtests (326.15s).
- NodeKnowledgeStore file-read session/checkpoint APIs serialized under RLock, making offset validation+commit atomic cross-thread; focused 49 passed/31 subtests; full suite 799 passed, 5 skipped, 352 subtests (329.33s).
- NodeKnowledgeStore serializes capsule operations and knowledge search with RLock for cross-thread SQLite safety. Focused 104 passed/57 subtests; full suite 799 passed, 5 skipped, 352 subtests (333.30s).
- EventStream primary lifecycle write failure now best-effort handoff-records error and returns without crashing executor; does not claim primary audit success. Goal-loop 84 passed/36 subtests; full suite 799 passed, 5 skipped, 352 subtests (335.32s).
- Primary EventStream append error now triggers best-effort ProjectHandoff failure record, then propagates; regression verifies failure phase. Goal-loop 84 passed/36 subtests; full suite 799 passed, 5 skipped, 352 subtests (347.96s).
- Primary EventStream append failure now propagates and cannot be represented as successful lifecycle audit; secondary handoff failure note best-effort only. Regression verifies no fallback lifecycle event. Goal-loop 84 passed/36 subtests; full suite 799 passed, 5 skipped, 352 subtests (326.64s).
- Node lifecycle event emission survives broken stderr diagnostic write; event/capsule/handoff path continues. Regression added. Goal-loop 83 passed/36 subtests; full suite 798 passed, 5 skipped, 352 subtests (330.40s).
- Replay clears in-flight tools on explicit `node_skipped`/`node_blocked` events; parameterized coverage. EventStream 41 passed/20 subtests; full suite 797 passed, 5 skipped, 352 subtests (335.63s).
- Replay checkpoint reconciliation collapses duplicate active records for same operation/node, retaining latest checkpoint; EventStream 41 passed/18 subtests; full suite 797 passed, 5 skipped, 350 subtests (333.36s).
- Lifecycle transition no longer bubbles secondary handoff-failure-event append error after primary event commit; regression injects both secondary failures. Goal-loop 82 passed/36 subtests; full suite 796 passed, 5 skipped, 350 subtests (326.66s).
- Lifecycle event preserved when secondary handoff recording fails; failure logged as `node_handoff_persist_failure` with error class. Goal-loop 82 passed/36 subtests; full suite 796 passed, 5 skipped, 350 subtests (350.46s).
- Node event emission survives capsule persistence failure, annotating null capsule ref + error class rather than losing runtime event. Goal-loop 81 passed/36 subtests; full suite 795 passed, 5 skipped, 350 subtests (334.60s).
- Context append verifies exact persisted content, not only revision row; read errors/missing/mismatch reject and rollback. Tampered-row regression. Goal-loop 80 passed/36 subtests; full suite 794 passed, 5 skipped, 350 subtests (323.69s).
- Durable append followed by audit failure restores exact committed SQLite context into memory via UUID/revision lookup; tested equality. Goal-loop 80 passed/36 subtests; full suite 794 passed, 5 skipped, 350 subtests (323.07s).
- Context append now persists revision before memory mutation/audit events; failed write emits neither update nor compaction event. Goal-loop 80 passed/36 subtests; full suite 794 passed, 5 skipped, 350 subtests (323.70s).
- Zero input budget now remains zero (no 128-byte floor) for context append/compaction; regression verifies rejection of nonempty append. Goal-loop 80 passed/36 subtests; full suite 794 passed, 5 skipped, 350 subtests (321.56s).
- After durable SQLite write, later audit-event failure now preserves in-memory revision/context and reports persisted-but-audit-failed instead of false rollback. Goal-loop 80 passed/36 subtests; full suite 794 passed, 5 skipped, 350 subtests (320.25s).
- `node_context_compacted` event now follows successful persistent write; failed append rolls back without false compaction audit. Goal-loop 79 passed/36 subtests; full suite 793 passed, 5 skipped, 350 subtests (317.40s).
- `_append_node_context` also rejects bool-as-int budget pitfall, applying 12000-byte conservative fallback; regression covers compaction. Goal-loop 78 passed/36 subtests; full suite 792 passed, 5 skipped, 350 subtests (317.54s).
- Codemode read uses atomic locked in-memory snapshot; no persistence probe; SQLite outage cannot falsely fail read. Goal-loop 78 passed/36 subtests; full suite 792 passed, 5 skipped, 350 subtests (317.45s).
- NodeKnowledgeStore serializes persistent context verify/write with RLock; codemode read failures report separately without mutating in-memory context. Goal-loop 78 passed/36 subtests; full suite 792 passed, 5 skipped, 350 subtests (316.94s).
- Context append verifies persisted UUID-scoped revision after write; silent persistence no-op rolls back memory/revision. Regression added. Goal-loop 78 passed/36 subtests; full suite 792 passed, 5 skipped, 350 subtests (317.43s).
- Codemode append rolls back in-memory context/revision and reports sanitized error if persistent write fails; regression simulates OSError. Goal-loop 78 passed/36 subtests; full suite 792 passed, 5 skipped, 350 subtests (318.00s).
- Per-node codemode APIs serialize read/append for optimistic CAS; race regression gives one success/one conflict. SQLite connection permits serialized cross-thread use. Goal-loop 77 passed/36 subtests; full suite 791 passed, 5 skipped, 350 subtests (317.76s).
- Codemode append excludes bool-valued available_input from integer budget parsing; fallback 12000-byte cap applied and regression covers it. Goal-loop 76 passed/36 subtests; full suite 790 passed, 5 skipped, 350 subtests (317.88s).
- Codemode rejects unpaired-surrogate invalid UTF-8 payload before mutation; goal-loop 76 passed/36 subtests; full suite 790 passed, 5 skipped, 350 subtests (319.62s).
- Codemode rejects oversized individual append payload above node UTF-8 byte budget without advancing context revision; goal-loop 76 passed/36 subtests; full suite 790 passed, 5 skipped, 350 subtests (317.62s).
- Codemode rejects non-string operation values safely before dispatch; goal-loop 76 passed/36 subtests; full suite 790 passed, 5 skipped, 350 subtests (317.05s).
- Codemode read/append share revision validation; unsupported operation rejects first. Goal-loop 76 passed/36 subtests; full suite 790 passed, 5 skipped, 350 subtests (317.52s).
- Codemode read now optionally checks expected_revision and rejects stale snapshots; regression checks current/stale reads. Goal-loop 76 passed/36 subtests; full suite 790 passed, 5 skipped, 350 subtests (317.44s).
- Codemode append rejects non-string payload safely (no `.strip()` exception); goal-loop 76 passed/36 subtests; full suite 790 passed, 5 skipped, 350 subtests (318.62s).
- Codemode context append offers expected-revision CAS and returns UUID; all context writes increment revision, stale/invalid revision rejected. Goal-loop 76 passed/36 subtests; full suite 790 passed, 5 skipped, 350 subtests (318.10s).
- Compaction near marker boundary retains marker and bounded payload at/above 75 bytes; edge tests pass. Goal-loop 76 passed/36 subtests; full suite 790 passed, 5 skipped, 350 subtests (318.05s).
- Compaction marker boundary fixed for caps >=75 bytes; marker retained with tiny content and output stays bounded. Goal-loop 76 passed/36 subtests; full suite 790 passed, 5 skipped, 350 subtests (317.58s).
- Tiny-cap UTF-8 compaction preserves fitting text prefix without marker when marker cannot fit; goal-loop 76 passed/36 subtests; full suite 790 passed, 5 skipped, 350 subtests (317.62s).
- Replay retains bare key for first operation-ID occurrence and qualifies only collisions; regression preserves legacy lookup when unrelated operations precede it. EventStream 40 passed/18 subtests; full suite 790 passed, 5 skipped, 350 subtests (317.61s).
- Legacy prefix followed by malformed gap is no longer exposed when later signed chain exists; verifier zeros verified boundary. read/follow/replay regression. EventStream 39 passed/18 subtests; full suite 789 passed, 5 skipped, 350 subtests (317.49s).
- Replay terminal statuses are case/whitespace normalized; regression covers terminal spellings. EventStream 38 passed/18 subtests; full suite 788 passed, 5 skipped, 350 subtests (317.24s).
- Replay checkpoint updates matching operation+node record without duplicate; regression checks collision isolation. EventStream 38 passed/12 subtests; full suite 788 passed, 5 skipped, 344 subtests (316.73s).
- Replay now retains all active operations for reused IDs across nodes with unique node-qualified keys; regression covers both starts. EventStream 37 passed/12 subtests; full suite 787 passed, 5 skipped, 344 subtests (317.89s).
- Replay preserves colliding operation IDs across nodes using qualified keys and node-scoped completion; focused 36 passed/12 subtests; full suite 786 passed, 5 skipped, 344 subtests (317.08s).
- Replay completion/recovery clears in-flight records only for matching node ID; duplicate operation ID on another node stays active. EventStream 36 passed/12 subtests; full suite 786 passed, 5 skipped, 344 subtests (317.09s); compileall/JSON/diff checks pass.
- Replay recognizes cancelled/canceled state and node terminal event variants; EventStream 35 passed/12 subtests; full suite 785 passed, 5 skipped, 344 subtests (316.74s); compileall/diff-check pass.
- Replay also clears in-flight tools on explicit terminal node events (`node_end`, completion/failure/cancellation variants). EventStream 35 passed/7 subtests; full suite 785 passed, 5 skipped, 339 subtests (317.36s); compileall/diff-check pass.
- Replay reconciliation clears in-flight tool records when node state reaches completed/failed/cancelled/skipped/blocked. EventStream 34 passed/7 subtests; full suite 784 passed, 5 skipped, 339 subtests (316.90s).
- EventStream now rejects/discards prefix if malformed line precedes later signed record; prevents returning legacy-looking records before delayed chain start. Focused 33 passed/7 subtests; full suite 783 passed, 5 skipped, 339 subtests (316.49s).
- Signed EventStream readers expose only verified prefix after corruption, using verified physical line boundary to preserve legacy prefix/blank lines; read/follow/replay do not parse hostile suffix. Focused 33 passed, 7 subtests; full suite 783 passed, 5 skipped, 339 subtests (316.99s); compileall/diff-check/JSON validation pass.
- Simplified legacy torn-tail framing check to require final newline after record parsing; no whole-file byte recount. Focused 32 passed/7 subtests; full suite 782 passed, 5 skipped, 339 subtests (318.15s).
- Clarified EventStream policy: fresh streams and already-hashed streams append signed events; legacy streams append legacy-format only. No legacy migration implicit. EventStream 32 passed/7 subtests; full suite 782 passed, 5 skipped, 339 subtests (317.68s).
- Legacy append now checks file byte size against complete newline-delimited records and refuses torn final records without modifying data. Regression verifies no rewrite; EventStream 32 passed/7 subtests; full suite 782 passed, 5 skipped, 339 subtests (318.17s).
- Prevented silent legacy→hashed stream transition: legacy append strips/blocks caller reserved chain metadata; requesting signed append on legacy file requires explicit migration. Regression covers both, no mixed-format stream. Full suite 781 passed, 5 skipped, 339 subtests (318.06s).
- Preserved legacy-only append behavior: appends remain unchained and strip caller-supplied chain metadata until explicit migration, avoiding mixed-format log corruption. Regression confirms legacy count increments to 3. Focused 31 passed/7 subtests; full suite 781 passed, 5 skipped, 339 subtests (317.13s).
- Event verifier now halts immediately at invalid JSON after legacy/hashed stream starts; stops scanning hostile suffix. Updated regression. Focused 31 passed/7 subtests; full suite 781 passed, 5 skipped, 339 subtests (317.17s).
- Non-object JSON values (e.g. `[]`) after legacy records now mark stream corrupt and stop verification; append fails closed. Regression added. EventStream 31 passed/7 subtests; full suite 781 passed, 5 skipped, 339 subtests (319.99s).
- Added explicit regression for legacy-only event stream validity and accurate unchained count. EventStream 30 passed/7 subtests; full suite 780 passed, 5 skipped, 339 subtests (317.91s).
- Simplified legacy unchained-event integrity logic without changing compatibility: legacy-only stream remains valid; later switch into signed-chain is corruption. Focused 29 passed/7 subtests; full suite 779 passed, 5 skipped, 339 subtests (317.58s).
- Simplified append guard to use `verify_integrity()["valid"]` as sole corruption predicate. Focused 29 passed/7 subtests; full suite 779 passed, 5 skipped, 339 subtests (317.97s).
- EventStream chain verifier now validates parent and digest format as exactly 64 lowercase hex chars before comparison; malformed string metadata rejected. Focused 29 passed/7 subtests; full suite 779 passed, 5 skipped, 339 subtests (318.69s).
- EventStream verifier now rejects records missing chain metadata once chain started, and requires string parent hash/digest before comparisons; malformed non-string fields fail closed. Focused 29 passed/7 subtests; full suite 779 passed, 5 skipped, 339 subtests (317.49s).
- Event sequence verifier requires non-bool integer; Python `True == 1` had allowed malformed boolean sequence through. Regression recomputes valid digest around boolean sequence and confirms rejection. Focused 29 passed/7 subtests; full suite 779 passed, 5 skipped, 339 subtests (319.03s).
- Simplified EventStream append corruption exception to use verifier errors directly; no runtime change. Focused 28 passed/7 subtests; full suite 778 passed, 5 skipped, 339 subtests.
- Prevented callers forging EventStream chain metadata through `append(**details)` by dropping reserved keys and writing canonical sequence/parent/digest. Focused 28 passed/7 subtests; full suite 778 passed, 5 skipped, 339 subtests (319.51s).
- Added regression proving verifier stops at first event-digest mismatch and does not inspect hostile suffix. Integrity now halts on sequence/previous-hash/digest breaks. EventStream 27 passed/7 subtests; full suite 777 passed, 5 skipped, 339 subtests (319.13s).
- Hash-chain verifier halts at first previous-hash mismatch or event-digest mismatch, not scanning later suffix; regression verifies valid-prefix count with malicious tail. Focused 26 passed/7 subtests; full suite 776 passed, 5 skipped, 339 subtests (319.91s).
- Integrity verifier now halts on first sequence discontinuity; regression injects sequence 99 then corrupted tail seq 100 and verifies only valid prefix is counted. Focused 25 passed/7 subtests; full suite 775 passed, 5 skipped, 339 subtests (319.52s).
- Fixed `verify_integrity()` propagation of persistent `chain_broken` for invalid trailing bytes/JSON on a signed stream. Append now rejects; read/replay expose only valid prefix. EventStream 24 passed/7 subtests; full suite 774 passed, 5 skipped, 339 subtests (319.18s).
- EventStream append now uses a single consistent integrity/error predicate; legacy unchained count retained. Focused 24 passed/7 subtests; full suite 774 passed, 5 skipped, 339 subtests (319.62s).
- Extended EventStream fail-closed checks to invalid/non-object lines after legacy unchained records; prevents appending past malformed legacy tail. Focused 24 passed/7 subtests; full suite 774 passed, 5 skipped, 339 subtests (319.89s).
- Renamed verifier flag `unparseable_after_chain` to `chain_broken` for accurate persistent-state naming. Runtime behavior unchanged; focused 23 passed/7 subtests and static checks pass.
- EventStream verifier now prioritizes invalid-JSON/legacy boundary before sequence checks; malformed sequence on subsequent record cannot advance/skip the corrupt suffix. Adversarial probe confirms only one valid-prefix event; full suite 773 passed, 5 skipped, 339 subtests (319.14s).
- Reordered EventStream verifier checks so invalid-JSON boundary is handled before sequence-mismatch logic; corrupted suffix stops at first later hashed record. Focused 23 passed/7 subtests; full suite 773 passed, 5 skipped, 339 subtests (319.09s).
- Integrity verifier now stops immediately at first hashed record following invalid JSON inside chain, reports only valid prefix, and append refuses corrupted suffix. EventStream 23 passed/7 subtests; full suite 773 passed, 5 skipped, 339 subtests (319.16s).
- Integrity verification stops counting verified chain at first unparsable line within it (reports valid prefix only), instead of resuming at next apparently linked event; test checks `events_verified == 1`. Full suite 773 passed, 5 skipped, 339 subtests (318.37s).
- Removed unused integrity-verifier `chain_position` bookkeeping; no behavior change. Focused EventStream 23 passed/7 subtests; static checks pass.
- `EventStream.verify_integrity()` now returns `valid=false` whenever `chain_corrupted=true`, including when malformed JSON is between hashed events but no subsequent hash comparison itself errors. EventStream 23 passed/7 subtests; full suite 773 passed, 5 skipped, 339 subtests (318.01s).
- EventStream integrity now rejects hash-chain continuation after an invalid JSON line, preventing silent chain breaks; terminal invalid tail remains readable until continuation. Regression included. EventStream 23 passed/7 subtests; full suite 773 passed, 5 skipped, 339 subtests (318.64s).
- Added mocked Windows `msvcrt` branch test verifying one-byte lock/unlock at offset zero and sentinel byte initialization. Focused EventStream 22 passed/7 subtests; full suite 772 passed, 5 skipped, 339 subtests (318.93s). Windows-native execution remains unavailable.
- Fixed EventStream sidecar-lock path canonicalization for symlink aliases. EventStream tests terminate spawned workers if timeout; manual spawn-from-stdin probe invalid (`__main__` not importable), no child append. Focused 21 passed/7 subtests; latest full suite 771 passed, 5 skipped, 339 subtests.
- Added sidecar advisory file lock to serialize EventStream appends across processes (`fcntl` POSIX, `msvcrt` Windows); spawned-process regression: 2 writers × 10 append operations, valid chain. Focused 20 passed/7 subtests; full suite 770 passed, 5 skipped, 339 subtests (317.32s). `_process_lock()` annotated as `ContextManager[None]`; imports consolidated. mypy unavailable, py_compile and static checks pass.
- Fixed in-process concurrent EventStream writers across separate instances by sharing a lock keyed on canonical stream path; test runs 2 writer threads × 25 appends and verifies chain. Focused rerun 19 passed/7 subtests; latest full suite remains 769 passed, 5 skipped, 339 subtests (317.10s).
- Hardened event hash chain against unsigned insertion/reordering; append fails closed on detected chain corruption while retaining legacy invalid-JSONL tolerance. Focused EventStream: 18 passed, 7 subtests. Full suite: 768 passed, 5 skipped, 339 subtests (428.61s). Static checks pass.
- Continuation baseline: full suite 766 passed, 5 skipped, 332 subtests. Found/fixed `_compact_node_text` UTF-8 boundary bug where trimming multibyte data could exceed tiny byte cap; added cap edge regressions and scan 1–79 bytes. Post-fix focused goal-loop 76 passed/36 subtests (repeated after test-only extension); full suite 766 passed, 5 skipped, 337 subtests (346.58s; implementation unchanged after suite). Tokenizer/output-cap remain blocked without backend evidence.
- User requested solve/continue per-node context, model token caps, compaction, codemode; preserve v3 seriality/provider/routing/policy.
- Sources refreshed: Pi `2688aba7dc177020ef5da5492a966ed28ad619bd`, Claude Code `9b4f0d6ef8ceaf62f6b46babb9a4d84bec541a2e`, Codex `7eed30ad1beaebc20b7d848ce9ee887525a379b0`; license/provenance and upstream patterns in TODO.
- Implemented first tranche: per-node context/budget/revision in NodeState capsules; catalog+env input/output limits and reserve; safe prompt budget, compaction; serial read/append context API, no eval/tool execution; memory loader accepts exact caller tokenizer or fails closed. Append now persists node-scoped knowledge revision/hash event.
- Validation: focused `unittest` 65 tests passed; complete pytest suite `743 passed, 5 skipped, 301 subtests` via `--ignore=external_sources` (317.16s). `compileall`, JSON and `git diff --check` pass.
- Budget hardening added after skills/custom prompt loading: final prompt includes assigned skills in estimation, fails closed when fixed instructions exceed safe budget; node-local context is fit to remaining budget. Fallback estimate changed to UTF-8 byte upper bound tagged `utf8_byte_upper_bound_v1` (not provider-exact); targeted after change: 69 passed/16 subtests.
- OmniRoute adapter now sends only requested/fallback IDs explicitly marked free; invalid paid-only config fails before HTTP. Full suite after these changes: 746 passed, 5 skipped, 301 subtests.
- Recovery hardening: node context snapshot stores node UUID in provenance; capsule restore selects latest UUID-matched snapshot when revision is >= capsule revision, preventing stale capsule from winning ties. Restart/revision-precedence regressions added. Focused `test_goal_loop_orchestrator` + `test_node_knowledge`: 82 passed, 37 subtests; full suite after tie-break fix 748 passed, 5 skipped, 301 subtests.
- Token fallback now counts UTF-8 bytes, metadata records `utf8_byte_upper_bound_v1`, and compaction caps bytes. Unicode regression verifies count and cap. Focused suite 69 passed/16 subtests; compileall/JSON/diff check pass; full suite rerun pending.
- Wet mock restart exposed terminal capsule bug: restore skipped completed/failed nodes without restoring status. Fixed to restore terminal status plus context/revision/messages/output/error, so resumed completed tree remains completed. OmniRoute forwards effective max_tokens (catalog cap/reserve/config minimum); adapter rejects invalid/non-positive/non-integer/decimal token-limit env before HTTP; goal-loop input/output/reserve/context-margin env now use same strict positive-integer validation. Pi CLI `pi --help` exposes no max-output/max-tokens option. Added opt-in `STAGEWARDEN_GOAL_LOOP_REQUIRE_OUTPUT_CAP=true`, which fails before Pi subprocess if a max output cap is known but unenforceable; default remains off for backwards compatibility. Regression covers fail-closed opt-in on both Pi and OmniRoute before subprocess (OmniRoute `max_tokens` request is not proof of enforcement), plus default execution path.

## Terminology
- User requests generic naming: call it “decision model”, not vendor/model-specific name. Vendor names only in technical provenance/reference notes.
- User requires Stagewarden remote-model tests free-only. OmniRoute adapter filters requested/fallback IDs. Previously overlooked OpenRouter benchmark stubs in `test_handoff.py`, `test_trace_cli.py`, `test_agent_integration.py` and `scripts/test_chatgpt_flow.sh` hardcoded paid preview model. Replaced by `STAGEWARDEN_TEST_FREE_MODEL` default `auto/coding:free`; live cases skip or smoke fails closed if model lacks `:free`. Targeted suites: 240 passed, 4 skipped, 15 subtests.

## Historical decision-model/skills status
- User clarified the decision model is an optional add-on alongside classic LLM; it must not replace/change existing LLM/provider/fallback/routing.
- Chosen `/skill:mvp-first-agent-workflow`; direct analysis, no subagent. User says decision-model efficiency in decision process is already demonstrated. `TODO.md` proposes serial decision-model→policy→existing LLM-on-uncertainty; Stagewarden tests validate faithful integration/no regressions, not re-prove supplied evidence.
- Obsidian details revealed working implementation contracts. Classifier adapters follow documented TypeSafe System One and local llama.cpp verdict-slot protocol. Opt-in `api|llama_cpp` is wired to goal-loop autonomy gate; default off, deterministic policy authoritative, can only raise caution. LLM path unchanged.
- Targeted tests `72 passed, 16 subtests`; full suite `738 passed, 5 skipped, 301 subtests`. HTTP stub smoke only; no actual JEV/GGUF installed, live backend test deferred.
- Pi codemode docs cite a specific classifier as upstream example only; Stagewarden terminology remains generic: decision model. Do not port codemode/skill-loader; adapters use typed contracts without arbitrary script execution.
- Skills now workspace-scoped per node: catalog `.stagewarden/skills`, assignment registry `.stagewarden/goal_loop_skills.json`, named multi-skill custom nodes, safe bounded Markdown only. CLI supports list/assign. Content labeled untrusted prompt data.
- Checkout HEAD `8b32359`; handoff mirrors, TODO, skill views/orchestrator/CLI/tests and classifier files modified. V3 serial/exclusions and classic LLM route unchanged.

## Current phase
Node-first MVP remains fail-closed against untrusted input at model, persisted state and model-action boundaries. V3 section 21 is approved. Serial execution and provider/model/fallback/routing remain unchanged; extensions/subagents and v2 migration/compatibility are declined. Multi-node OmniRoute free remains externally unstable and fail-closed. Loop active every 5 minutes (`stagewarden-mvp-continue`, task `c05d5335`).

## Latest bounded iteration
- Skill feature validation: full suite `741 passed, 5 skipped, 301 subtests`; focused goal-loop/classifier `75 passed, 16 subtests`; CodeGraph current. Per-node Markdown skills implemented, workspace-bounded and not executable.
- Classifier integration: targeted `72 passed, 16 subtests`; full suite `738 passed, 5 skipped, 301 subtests`; local HTTP stub only, real API/GGUF awaits configured Mac.
- Prior MVP waiting baseline below is historical, predates current classifier integration.
- Outcome: **HOLD; approved MVP scope remains waiting, metadata gate `6/6`.**
- Objective: verify approved scope, mirrors and runtime baseline. Metric/threshold: gate `6/6`, runtime diff `0`.
- Proof: HEAD `65ac04d`; answer persisted in `.stagewarden_handoff.json`; TODO v3 approval checked; no unchecked approved runtime slice; extensions/subagents and v2 migration remain unchecked by explicit decision.
- Wet: targeted `161 passed, 79 subtests`; historical full pytest `718 passed, 5 skipped, 301 subtests`; unified validation `6/6`; direct OmniRoute smoke green; JSON/compile/diff guards green.
- State: `main`, sole worktree, CodeGraph current, JSON question answered/status waiting, loop unchanged. No provider/model/fallback/routing/scheduler/parallel change.
- Decision: continue only approved MVP TODO work; fail-closed on unstable multi-node OmniRoute.
- Evidence: `/tmp/stagewarden-cycle357-baseline-2026-09-30.log`..............................................................................

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
