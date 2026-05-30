# Agent Handoff

## Current objective
Evolve Stagewarden into a stronger PRINCE2-oriented coding/design agent: every non-trivial coding step should be governed as a product-focused work package with acceptance criteria, TDD/wet-run evidence, scope control, and exception escalation when tolerances are threatened.

## Current state
- PRINCE2 study pass completed against `/Users/donato/study/PRINCE2_Agent_Project_Spec.md`, `/Users/donato/study/PRINCE2_Agent_Exam_Cram.md`, and `/Users/donato/study/PRINCE2_Archivio_Studio.md`; external AXELOS/PeopleCert PRINCE2 pages were checked as institutional references.
- First PRINCE2+coding tranche is implemented: executor prompt packets now include explicit `Coding work package controls` so model steps must define product focus, acceptance criteria, failing-test/TDD control, minimal implementation, focused wet-run, evidence rule, and escalation boundary.
- Validation passed for touched paths: `python3.11 -m py_compile stagewarden/executor.py stagewarden/executor_prompting.py tests/test_executor.py`, `python3.11 -m unittest tests.test_executor -v` -> 50 OK, and `python3.11 -m unittest tests.test_rag -v` -> 15 OK.
- Full discovery was attempted with `python3.11 -m unittest discover -s tests -v`; it timed out at 600s after exposing three environment-gated failures caused by missing OpenRouter API key (`tests.test_agent_integration.AgentIntegrationTests.test_agent_verbose_output_shows_handoff_runtime_details`, `tests.test_handoff.HandoffTests.test_handoff_passes_openrouter_api_key_to_backend`, `tests.test_handoff.HandoffTests.test_handoff_runs_mmlu_benchmark_suite_against_openrouter`). Focused rerun confirmed all three fail before exercising product code because `_openrouter_env_name()` calls `self.fail("OpenRouter API key is required for this test.")`.
- Session-resume follow-up found one remaining portability gap: test subprocess helpers invoked `python3` directly, which can select Python 3.9 on macOS and break on `dataclass(slots=True)`.
- Portability fix is now in place: subprocess CLI test helpers use `sys.executable` so spawned runs use the same interpreter as the parent test process.
- PR `#1` was merged into `main` (`merge commit 26f53f4ef419e1b22aade0b0cc9b7704cedd2428`) and the feature branch `pr/p4-p5-updates` was deleted locally/remotely.
- Current branch: `main`.
- RAG implementation is complete for this slice and focused tests pass, including hardening found during deep review.
- Core validation passed: `python3 -m unittest tests.test_memory tests.test_executor tests.test_agent_integration tests.test_rag tests.test_json_schema_registry -v` -> 74 OK.
- Focused battery validation passed: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_battery_cli_runs_simulated_agent_scenarios -v`.
- Full validation passed: `python3 -m unittest discover -s tests -v` -> 425 OK.
- CLI smoke passed for `rag add`, `rag rebuild-vectors`, vector-mode `rag search`, and `rag remove`.
- Runtime RAG state is persisted to `.stagewarden_rag.json` and ignored by git.
- Additional validation this session: full `tests.test_trace_cli` run completed with 1 intermittent failure in `test_openrouter_benchmark_cli_reports_multi_suite_baseline`; immediate isolated rerun of that test passed (`ok`), indicating likely flake in benchmark path rather than deterministic regression.
- Post-hardening validation: full trace suite re-run now passes cleanly (`python3 -m unittest tests.test_trace_cli -v` -> 200 OK).
- Cross-cutting regression validation also passes post-hardening: `python3 -m unittest tests.test_rag tests.test_executor tests.test_json_schema_registry -v` -> 66 OK.
- Full discovery now passes after live-benchmark drift guard update: `python3 -m unittest discover -s tests -v` -> 431 OK.

## Recent changes
- `stagewarden/executor_prompting.py`: added `coding_work_package_controls_section(...)`, a PRINCE2/product-delivery control block for coding work packages (product focus, expected output, acceptance criteria, quality gates, TDD, minimal implementation, focused wet-run, scope control, evidence rule, escalation boundary).
- `stagewarden/executor.py`: `_build_model_communication_packet(...)` now injects a bounded `Coding work package controls` section into model prompts before the broader model-context/handoff sections.
- `tests/test_executor.py`: added `test_executor_prompt_includes_coding_work_package_controls_for_code_steps`, written and observed failing first, then passing after implementation.
- `tests/test_rag.py`: `run_main_capture(...)` now uses `sys.executable` instead of hardcoded `python3` for interpreter consistency across environments.
- `tests/test_trace_cli.py`: `run_main_in_cwd(...)` and `run_main_capture(...)` now use `sys.executable` instead of hardcoded `python3`.
- `tests/test_trace_cli.py`: hardened live OpenRouter benchmark trace regression by adding one retry and transient-provider-error skip path (when benchmark returns non-zero and case-level provider/network errors are present), preserving strict failure for non-transient regressions.
- `tests/test_trace_cli.py`: fixed retry-side assertion drift by conditioning `history.previous` expectation on whether a retry occurred (retry writes first snapshot, so `previous` is legitimately non-null on second attempt).
- `stagewarden/project/role_flow.py`: `role tick` RAG retrieval now applies strict scoped tag filtering (`source_node`, `target_node`, `edge_id`) first, then falls back to unscoped delivery retrieval if no scoped hits are found.
- `stagewarden/project/role_flow.py`: added selective RAG indexing for high-signal governed node messages (`role message`) and scoped RAG retrieval context injection on `role tick` when consuming inbox messages.
- `stagewarden/project/role_command_flow.py`: role-message output now reports whether message was indexed into RAG; role-tick output now summarizes retrieved RAG context entries when present.
- `tests/test_trace_cli.py`: role message/tick lifecycle tests now also assert communication-RAG CLI signals (`RAG indexed:` and `RAG context:`) and remain green.
- `stagewarden/cli_dispatch.py`: `role tick --json` payload now includes a top-level `rag_context` field sourced from the latest matching `role_tick` handoff entry details.
- `tests/test_trace_cli.py`: role lifecycle JSON test now asserts `rag_context` key presence in `role tick --json` response payload.
- `stagewarden/project/role_flow.py`: role-message handoff action details now persist `rag_entry_id` when selective indexing occurs.
- `stagewarden/cli_dispatch.py`: `role message --json` now exposes top-level `rag_indexed` and `rag_entry_id` fields for machine-readable indexing telemetry.
- `tests/test_trace_cli.py`: role-message JSON regression test now asserts `rag_indexed`/`rag_entry_id` presence.
- `stagewarden/cli_dispatch.py`: `roles tick --json` now includes top-level `rag_context_by_node` map for machine-readable batch retrieval context visibility.
- `tests/test_trace_cli.py`: batch roles-tick JSON regression now asserts `rag_context_by_node` presence/type.
- `stagewarden/cli_dispatch.py`: non-JSON `roles tick` summary line now reports `rag_context_nodes=<N>` to expose how many nodes consumed retrievable communication context in the batch.
- `tests/test_trace_cli.py`: batch roles-tick regression now asserts non-JSON summary includes `rag_context_nodes=` alongside existing JSON assertions.
- `stagewarden/project/role_flow.py`: batch `roles tick` now computes deterministic `rag_context_by_node` directly from runtime tick results (consumed-message driven), then carries it in the returned result payload.
- `stagewarden/cli_dispatch.py`: roles-tick JSON routes now source `rag_context_by_node` from the returned roles-tick result payload; obsolete handoff-scan helper removed.
- `stagewarden/cli_dispatch.py`: non-JSON `roles tick` summary now includes `rag_context_node_ids=` for quick operator visibility of which nodes had RAG context in the batch.
- `tests/test_trace_cli.py`: batch non-JSON regression now asserts `rag_context_node_ids=` appears in roles-tick summary output.
- `stagewarden/cli_dispatch.py`: `roles tick --json` now also emits compact `rag_context_summary` (`count`, `node_ids`) alongside `rag_context_by_node`.
- `tests/test_trace_cli.py`: roles-tick JSON regression now asserts `rag_context_summary` consistency (`count == len(node_ids)`).
- `tests/test_trace_cli.py`: role-tick lifecycle JSON regression now explicitly tolerates `rag_context=None` on subsequent tick after message consumption while still validating typed context when present.
- `tests/test_trace_cli.py`: role-message JSON regression now asserts telemetry consistency (`bool(rag_entry_id) == rag_indexed`).
- `tests/test_trace_cli.py`: roles-tick JSON regression now asserts `rag_context_summary.node_ids` exactly matches `rag_context_by_node` keys.
- `tests/test_trace_cli.py`: batch roles-tick regression now asserts `delivery.team_manager` appears in `rag_context_by_node` under the governed message-consumption fixture.
- `stagewarden/rag_views.py`: added `percentage_precision` option (0..6) for latest severity percentage rendering/summary formatting.
- `stagewarden/commands.py`: benchmark usage now documents `[percentage_precision=3]`.
- `tests/test_rag.py`: added coverage for configured percentage precision propagation in `latest_summary`.
- `stagewarden/rag_views.py`: benchmark text rendering now includes short CI command examples for latest-enforce usage (default and custom exit code).
- `stagewarden/rag_views.py`: added `latest_enforce_exit_code` option so latest-enforce gate failures can return caller-defined non-zero exit codes.
- `stagewarden/cli_dispatch.py`: rag command now respects report-level `exit_code` when `ok=false`.
- `stagewarden/commands.py`: benchmark usage now documents `[latest_enforce_exit_code=1]`.
- `tests/test_rag.py`: added coverage for enforce-failure `exit_code` payload and end-to-end CLI return-code propagation.
- `stagewarden/rag_views.py`: added `latest_enforce=true` gate mode; when latest deltas fail threshold checks, benchmark report returns `ok=false` with explicit gate error while preserving latest diagnostics payload.
- `stagewarden/commands.py`: benchmark usage now includes `[latest_enforce=true]`.
- `tests/test_rag.py`: added coverage for both pass and fail paths of latest-enforce gating.
- `stagewarden/rag_views.py`: latest benchmark report now includes a compact `latest_summary` object (pass/fail, thresholds, failing count, counts, percentages) for CI-friendly consumption.
- `tests/test_rag.py`: added assertions for `latest_summary` payload keys and rendered summary line.
- `stagewarden/rag_views.py`: latest benchmark payload now includes normalized severity percentages (`minor_pct|major_pct|critical_pct`) over total latest deltas, and rendered output prints the percentage line.
- `tests/test_rag.py`: added coverage for `severity_percentages` payload keys.
- `stagewarden/rag_views.py`: latest benchmark payload now includes severity aggregate counters (`severity_counts.minor_count|major_count|critical_count`) and rendered output prints the aggregate line.
- `tests/test_rag.py`: added coverage for `severity_counts` payload keys.
- `stagewarden/rag_views.py`: failing-delta severity is now configurable from CLI via `major_threshold` and `critical_threshold`, and the chosen thresholds are surfaced in latest benchmark reports.
- `stagewarden/commands.py`: benchmark usage now documents `[major_threshold=0.10] [critical_threshold=0.20]`.
- `tests/test_rag.py`: added coverage for configurable severity-threshold report fields.
- `stagewarden/rag_views.py`: `failing_deltas` entries are now enriched with severity labels (`minor|major|critical`) derived from delta magnitude, and rendered output lists each failing metric with severity.
- `tests/test_rag.py`: added coverage asserting severity presence on failing delta payload entries.
- `stagewarden/rag_views.py`: `latest=true` benchmark payload now includes `failing_deltas` pre-filtered by `warn_threshold` for machine triage.
- `tests/test_rag.py`: added coverage for `failing_deltas` presence/type in latest report paths.
- `stagewarden/rag_views.py`: `rag benchmark ... latest=true` now emits `latest_passed` for quick CI-style gating based on `warn_threshold` and latest deltas.
- `tests/test_rag.py`: added assertions for `latest_passed` presence/type and rendered latest status line.
- `stagewarden/rag_views.py`: `rag benchmark ... latest=true` now accepts `warn_threshold=<float>` and includes that threshold in report payload; rendered latest deltas annotate regressions when delta breaches threshold.
- `stagewarden/commands.py`: benchmark usage updated with `[warn_threshold=0.05]`.
- `tests/test_rag.py`: added coverage for `latest_warn_threshold` parsing/reporting path.
- `stagewarden/rag_benchmark.py`: added `summarize_rag_benchmark_latest(...)` to compute newest-vs-previous deltas for `recall@1`/`recall@3` across modes.
- `stagewarden/rag_views.py`: `rag benchmark ... latest=true` now returns and renders a compact latest snapshot delta section.
- `stagewarden/commands.py`: benchmark usage now includes `[latest=true]`.
- `tests/test_rag.py`: added coverage for latest summary helper plus CLI `latest=true` report/render path.
- `stagewarden/rag_benchmark.py`: trend summary now includes `first_recorded_at` and `last_recorded_at` derived from history envelope timestamps.
- `stagewarden/rag_views.py`: benchmark rendering now prints a `Trend window` line with first/last recorded timestamps when available.
- `tests/test_rag.py`: added trend-render assertion for `Trend window` output.
- `stagewarden/rag_benchmark.py`: benchmark history entries now use a timestamped envelope (`recorded_at`, `report`) when appended, while trend aggregation remains backward compatible with legacy raw report entries.
- `tests/test_rag.py`: added coverage asserting history envelope fields are present and trend summaries still compute correctly.
- `stagewarden/rag_views.py`: `render_rag_report` now prints `rag search` policy metadata header (`mode`, effective `min_score`, `policy_source`) before entries for quick shell inspection.
- `tests/test_rag.py`: added assertions for search-render policy metadata (`policy_source=role`).
- `stagewarden/rag_views.py`: `rag benchmark` now accepts `max_entries=<N>` for history retention control when appending snapshots.
- `stagewarden/commands.py`: benchmark usage string updated with `max_entries=<N>`.
- `tests/test_rag.py`: added coverage for default history retention metadata and explicit truncation behavior (`max_entries=1`).
- `stagewarden/rag.py`: added `resolve_min_score_policy_details(...)` returning both resolved threshold and policy source (`override|role|phase|default`); `resolve_min_score_policy(...)` now delegates to it.
- `stagewarden/rag_views.py`: `rag search` report now includes `policy_source` alongside effective `min_score`.
- `stagewarden/executor.py`: `rag_search` transcript summary now includes threshold policy source for auditability.
- `tests/test_rag.py`: added policy-source assertions for resolution logic and CLI search report output.
- `stagewarden/rag_views.py`: benchmark report rendering now includes per-mode trend details (`first -> last`, `delta`) for `recall@1` and `recall@3`.
- `tests/test_rag.py`: added rendering assertion coverage for trend detail lines.
- `stagewarden/rag_benchmark.py`: added benchmark history append/load support and deterministic trend summarization (`append_rag_benchmark_history`, `load_rag_benchmark_history`, `summarize_rag_benchmark_trend`).
- `stagewarden/rag_views.py`: `rag benchmark` now supports `history=<path>` (append + trend) and `trend=<path>` (read-only trend from history file).
- `stagewarden/commands.py`: updated `rag benchmark` usage string with history/trend flags.
- `tests/test_rag.py`: added coverage for benchmark history/trend helpers and CLI report paths.
- `stagewarden/executor.py`: `_run_action(...)` now accepts optional `prince2_role`; execution path passes step role into action execution so `rag_search` can apply role-aware `min_score` defaults even when action payload omits `role`.
- `tests/test_rag.py`: added executor-level coverage asserting role-derived fallback behavior for `rag_search`.
- `stagewarden/rag.py`: extended RAG v3.5 with role-aware threshold defaults (`RAG_MIN_SCORE_ROLE_DEFAULTS`) in `resolve_min_score_policy`, preserving explicit override precedence.
- `stagewarden/rag_views.py`, `stagewarden/executor.py`, and `stagewarden/executor_prompting.py`: `rag_search` now accepts optional `role` context and applies role-aware effective `min_score` defaults when caller omits threshold.
- `tests/test_rag.py`: added role-aware min-score policy tests in both direct policy resolution and CLI report behavior.
- `stagewarden/rag.py`, `stagewarden/rag_views.py`, and `stagewarden/executor.py`: started RAG v3.5 retrieval policy defaults by phase/mode via `resolve_min_score_policy(...)` and automatic `min_score` resolution when caller does not override.
- `tests/test_rag.py`: added policy-default coverage and CLI assertion for effective `min_score` in phase-scoped searches.
- `stagewarden/rag_benchmark.py`: added baseline-compare utilities (`compare_rag_benchmark_reports`) and snapshot load/save helpers for retrieval drift gating.
- `stagewarden/rag_views.py`: `rag benchmark` now supports `baseline=<path>`, `threshold=<float>`, and `write=<path>` for deterministic compare workflows.
- `tests/test_rag.py`: added regression coverage for benchmark compare behavior and CLI benchmark write/compare path.
- `stagewarden/rag_views.py` and `stagewarden/cli_dispatch.py`: completed RAG v3.4 CLI wiring with `rag benchmark`, including correct JSON schema routing (`stagewarden.rag_benchmark`).
- `stagewarden/json_schema_registry.py` and `stagewarden/commands.py`: registered command/schema/catalog entries for `rag benchmark`.
- `tests/test_rag.py` and `tests/test_json_schema_registry.py`: added CLI/schema coverage for `rag benchmark` end-to-end.
- `stagewarden/rag_benchmark.py`: started RAG v3.4 deterministic retrieval benchmark harness (`run_rag_benchmark`) with fixed corpus/cases and recall@1/recall@3 metrics across lexical/vector/hybrid modes.
- `tests/test_rag.py`: added deterministic snapshot-contract test for benchmark payload shape and stability.
- `stagewarden/rag.py`: completed RAG v3.3 compaction policy modes with `compact(mode=...)` supporting `strict`, `balanced`, and `aggressive` dedupe strategies.
- `stagewarden/rag_views.py`: `rag compact` now accepts `mode=strict|balanced|aggressive` and reports selected mode in response payload.
- `tests/test_rag.py`: added `test_design_rag_compact_modes` and CLI invalid-mode coverage for compaction policy behavior.
- `stagewarden/rag.py`: completed RAG v3.2 diagnostics foundation via `search_diagnostics(...)`, exposing per-result total score plus lexical/vector components.
- `stagewarden/rag_views.py`: `rag search` now returns score diagnostics payload (`mode`, `lexical_score`, `vector_score`) per entry.
- `stagewarden/executor.py`: `rag_search` model-action output now includes lexical/vector score components alongside total score.
- `tests/test_rag.py`: added diagnostics assertions for rag core, executor output, and CLI report payload.
- `stagewarden/rag.py`: started RAG v3 slice with scored retrieval API (`search_scored`) and query thresholding (`min_score`) so ranking confidence can be controlled by caller.
- `stagewarden/rag_views.py`: `rag search` now supports `min_score=<float>` and returns/render per-entry retrieval `score` for explainability.
- `stagewarden/executor.py` and `stagewarden/executor_prompting.py`: `rag_search` schema now accepts `min_score`; action output now includes per-entry score in untrusted results.
- `tests/test_rag.py`: added coverage for invalid `min_score` handling and score-aware search/report behavior.
- `stagewarden/rag.py`: RAG v2 retrieval tuning with field-weighted lexical scoring (title/content/tag coverage), phrase-match boosts, adaptive hybrid lexical/vector weighting, and stronger dedupe detection using token overlap + ngram similarity for near-duplicates.
- `stagewarden/rag.py`: tokenizer now adds a simple plural-normalized alias (`tokens` -> `token`) to improve matching/dedup robustness without external dependencies.
- `tests/test_rag.py`: added `test_design_rag_stronger_dedup_and_ranking` to validate near-duplicate collapse and improved hybrid ranking priority for title-strong matches.
- `.gitignore`: added `.stagewarden_rag.json` runtime state ignore.
- `stagewarden/rag.py`: added JSON-backed `DesignRag` and `RagEntry`, keyword/tag/phase retrieval, deterministic trigram/fuzzy matching, local hashed vector embeddings, persisted vector index, prompt rendering, timestamps, persistence, duplicate upsert, `compact()`, remove, update, vector rebuild, vector-index versioning, and robust next-id recovery.
- `stagewarden/config.py`: added `rag_filename` and `rag_path`.
- `stagewarden/agent.py`: loads/saves RAG, passes it to `Executor`, indexes project start, clarification, rejection, step completion, step observation, step failure, recovery-gate closure, and project finish.
- `stagewarden/executor.py`: injects `Design knowledge (RAG)` into primary and devil-advocate prompt packets; supports model actions `rag_search`, `rag_add`, `rag_update`, and `rag_remove`; exposes RAG actions in executor-level schema constants.
- `stagewarden/executor_prompting.py`: exposes `rag_search`, `rag_add`, `rag_update`, and `rag_remove` in model-visible action schema and examples.
- `stagewarden/rag_views.py`: added CLI report/render helpers for `rag`, `rag list`, `rag search` with `mode=lexical|vector|hybrid`, `rag add`, `rag update`, `rag remove`, `rag compact`, and `rag rebuild-vectors`.
- `stagewarden/cli_dispatch.py`: routes manual RAG CLI commands and JSON output.
- `stagewarden/cli_dispatch.py`: restored browser/system/watch/external IO JSON routing coverage and corrected roles flow/tick routing to owner modules.
- `stagewarden/command_dispatch.py`: added browser `--limit` parsing and non-JSON external IO handling.
- `stagewarden/ui_views.py`: restored slash fuzzy-match highlighting helper.
- `stagewarden/main.py`: restored compatibility exports for catalog/auth/runtime patch targets used by tests.
- `stagewarden/model_views.py`: restored provider auth/login metadata in `model list <provider>` output.
- `stagewarden/modelprefs.py`: stabilized PRINCE2 proposal defaults for project manager/team manager and filters non-chat model specs from role defaults.
- `stagewarden/status_limits_views.py`: provider-limit summaries now report configured/relevant providers rather than every registry provider.
- `stagewarden/status_dashboard_views.py`: runtime detection honors the compatibility patch target used by existing tests.
- `stagewarden/project/tree_flow.py`: restored missing design-flow import for AI-assisted project tree proposals.
- `stagewarden/project/role_flow.py` and `stagewarden/project/role_views.py`: aligned guided role reasoning ordering/rendering with existing CLI contracts.
- `stagewarden/commands.py`: added command catalog entries for RAG list/search/add/update/remove/compact/rebuild-vectors commands.
- `stagewarden/shell_views.py`: recognizes `rag` command prefix in interactive command detection.
- `stagewarden/battery_views.py`: `log_detection` battery path now resolves `_log_error_report` through `project_handoff_views`; focused battery regression passes.
- `tests/test_rag.py`: added coverage for RAG search/persistence, dedupe, fuzzy retrieval, local vector search, vector rebuild, compaction, executor RAG actions, prompt injection, and CLI report helpers.

## Important files
- `stagewarden/executor_prompting.py`: owns prompt sections/schemas; new PRINCE2 coding-work-package control text lives here.
- `stagewarden/executor.py`: prompt packet assembly path; now injects the bounded coding work package controls into every step prompt.
- `tests/test_executor.py`: regression coverage for executor prompt contracts including the new coding-work-package controls.
- `stagewarden/rag.py`: canonical RAG store and retrieval implementation; prompt rendering escapes embedded fences and rebuilds vectors on load to avoid stale persisted embeddings.
- `stagewarden/agent.py`: lifecycle auto-indexing and RAG ownership for agent runs.
- `stagewarden/executor.py`: prompt injection and model action execution path.
- `stagewarden/rag_views.py`: manual CLI surface for RAG.
- `tests/test_rag.py`: dedicated regression coverage for this slice.
- `.stagewarden_rag.json`: local runtime design-knowledge store, intentionally gitignored.

## Technical decisions
- Decision: Treat coding steps as PRINCE2-style work packages in the executor prompt, not only as generic model tasks.
  - Reason: the delivery agent must optimize for concrete products, explicit acceptance criteria, quality evidence, and exception escalation, which directly supports designing and writing better code.
  - Trade-offs: slightly more prompt budget per step; mitigated by bounding the section to 2500 chars and deriving content from existing brief/step fields.
- Decision: Keep the first tranche prompt-level and TDD-covered rather than adding a new command or persistence format.
  - Reason: prompt packet assembly is the highest-leverage path shared by primary execution and assurance flows, and avoids schema churn while proving behavior.
  - Trade-offs: controls guide model behavior but do not yet hard-fail steps that omit TDD evidence; that can be a later enforcement slice.
- Decision: Use stdlib-only JSON-backed RAG with deterministic lexical, trigram, fuzzy-subsequence, and local hashed-vector scoring, not an external vector DB.
  - Reason: keeps Stagewarden dependency-free and portable.
  - Trade-offs: local vectors improve semantic-ish recall without services, but are not as strong as model-generated embeddings.
- Decision: Persist the vector index inside `.stagewarden_rag.json` and version it.
  - Reason: avoids recomputing on every load and safely rebuilds stale vectors after tokenizer/index changes.
  - Trade-offs: the RAG file is larger than entry-only JSON.
- Decision: Inject RAG through `_build_model_communication_packet`.
  - Reason: primary prompts and devil-advocate prompts both render from that packet path.
  - Trade-offs: prompt size is bounded to 2500 chars for RAG context.
- Decision: Allow both automatic lifecycle indexing and manual/model additions.
  - Reason: design knowledge must evolve during project execution and remain user-controllable.
  - Trade-offs: duplicate entries are possible; no deduplication policy yet.
- Decision: expose retrieval confidence as explicit score and support caller-side threshold (`min_score`).
  - Reason: improves auditability and makes retrieval behavior tunable in CLI/model actions without changing persistence format.
  - Trade-offs: threshold tuning can hide relevant low-score entries if set too high.

## Next implementation plan
1. Optionally expose `policy_source` in non-JSON interactive shortcut outputs where only plain text is shown.
2. Consider adding percentage rounding/precision controls for dashboard-specific formatting needs.

## Open issues
- Bugs: No known deterministic bugs in touched paths after validation; `python3` vs interpreter mismatch in subprocess tests is fixed.
- Risks: Full `unittest discover` currently requires OpenRouter credentials for three live/provider tests and timed out at 600s in this environment; focused touched-path validation is green, but full-suite green requires providing `OPENROUTER_API_KEY` or adjusting those tests to skip when credentials are absent.
- Risks: Local hashed vectors can still miss deep semantic matches that require model-generated embeddings or an LLM reranker.
- Risks: `openrouter benchmark` trace test appears intermittently flaky under full-suite load; keep monitoring and re-run isolated test before treating as product regression.
- Risks: Live OpenRouter benchmark remains externally dependent (provider/network/rate limits); test now treats explicit case-level provider errors as transient skips.
- Unknowns: Whether future project design flows should add structured domain-specific RAG entry types beyond generic phase/tags/title/content.

## Next steps
1. Consider enforcement slice: reject or escalate model completions that claim code changes complete without concrete executed validation evidence.
2. Consider adding PRINCE2 product-description/checkpoint summaries to handoff entries after each completed code step.
3. If semantic recall becomes insufficient, consider optional external embedding/reranker backend behind the current dependency-free vector fallback.

## Starting point note
- Start from `main` with a clean worktree.
- Keep PR scope narrow (single objective per branch) and preserve current RAG behavior/contracts.
- Re-run at least focused tests for touched modules; run full discovery for cross-cutting/runtime-impacting changes.

## Commands
```bash
# test
python3.11 -m py_compile stagewarden/executor.py stagewarden/executor_prompting.py tests/test_executor.py
python3.11 -m unittest tests.test_executor.ExecutorTests.test_executor_prompt_includes_coding_work_package_controls_for_code_steps -v
python3.11 -m unittest tests.test_executor -v
python3.11 -m unittest tests.test_rag -v
python3.11 -m unittest discover -s tests -v
python3.11 -m unittest tests.test_rag.RagTests.test_rag_cli_json_schema_and_interactive_route -v
python3.11 -m unittest tests.test_rag -v
python3.11 -m unittest tests.test_trace_cli.TraceAndCliTests.test_interactive_shell_renders_overview_and_board_commands -v
python3.11 -m unittest tests.test_trace_cli.TraceAndCliTests.test_openrouter_benchmark_cli_reports_multi_suite_baseline -v
python3 -m py_compile stagewarden/ui_views.py stagewarden/cli_dispatch.py stagewarden/command_dispatch.py stagewarden/model_views.py stagewarden/main.py stagewarden/rag.py stagewarden/executor.py stagewarden/status_limits_views.py stagewarden/status_dashboard_views.py stagewarden/modelprefs.py stagewarden/project/role_flow.py stagewarden/project/role_views.py stagewarden/project/tree_flow.py tests/test_rag.py
python3 -m unittest tests.test_rag -v
python3 -m unittest tests.test_memory tests.test_executor tests.test_agent_integration tests.test_rag tests.test_json_schema_registry -v
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_battery_cli_runs_simulated_agent_scenarios -v
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_openrouter_benchmark_cli_reports_multi_suite_baseline tests.test_trace_cli.TraceAndCliTests.test_interactive_shell_renders_overview_and_board_commands tests.test_trace_cli.TraceAndCliTests.test_interactive_shell_role_configure_menu_persists_manual_assignment tests.test_trace_cli.TraceAndCliTests.test_interactive_shell_roles_propose_persists_assignments_and_handoff tests.test_trace_cli.TraceAndCliTests.test_roles_propose_preloads_local_execution_candidates_into_delivery_fallbacks tests.test_trace_cli.TraceAndCliTests.test_roles_tick_advances_runtime_in_batch tests.test_trace_cli.TraceAndCliTests.test_roles_tick_spawns_escalation_child_and_tracks_thread_tokens tests.test_trace_cli.TraceAndCliTests.test_roles_flow_shows_prince2_node_transitions -v
python3 -m unittest discover -s tests -v

# smoke
python3 -m stagewarden.main --json rag add design VectorSmoke HTTP_endpoint_contract
python3 -m stagewarden.main --json rag rebuild-vectors
python3 -m stagewarden.main --json rag search api mode=vector
python3 -m stagewarden.main --json rag remove rag-3
```
