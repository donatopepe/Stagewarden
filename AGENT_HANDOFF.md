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
- PRINCE2 enforcement slice completed: coding work-package `complete` actions now require prior successful non-model tool evidence for the same step when the step explicitly involves code/tests (`pytest`, `unittest`, `tests/`, file extensions, or code-and-tests wording). Narrative claims such as `passed exit_code=0` are rejected without tool transcript evidence.
- Validation for enforcement slice: RED observed with `python3 -m unittest tests.test_executor.ExecutorTests.test_executor_rejects_coding_completion_without_prior_tool_evidence -v` failing because the narrative completion was accepted; after implementation, the new reject/accept evidence tests pass, `py_compile` passes, and `python3 -m unittest tests.test_executor -v` -> 52 OK.
- PRINCE2 product checkpoint slice completed: completed coding/product-mutating steps now write `product_checkpoint` handoff entries with product description, acceptance criteria, quality-gate evidence, checkpoint status, model/action metadata, and product id for downstream continuation.
- Validation for checkpoint slice: RED observed in `tests.test_agent_integration.AgentIntegrationTests.test_agent_completes_task_with_stub_backend` because no `product_checkpoint` entries existed; GREEN focused run passed, and `python3 -m py_compile stagewarden/agent.py stagewarden/project_handoff.py tests/test_agent_integration.py && python3 -m unittest <5 non-live agent integration tests> tests.test_executor -v` -> 57 OK. Full `tests.test_agent_integration tests.test_executor` still hits the known OpenRouter API-key failure in `test_agent_verbose_output_shows_handoff_runtime_details` before product code.
- PRINCE2 checkpoint recovery slice completed: on resume after a failed completion/quality gate, the planner now uses the latest `product_checkpoint` to insert a dedicated `checkpoint-recovery-step-*` before retrying the blocked work package, so Stagewarden captures the missing non-model evidence instead of immediately repeating the same closure prompt.
- PRINCE2 live checkpoint recovery slice completed: during the same agent run, failed completion/quality gates (`wet_run_required`, `prince2_closure_failure`, `response_insufficient`) now insert a ready `checkpoint-recovery-step-*` from the latest `product_checkpoint`, demote the blocked work package back to planned, and sync the implementation backlog so the next iteration captures missing evidence before retrying closure.
- Validation for checkpoint recovery slices: RED observed in `tests.test_planner.PlannerTests.test_create_plan_injects_checkpoint_recovery_for_failed_completion_gate` because no recovery step was generated; RED observed in `tests.test_agent_integration.AgentIntegrationTests.test_agent_inserts_live_checkpoint_recovery_step_after_completion_gate_failure` because the live insertion hook did not exist. GREEN focused runs passed, `python3 -m py_compile stagewarden/agent.py stagewarden/planner.py tests/test_agent_integration.py tests/test_planner.py` passed, `python3 -m unittest tests.test_planner tests.test_executor <5 non-live agent integration tests> -v` -> 65 OK.
- PRINCE2 non-coding product-evidence enforcement slice completed: `complete` now also requires prior successful same-step non-model tool evidence for wet-run-required design/documentation/specification artifacts, not only explicit code/test work packages. The broadening is intentionally limited to concrete artifact markers (`design`, `architecture`, `ADR`, `documentation`, `docs/`, `.md`, `specification`, etc.) so routing/planning control steps can still flow to response-quality gates instead of being misclassified as product closure.
- Ambiguous-brief clarification slice completed: required project-brief fields that contain placeholder values (`TBD`, `unknown`, `to be decided`, `da definire`, etc.) now become explicit `ambiguous_<field>` clarification gaps in project design/tree/start flows, preventing Stagewarden from approving startup from placeholders or assumptions.
- Validation for ambiguous-brief slice: RED observed in `tests.test_trace_cli.TraceAndCliTests.test_project_start_requests_clarification_for_ambiguous_brief_values` because `objective=TBD` still approved startup; GREEN focused run passed with py_compile plus project-start/tree clarification regressions, persistence/PRINCE2 coverage, and ready-project startup regressions.
- Full regression validation after ambiguous-brief slice passed with explicit Hermes env sourcing: `set -a; . ~/.hermes/.env; set +a; python3.11 -m unittest discover -s tests -q` -> 440 OK in 1064.353s.
- Project-brief guidance ambiguity slice completed: `project brief` and `project brief set` now surface ambiguous required values before later missing fields, expose `ambiguous_gaps` and `next_missing_gap` in JSON, and tell the operator to replace the ambiguous value with a concrete one.
- Validation for project-brief guidance ambiguity slice: RED observed in `tests.test_trace_cli.TraceAndCliTests.test_project_brief_set_reports_ambiguous_field_before_missing_fields` because `objective=TBD` guidance skipped to missing `scope`; GREEN focused run passed, then py_compile plus brief/start/design regressions and project-tree proposal/approval regressions passed.
- Stale-baseline-on-brief-change slice completed: after a Project Board/project-tree approval, `project brief set` and `project brief clear` now mark the persisted PRINCE2 role-tree baseline `stale` when the current brief diverges from the approved proposal brief. `roles baseline` text/JSON now surfaces `status=stale`, changed fields, stale reason, and the required action to rerun proposal/review/approval before execution continues.
- Validation for stale-baseline slice: RED observed in `tests.test_trace_cli.TraceAndCliTests.test_project_brief_change_marks_approved_project_tree_baseline_stale` because a changed approved scope did not stale the baseline; RED observed in `test_project_brief_clear_marks_approved_project_tree_baseline_stale` because clearing an approved delivery mode did not stale the baseline. GREEN focused runs passed; `py_compile` plus 4 tree/baseline regressions passed; broader brief/start/tree/persistence/PRINCE2 regression passed (`30 OK`).
- Stale-baseline execution-gate slice completed: `roles runtime`, `roles tick`, `role tick <node_id>`, and `project start` now refuse to continue from a `stale` role-tree/project-tree baseline, returning `blocked_stale_baseline` with changed fields and the rerun proposal/review/approval action in text and JSON.
- Validation for stale-baseline execution-gate slice: RED observed in `tests.test_trace_cli.TraceAndCliTests.test_stale_project_tree_baseline_blocks_runtime_and_tick_execution` because `roles runtime` returned 0 against a stale baseline and `project start` only returned generic `blocked`; GREEN focused run passed, then py_compile plus 6 runtime/start/baseline regressions passed, followed by 29-test broader project-start/runtime/PRINCE2/persistence regression passing. Full discovery validation also passed with explicit Hermes env sourcing: `set -a; . ~/.hermes/.env; set +a; python3.11 -m unittest discover -s tests -q` -> 444 tests OK, 1 skipped, in 1129.903s.
- Stale-baseline supervision-view slice completed: `roles active`, `roles queues`, `roles control`, and `roles messages` stay non-blocking/readable on a stale approved baseline, but text and JSON now include stale-baseline warning/context so supervision cannot be mistaken for execution approval.
- Validation for stale-baseline supervision-view slice: RED observed in `tests.test_trace_cli.TraceAndCliTests.test_stale_project_tree_baseline_marks_supervision_views_without_blocking_them` because `roles active` lacked the warning; GREEN focused run passed, targeted 6-test runtime/supervision/persistence regression passed, and full discovery passed with explicit Hermes env sourcing: `set -a; . ~/.hermes/.env; set +a; python3.11 -m unittest discover -s tests -q` -> 445 tests OK in 1167.000s.
- Validation for non-coding evidence slice: RED observed in `tests.test_executor.ExecutorTests.test_executor_rejects_design_work_package_completion_without_prior_tool_evidence` because a narrative-only ADR/design closure was accepted; GREEN focused reject/accept design tests passed; `python3 -m py_compile stagewarden/executor.py tests/test_executor.py && python3 -m unittest tests.test_executor tests.test_planner -v` -> 62 OK.
- Non-coding evidence enforcement follow-up completed for research/report/plan artifacts: concrete report/plan file completions now require prior same-step non-model tool evidence, while generic planning/review steps without an explicit file/path artifact remain non-blocking. RED observed on research report file and implementation plan file completions; GREEN focused evidence tests passed; executor/planner/agent-integration regression passed with env sourced (`74 OK`), and full discovery passed with explicit Hermes env sourcing: `set -a; . ~/.hermes/.env; set +a; python3.11 -m unittest discover -s tests -q` -> 449 tests OK in 1136.235s.

