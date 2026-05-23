# Agent Handoff

## Current objective
Implement RAG as a first-class design-knowledge base for the Stagewarden agent: persisted locally, injected into model prompts, queryable/updatable/removable by model actions and CLI commands, automatically indexed during agent lifecycle events, deduplicated, and retrievable with deterministic lexical/fuzzy/vector matching.

## Current state
- PR `#1` was merged into `main` (`merge commit 26f53f4ef419e1b22aade0b0cc9b7704cedd2428`) and the feature branch `pr/p4-p5-updates` was deleted locally/remotely.
- Current branch: `main`.
- RAG implementation is complete for this slice and focused tests pass, including hardening found during deep review.
- Core validation passed: `python3 -m unittest tests.test_memory tests.test_executor tests.test_agent_integration tests.test_rag tests.test_json_schema_registry -v` -> 74 OK.
- Focused battery validation passed: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_battery_cli_runs_simulated_agent_scenarios -v`.
- Full validation passed: `python3 -m unittest discover -s tests -v` -> 425 OK.
- CLI smoke passed for `rag add`, `rag rebuild-vectors`, vector-mode `rag search`, and `rag remove`.
- Runtime RAG state is persisted to `.stagewarden_rag.json` and ignored by git.

## Recent changes
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
- `stagewarden/rag.py`: canonical RAG store and retrieval implementation; prompt rendering escapes embedded fences and rebuilds vectors on load to avoid stale persisted embeddings.
- `stagewarden/agent.py`: lifecycle auto-indexing and RAG ownership for agent runs.
- `stagewarden/executor.py`: prompt injection and model action execution path.
- `stagewarden/rag_views.py`: manual CLI surface for RAG.
- `tests/test_rag.py`: dedicated regression coverage for this slice.
- `.stagewarden_rag.json`: local runtime design-knowledge store, intentionally gitignored.

## Technical decisions
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
2. Optionally include explicit failing delta entries in `latest=true` output payload for easier machine triage.

## Open issues
- Bugs: No known RAG, battery, trace-CLI, or full-suite bugs after validation.
- Risks: Local hashed vectors can still miss deep semantic matches that require model-generated embeddings or an LLM reranker.
- Unknowns: Whether future project design flows should add structured domain-specific RAG entry types beyond generic phase/tags/title/content.
- Full-suite follow-up: completed. RAG-focused suite revalidated (`python3 -m unittest tests.test_rag -v` -> 14 OK), extended impact validation passed (`python3 -m unittest tests.test_executor tests.test_agent_integration -v` -> 56 OK), trace CLI passed (`python3 -m unittest tests.test_trace_cli -v` -> 200 OK), and full discovery passed (`python3 -m unittest discover -s tests -v` -> 426 OK). v3.4 CLI/schema checks passed (`python3 -m unittest tests.test_rag tests.test_json_schema_registry -v` -> 14 OK). v3.5 role-policy checks passed (`python3 -m unittest tests.test_rag tests.test_executor.ExecutorTests.test_model_visible_tool_schema_matches_executor_actions -v` -> 15 OK), including executor role-fallback wiring. v3.6 history/trend checks passed (`python3 -m unittest tests.test_rag tests.test_json_schema_registry -v` -> 17 OK). trend-render detail follow-up passed (`python3 -m unittest tests.test_rag -v` -> 15 OK). policy-source introspection checks passed (`python3 -m unittest tests.test_rag tests.test_executor.ExecutorTests.test_model_visible_tool_schema_matches_executor_actions -v` -> 16 OK). retention-control checks passed (`python3 -m unittest tests.test_rag tests.test_json_schema_registry -v` -> 17 OK). search-render policy metadata checks passed (`python3 -m unittest tests.test_rag -v` -> 15 OK). timestamp-envelope history checks passed (`python3 -m unittest tests.test_rag tests.test_json_schema_registry -v` -> 17 OK). trend-window visibility checks passed (`python3 -m unittest tests.test_rag tests.test_json_schema_registry -v` -> 17 OK). latest-delta mode checks passed (`python3 -m unittest tests.test_rag tests.test_json_schema_registry -v` -> 17 OK). latest warn-threshold checks passed (`python3 -m unittest tests.test_rag tests.test_json_schema_registry -v` -> 17 OK). latest-pass gate checks passed (`python3 -m unittest tests.test_rag tests.test_json_schema_registry -v` -> 17 OK).

## Next steps
1. No immediate follow-up is pending for the completed RAG/trace-regression slice.
2. If semantic recall becomes insufficient, consider optional external embedding/reranker backend behind the current dependency-free vector fallback.

## Starting point note
- Start from `main` with a clean worktree.
- Keep PR scope narrow (single objective per branch) and preserve current RAG behavior/contracts.
- Re-run at least focused tests for touched modules; run full discovery for cross-cutting/runtime-impacting changes.

## Commands
```bash
# test
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
