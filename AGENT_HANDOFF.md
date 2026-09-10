# Agent Handoff

## Current objective
Apply Hermes Memory standard rules to Stagewarden without disturbing pre-existing worktree changes; make simulation coverage reproducible with canonical matrix and runners.

## Current state
- Checkout: `/home/public/Stagewarden`, branch `main`; only main worktree exists.
- CodeGraph synced/current: 119 files, 3330 nodes, 10744 edges.
- Canonical matrix added at `data/simulation_matrix.json`: 29 existing battery scenarios, 6 categories.
- Reusable runner added at `scripts/run_simulation_matrix.py`; supports list, total, `--scenario`, and `--category`; emits JSON coverage and pass/fail evidence.
- Baseline/wet runs pass: list `29` scenarios; total `29/29`; scenario `executor_write_file` `1/1`; category `role-runtime` `10/10`.
- Existing `battery --json` wet run passes `29/29` in isolated workspace.
- Project policy artifacts define adaptive governance, MVP/no-overengineering, explicit roles, exception handling, wet-run requirement, traceability, cost control, simulation/test completeness, active role nodes, and CLI baseline; `AGENT_POLICY.md` links TODO, matrix, and runner artifacts.
- Targeted validation passes: matrix/policy tests 9/9; battery CLI test 1/1; all three interactive-shell tests 3/3 after restoring executable modes. Full suite rerun pending.

## Recent changes
- `TODO.md`: created as single operational plan; controls, dependencies, evidence, blockers, and validations recorded.
- `data/simulation_matrix.json`: canonical scenario/category catalog mapped one-to-one to existing `battery_views.py` scenarios.
- `scripts/run_simulation_matrix.py`: deterministic total/granular runner with validation and machine-readable report.
- `.codegraph/`: local CodeGraph index synced; tracked ignore metadata preserved.
- `README.md` and `AGENT_POLICY.md`: document matrix and runner.
- Eleven historical executable files were restored to tracked mode 0755 after workspace initialization changed them to 0644. No content cleanup performed.

## Important files
- `AGENT_HANDOFF.md`: current continuation state.
- `HANDOFF.md`: legacy project summary, still aligned with prior OmniRoute/goal-loop capabilities.
- `.stagewarden_handoff.json`: persisted Stagewarden runtime handoff with current standards activity, final evidence, blocker, and residual risks.
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
- Initial shell failures were caused by executable bits changed to 0644; restored 0755 and targeted shell tests now pass. Full suite rerun pending.
- External OmniRoute/OpenRouter checks not rerun in this activity; prior handoff records their last known results.
- `.pi-loop.json.lock` remains preserved.

## Next steps
1. Investigate three interactive-shell failures separately.
2. Rerun OmniRoute/OpenRouter live checks when provider availability permits.
3. Preserve current matrix evidence and do not clean lock/index artifacts without authorization.

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