## Recent changes
- `stagewarden/project/role_flow.py`: added shared stale-baseline block payload/render helpers and guards for `roles tick` plus `role tick <node_id>` before runtime advancement.
- `stagewarden/project/role_runtime_views.py`: `roles runtime` text/JSON now returns `blocked_stale_baseline` instead of materializing runtime from a stale baseline.
- `stagewarden/project/role_runtime_views.py`: supervision-only views (`roles active`, `roles queues`, `roles control`, `roles messages`) now prepend text warnings and add JSON stale context without changing their non-blocking exit behavior.
- `stagewarden/project/start_flow.py`: `project start` now blocks with `blocked_stale_baseline` when the approved project tree is stale, instead of silently approving/replanning from obsolete approval.
- `stagewarden/project/role_command_flow.py` and `stagewarden/cli_dispatch.py`: role/roles runtime command surfaces now return non-zero status and machine-readable stale block payloads for blocked execution.
- `tests/test_trace_cli.py`: added RED/GREEN coverage for stale-baseline execution gates across `roles runtime`, `roles tick`, `role tick`, and `project start`.
- `tests/test_trace_cli.py`: added RED/GREEN coverage proving stale-baseline supervision views remain readable while surfacing warning/context.
- `stagewarden/executor.py`: broadened wet-run completion gating to research/report/plan file artifacts using explicit artifact/action matching, avoiding false positives on generic planning/control/analysis steps.
- `tests/test_executor.py`: added RED/GREEN coverage for research report file and implementation plan file evidence gates plus a generic planning non-blocking guard.
- `stagewarden/project/brief.py`: marks an approved project-tree/role-tree baseline stale when `project brief set` or `project brief clear` changes fields compared with the approved proposal brief; CLI output tells the operator to rerun proposal/review/approval.
- `stagewarden/project/role_tree_views.py`: `roles baseline` text/JSON now reports the baseline's actual status (`approved` or `stale`) and renders stale reason/changed fields/action.
- `stagewarden/modelprefs.py`: preserves the structured `stale` payload in normalized persisted role-tree baselines.
- `tests/test_trace_cli.py`: added RED/GREEN coverage for brief set/clear invalidating approved baselines.
- `stagewarden/executor_prompting.py`: added `coding_work_package_controls_section(...)`, a PRINCE2/product-delivery control block for coding work packages (product focus, expected output, acceptance criteria, quality gates, TDD, minimal implementation, focused wet-run, scope control, evidence rule, escalation boundary).
- `stagewarden/executor.py`: `_build_model_communication_packet(...)` now injects a bounded `Coding work package controls` section into model prompts before the broader model-context/handoff sections.
- `tests/test_executor.py`: added `test_executor_prompt_includes_coding_work_package_controls_for_code_steps`, written and observed failing first, then passing after implementation.
- `stagewarden/executor.py`: added a completion enforcement gate for explicit coding/test work packages so `complete` requires prior successful same-step non-model tool transcript evidence; this prevents narrative-only claims of executed tests from closing the step.
- `stagewarden/executor.py`: broadened the same prior-tool-evidence closure gate to wet-run-required non-coding product artifacts such as design docs, architecture decisions, ADRs, documentation, and specifications while avoiding generic planning/routing terms.
- `tests/test_executor.py`: added reject/accept coverage for coding completion evidence: one RED test proving narrative-only completion is blocked, and one positive test proving prior shell/tool evidence allows completion.
- `tests/test_executor.py`: added RED/GREEN reject/accept coverage for design/ADR work-package completion evidence, proving narrative-only design closure is blocked unless same-step file/tool evidence exists.
- `stagewarden/project_handoff.py`: added `record_product_checkpoint(...)`, persisting PRINCE2-style product/checkpoint handoff entries with structured details.
- `stagewarden/agent.py`: records a `product_checkpoint` immediately after a completed code/product-mutating work package before indexing the step-completed RAG phase; also injects a live `checkpoint-recovery-step-*` when a completion/quality gate fails and a prior product checkpoint can guide missing-evidence recovery.
- `stagewarden/planner.py`: injects a `checkpoint-recovery-step-*` from the latest `product_checkpoint` when a resumed run starts from a failed completion/quality gate, carrying the blocked stage, failed gate text, product description, acceptance criteria, and prior evidence into the next executable step.
- `tests/test_agent_integration.py`: extended the stub-backend happy-path test to assert persisted product checkpoint entries and structured detail fields; added live checkpoint-recovery insertion coverage.
- `tests/test_planner.py`: added RED/GREEN coverage for checkpoint-driven recovery step generation after a failed wet-run/completion gate.
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
- Decision: Block runtime/start execution from stale approved role-tree baselines.
  - Reason: surfacing stale metadata is insufficient if runtime/tick/start paths can still advance work from obsolete governance approval.
  - Trade-offs: operators must explicitly rerun proposal/review/approval after a brief change; this is safer and auditable, and the block payload includes changed fields and the exact recovery action.
