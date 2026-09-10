# Agent Handoff

## Current objective
Apply Hermes Memory standard rules to Stagewarden without disturbing pre-existing worktree changes; make simulation coverage reproducible with canonical matrix and runners.

## Current state
- Checkout: `/home/public/Stagewarden`, branch `main`; only main worktree exists.
- CodeGraph initialized/current: 117 files, 3297 nodes, 10693 edges.
- Canonical matrix added at `data/simulation_matrix.json`: 29 existing battery scenarios, 6 categories.
- Reusable runner added at `scripts/run_simulation_matrix.py`; supports list, total, `--scenario`, and `--category`; emits JSON coverage and pass/fail evidence.
- Baseline/wet runs pass: list `29` scenarios; total `29/29`; scenario `executor_write_file` `1/1`; category `role-runtime` `10/10`.
- Existing `battery --json` wet run passes `29/29` in isolated workspace.
- Project policy artifacts define adaptive governance, MVP/no-overengineering, explicit roles, exception handling, wet-run requirement, traceability, cost control, simulation/test completeness, active role nodes, and CLI baseline; `AGENT_POLICY.md` now links TODO, matrix, and runner artifacts.

## Recent changes
- `TODO.md`: created as single operational plan; controls, dependencies, evidence, blockers, and validations recorded.
- `data/simulation_matrix.json`: canonical scenario/category catalog mapped one-to-one to existing `battery_views.py` scenarios.
- `scripts/run_simulation_matrix.py`: deterministic total/granular runner with validation and machine-readable report.
- `.codegraph/`: local CodeGraph index created; do not commit unless project policy later requires it.
- No tracked source content changed by this activity except new untracked artifacts; eleven pre-existing mode-only changes preserved.

## Important files
- `AGENT_HANDOFF.md`: current continuation state.
- `HANDOFF.md`: legacy project summary, still aligned with prior OmniRoute/goal-loop capabilities.
- `.stagewarden_handoff.json`: persisted Stagewarden runtime handoff; remains historical goal-loop state and is ignored by git.
- `TODO.md`: current operational plan and evidence log.
- `data/simulation_matrix.json`: source of simulation cases.
- `scripts/run_simulation_matrix.py`: total/granular runner.
- `stagewarden/battery_views.py`: implementation source for 29 simulations.
- `AGENT_MANIFESTO.md`, `AGENT_POLICY.md`, `AGENT_POLICY.json`: governance rules and repository artifact map.
- `README.md`: user-facing matrix commands and wet-run behavior.

## Technical decisions
- Preserve pre-existing mode-only changes and active `.pi-loop.json.lock`; no cleanup without explicit authorization.
- Use existing battery implementation as MVP baseline; matrix catalogs real scenarios rather than inventing new cases.
- Runner invokes real `stagewarden battery --json` execution in a temporary workspace, then filters selected cases; no mock-only closure.
- Keep secrets out of repository and Hermes memory.

## Open issues
- `.stagewarden_handoff.json`, `HANDOFF.md`, and prior handoff entries describe earlier OmniRoute/goal-loop work; they are not overwritten because they are historical runtime state. Current activity is documented in `AGENT_HANDOFF.md` and `TODO.md`.
- Existing mode-only worktree changes are uncommitted and likely environment-induced; inspect before any commit.
- Full offline suite and external OmniRoute/OpenRouter checks are not rerun in this activity; prior handoff records their last known results.

## Next steps
1. Run final targeted tests/audits: matrix runner, policy docs, trace CLI battery, `git diff --check`, JSON/handoff consistency.
2. Update `TODO.md` and this handoff with final evidence.
3. Leave pre-existing mode-only changes, `.pi-loop.json.lock`, and `.codegraph/` untouched unless explicitly requested.

## Commands
```bash
python3 -m pip install -e .
./scripts/run_simulation_matrix.py --list
./scripts/run_simulation_matrix.py
./scripts/run_simulation_matrix.py --scenario executor_write_file
./scripts/run_simulation_matrix.py --category role-runtime
python3 -m unittest tests.test_policy_docs tests.test_trace_cli.Policy?  # use targeted test names from suite
python3 -m unittest discover -s tests
```
