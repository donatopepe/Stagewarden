# Agent Handoff

## Current objective
Provider tree runtime integration and Hermes/Obsidian memory MVP complete; local OmniRoute transport validated 3/4 cases, bounded real-Agent completion explicitly blocked.

## Current state
- Checkout: `/home/public/Stagewarden`, branch `main`; only main worktree exists.
- CodeGraph synced/current: 125 files, 3422 nodes, 10937 edges.
- Canonical matrix added at `data/simulation_matrix.json`: 29 existing battery scenarios, 6 categories.
- Reusable runner added at `scripts/run_simulation_matrix.py`; supports list, total, `--scenario`, and `--category`; emits JSON coverage and pass/fail evidence.
- Baseline/wet runs pass: list `29` scenarios; total `29/29`; scenario `executor_write_file` `1/1`; category `role-runtime` `10/10`.
- Existing `battery --json` wet run passes `29/29` in isolated workspace; current full suite passes `487/487` with `5` intentional skips.
- Project policy artifacts define adaptive governance, MVP/no-overengineering, explicit roles, exception handling, wet-run requirement, traceability, cost control, simulation/test completeness, active role nodes, and CLI baseline; `AGENT_POLICY.md` links TODO, matrix, and runner artifacts.
- Provider tree MVP passes: `models/providers/index.json` plus five provider JSON files, 238 records conserved; provider-tree tests 3/3.
- Runtime provider integration passes: valid tree precedence, malformed/missing fallback to legacy catalog, registry override; provider/model/router/runtime tests 30/30.
- Local OmniRoute adapter/smoke/opt-in live tests pass; loop iteration #28 reconfirmed stable inventory at `2060` models; stable SHA-256 `76e45187d90f41469bfd680ae7d974352ec40c76ee04b97c7abf7cadb891cf2c`, five expected routes present. Prior `auto/best-coding-fast` retry remained `ok=false`, `steps=2`; same non-terminal action-flow blocker persists, so no retry. Fixed local runtime evidence is 3/4; fail-closed critic parser retained.
- Hermes/Obsidian memory MVP passes: read-only Markdown roots/files, root traversal rejection, max-char bound, prompt integration, `memory status` CLI/schema. Memory context 5/5; combined memory/executor/parser 75/75.
- Standard memory controls applied: CodeGraph first, TODO operational source, main checkout only, MVP-first, reusable automation, UTF-8/no secrets, handoff continuity, wet-run evidence.

## Recent changes
- `TODO.md`: current operational plan; provider tree and Hermes/Obsidian memory MVP complete; loop iteration #28 evidence and bounded Agent blocker recorded.
- `data/simulation_matrix.json`: canonical scenario/category catalog mapped one-to-one to existing `battery_views.py` scenarios.
- `models/providers/index.json`, `models/providers/*.json`: provider model tree generated from legacy catalog.
- `models/providers/README.md`: provider-tree layout and regeneration contract.
- `stagewarden/memory_context.py`: read-only configured Markdown context loader.
- `tests/test_memory_context.py`, `tests/test_memory_status_cli.py`: memory behavior/status tests.
- `scripts/generate_provider_model_tree.py`: reproducible provider-tree generator.
- `tests/test_provider_model_tree.py`: provider-tree validity/conservation/secret-field tests.
- `scripts/run_simulation_matrix.py`: deterministic total/granular runner with validation and machine-readable report.
- `.codegraph/`: local CodeGraph index synced; tracked ignore metadata preserved.
- `README.md` and `AGENT_POLICY.md`: document matrix and runner.
- Eleven historical executable files are tracked at 0755 after workspace initialization changed them to 0644. No content cleanup performed.

## Important files
- `AGENT_HANDOFF.md`: current continuation state.
- `HANDOFF.md`: legacy project summary, still aligned with prior OmniRoute/goal-loop capabilities.
- `.stagewarden_handoff.json`: persisted runtime handoff with provider-tree evidence, open memory/config work, and residual risks.
- `TODO.md`: current operational plan and evidence log.
- `data/simulation_matrix.json`: source of simulation cases.
- `scripts/run_simulation_matrix.py`: total/granular runner.
- `stagewarden/battery_views.py`: implementation source for 29 simulations.
- `AGENT_MANIFESTO.md`, `AGENT_POLICY.md`, `AGENT_POLICY.json`: governance rules and repository artifact map.
- `README.md`: user-facing matrix commands and wet-run behavior.
- `/home/public/HermesVault/Memory/pi-memory.md`, `decisions.md`, `projects.md`, `conversation-log.md`: canonical memory context read before this activity; no secrets copied.

## Technical decisions
- Preserve active `.pi-loop.json.lock`; executable mode correction was required for tests and is now tracked at 0755.
- Use existing battery implementation as MVP baseline; matrix catalogs real scenarios rather than inventing new cases.
- Generate provider files from `data/ai_models_catalog.json`; preserve legacy catalog until runtime precedence is explicitly implemented.
- Runner invokes real `stagewarden battery --json` execution in a temporary workspace, then filters selected cases; no mock-only closure.
- Keep secrets out of repository and Hermes memory.

## Open issues
- External OmniRoute/OpenRouter checks not rerun; prior evidence retained.
- Bounded real-Agent completion remains blocked by repeated non-terminal free-route behavior; wait for route/model state change.
- `.pi-loop.json.lock` remains preserved.

## Next steps
1. Loop iteration #28 completed: stable route inventory, targeted regressions, local OmniRoute adapter/smoke/live checks, simulation matrix `29/29`, full suite `487/487` with `5` intentional skips, source-text UTF-8/no-BOM scan `180/180`, and diff check pass.
2. Stop bounded Agent retries until route/model behavior changes; preserve fail-closed critic parser.
3. Preserve current uncommitted tree and do not clean lock/index artifacts without authorization.

## Loop contract
- Loop prompt: continue Stagewarden work from `TODO.md`; one bounded iteration per trigger.
- Re-read TODO, handoff, CodeGraph, and Hermes memory each iteration.
- Stop on repeated model/environment blocker, green acceptance, or user cancellation.
- No new worktree, secrets, parser weakening, or unverified completion claims.

## Commands
```bash
python3 -m pip install -e .
./scripts/run_simulation_matrix.py --list
./scripts/run_simulation_matrix.py
./scripts/run_simulation_matrix.py --scenario executor_write_file
./scripts/run_simulation_matrix.py --category role-runtime
python3 -m unittest tests.test_simulation_matrix tests.test_policy_docs
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_battery_cli_runs_simulated_agent_scenarios
python3 -m unittest discover -s tests
```