- Decision: Keep supervision-only role views non-blocking on stale approved baselines while annotating them with stale context.
  - Reason: operators still need to inspect active nodes, queues, control signals, and messages to recover safely; these views do not advance execution.
  - Trade-offs: stale views remain accessible, so the warning is explicit in both text and JSON to avoid implying authorization to continue delivery.
- Decision: Mark approved role-tree baselines stale when the project brief changes after approval.
  - Reason: PRINCE2 execution must not continue against an obsolete baseline when the user's requirements have changed; the project should repeat propose/review/approve before delivery proceeds.
  - Trade-offs: a brief typo/change creates an explicit stale state that may require reapproval; mitigated by surfacing changed fields and preserving the previous approved proposal for comparison.
- Decision: Treat coding steps as PRINCE2-style work packages in the executor prompt, not only as generic model tasks.
  - Reason: the delivery agent must optimize for concrete products, explicit acceptance criteria, quality evidence, and exception escalation, which directly supports designing and writing better code.
  - Trade-offs: slightly more prompt budget per step; mitigated by bounding the section to 2500 chars and deriving content from existing brief/step fields.
- Decision: Keep the first tranche prompt-level and TDD-covered rather than adding a new command or persistence format.
  - Reason: prompt packet assembly is the highest-leverage path shared by primary execution and assurance flows, and avoids schema churn while proving behavior.
  - Trade-offs: controls guide model behavior but do not yet hard-fail every non-coding step that omits evidence; explicit coding/test work packages now have a narrow hard gate.
