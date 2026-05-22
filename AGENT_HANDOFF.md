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

## Open issues
- Bugs: No known RAG, battery, trace-CLI, or full-suite bugs after validation.
- Risks: Local hashed vectors can still miss deep semantic matches that require model-generated embeddings or an LLM reranker.
- Unknowns: Whether future project design flows should add structured domain-specific RAG entry types beyond generic phase/tags/title/content.
- Full-suite follow-up: RAG-focused suite revalidated after RAG v2 ranking/dedup changes (`python3 -m unittest tests.test_rag -v` -> 10 OK). Extended impact validation also passed (`python3 -m unittest tests.test_executor tests.test_agent_integration -v` -> 56 OK). Full trace CLI module passed (`python3 -m unittest tests.test_trace_cli -v` -> 200 OK).

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
