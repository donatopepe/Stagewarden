# Agent Handoff

## Current objective
Implement RAG as a first-class design-knowledge base for the Stagewarden agent: persisted locally, injected into model prompts, queryable/updatable/removable by model actions and CLI commands, automatically indexed during agent lifecycle events, deduplicated, and retrievable with deterministic lexical/fuzzy/vector matching.

## Current state
- Branch: `pr/p4-p5-updates`.
- RAG implementation is complete for this slice and focused tests pass.
- Core validation passed: `python3 -m unittest tests.test_memory tests.test_executor tests.test_agent_integration tests.test_rag tests.test_json_schema_registry -v` -> 73 OK.
- Focused battery validation passed: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_battery_cli_runs_simulated_agent_scenarios -v`.
- Full discovery was attempted with a 300s timeout; it passed the previous battery failure but timed out later in `tests.test_trace_cli` with unrelated browser/catalog/auth/model-view failures still present.
- CLI smoke passed for `rag add`, `rag rebuild-vectors`, vector-mode `rag search`, and `rag remove`.
- Runtime RAG state is persisted to `.stagewarden_rag.json` and ignored by git.

## Recent changes
- `.gitignore`: added `.stagewarden_rag.json` runtime state ignore.
- `stagewarden/rag.py`: added JSON-backed `DesignRag` and `RagEntry`, keyword/tag/phase retrieval, deterministic trigram/fuzzy matching, local hashed vector embeddings, persisted vector index, prompt rendering, timestamps, persistence, duplicate upsert, `compact()`, remove, update, vector rebuild, vector-index versioning, and robust next-id recovery.
- `stagewarden/config.py`: added `rag_filename` and `rag_path`.
- `stagewarden/agent.py`: loads/saves RAG, passes it to `Executor`, indexes project start, clarification, rejection, step completion, step observation, step failure, recovery-gate closure, and project finish.
- `stagewarden/executor.py`: injects `Design knowledge (RAG)` into primary and devil-advocate prompt packets; supports model actions `rag_search`, `rag_add`, `rag_update`, and `rag_remove`; exposes RAG actions in executor-level schema constants.
- `stagewarden/executor_prompting.py`: exposes `rag_search`, `rag_add`, `rag_update`, and `rag_remove` in model-visible action schema and examples.
- `stagewarden/rag_views.py`: added CLI report/render helpers for `rag`, `rag list`, `rag search` with `mode=lexical|vector|hybrid`, `rag add`, `rag update`, `rag remove`, `rag compact`, and `rag rebuild-vectors`.
- `stagewarden/cli_dispatch.py`: routes manual RAG CLI commands and JSON output.
- `stagewarden/commands.py`: added command catalog entries for RAG list/search/add/update/remove/compact/rebuild-vectors commands.
- `stagewarden/shell_views.py`: recognizes `rag` command prefix in interactive command detection.
- `stagewarden/battery_views.py`: `log_detection` battery path now resolves `_log_error_report` through `project_handoff_views`; focused battery regression passes.
- `tests/test_rag.py`: added coverage for RAG search/persistence, dedupe, fuzzy retrieval, local vector search, vector rebuild, compaction, executor RAG actions, prompt injection, and CLI report helpers.

## Important files
- `stagewarden/rag.py`: canonical RAG store and retrieval implementation.
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
- Bugs: No known RAG or battery-regression bugs after focused validation.
- Risks: Local hashed vectors can still miss deep semantic matches that require model-generated embeddings or an LLM reranker.
- Unknowns: Whether future project design flows should add structured domain-specific RAG entry types beyond generic phase/tags/title/content.
- Full-suite follow-up: `python3 -m unittest discover -s tests -v` timed out after 300s after reporting failures/errors in `test_browser_cli_fetch_exposes_title_and_links`, `test_catalog_refresh_and_status_use_shared_snapshot`, `test_cli_slash_choose_renders_candidates_and_json`, several interactive login/auth tests, `test_interactive_shell_model_list_uses_provider_registry_for_login_hints`, and `test_interactive_shell_persists_provider_model_variant`.

## Next steps
1. Investigate the unrelated full-discovery `test_trace_cli` browser/catalog/auth/model-view failures if this slice expands beyond RAG.
2. If semantic recall becomes insufficient, consider optional external embedding/reranker backend behind the current dependency-free vector fallback.

## Commands
```bash
# test
python3 -m py_compile stagewarden/rag.py stagewarden/rag_views.py stagewarden/agent.py stagewarden/executor.py stagewarden/cli_dispatch.py stagewarden/commands.py stagewarden/shell_views.py
python3 -m unittest tests.test_rag -v
python3 -m unittest tests.test_memory tests.test_executor tests.test_agent_integration tests.test_rag tests.test_json_schema_registry -v
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_battery_cli_runs_simulated_agent_scenarios -v
python3 -m unittest discover -s tests -v

# smoke
python3 -m stagewarden.main --json rag add design VectorSmoke HTTP_endpoint_contract
python3 -m stagewarden.main --json rag rebuild-vectors
python3 -m stagewarden.main --json rag search api mode=vector
python3 -m stagewarden.main --json rag remove rag-3
```