- Decision: Require same-step successful tool transcript evidence before accepting `complete` on explicit coding/test work packages.
  - Reason: a model can otherwise claim `ran tests` or `exit_code=0` in text without Stagewarden having executed or recorded the validation.
  - Trade-offs: the first enforcement slice used conservative code/test markers to avoid breaking non-coding routing/status tests.
- Decision: Broaden same-step tool-evidence enforcement to concrete non-coding product artifacts (design docs, architecture decisions, ADRs, documentation, specifications) without matching generic control terms like `work package` or `plan` alone.
  - Reason: non-code products can be fabricated narratively too; closure needs a real file/tool transcript once the step explicitly asks for a product artifact.
  - Trade-offs: generic planning/review steps still rely on response-quality and PRINCE2 closure gates until they emit structured artifact evidence consistently.
- Decision: Extend same-step tool-evidence enforcement to research/report/plan outputs only when the step explicitly asks to create/produce/write a concrete file/path/named artifact.
  - Reason: research reports and plan files are product artifacts and should not close on narrative claims alone.
  - Trade-offs: generic analysis, status reporting, and planning/control steps remain outside this hard gate to avoid blocking non-product decisions; the matcher uses whole-word report/plan markers plus explicit artifact references/actions.
- Decision: Persist completed coding/product-mutating work packages as explicit PRINCE2 `product_checkpoint` handoff entries.
  - Reason: downstream agents need a compact product description, acceptance criteria, quality evidence, and checkpoint status, not only raw observation text.
  - Trade-offs: checkpoint creation is intentionally limited to code/product-mutating action types or explicit code/test markers to avoid noisy handoff entries for purely analytical steps.
- Decision: Use product checkpoints to create a recovery lane after failed completion/quality gates both during the live run and on resume.
  - Reason: a failed closure with incomplete evidence should produce a concrete next work package for capturing missing evidence instead of repeating the same prompt or relying on narrative retry.
  - Trade-offs: recovery requires at least one prior `product_checkpoint`; projects with no completed/checkpointed product still fall back to the existing issue/exception controls.
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
- Risks: Full `unittest discover` requires explicit environment sourcing for OpenRouter-backed tests in this Hermes process; current full suite is green when run as `set -a; . ~/.hermes/.env; set +a; python3.11 -m unittest discover -s tests -q` -> 445 OK, 1167.000s after the supervision-view slice.
- Risks: Local hashed vectors can still miss deep semantic matches that require model-generated embeddings or an LLM reranker.
- Risks: `openrouter benchmark` trace test appears intermittently flaky under full-suite load; keep monitoring and re-run isolated test before treating as product regression.
- Risks: Live OpenRouter benchmark remains externally dependent (provider/network/rate limits); test now treats explicit case-level provider errors as transient skips.
- Unknowns: Whether future project design flows should add structured domain-specific RAG entry types beyond generic phase/tags/title/content.

## Next steps
1. Inspect repository status after the research/report/plan evidence-gate commit and choose the next narrow PRINCE2 governance slice only if a concrete gap remains.
2. If semantic recall becomes insufficient, consider optional external embedding/reranker backend behind the current dependency-free vector fallback.

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
set -a; . ~/.hermes/.env; set +a; python3.11 -m unittest discover -s tests -q
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
