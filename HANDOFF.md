# Stagewarden Handoff Summary

## Current State
- Hermes Memory standard alignment activity active on `main`; current operational plan is `TODO.md`.
- CodeGraph index current: 117 files, 3297 nodes, 10693 edges.
- Local model execution can use `scripts/run_model_omniroute.py` with free routes `auto/coding:free`, `auto/best-free`, and `coding-free-fallback`; prior smoke and opt-in live tests pass.
- `goal loop <task>` produces blueprint with scope, node graph, child prompts, execution order, tolerance matrix, exception policy, validation plan, final report.
- `goal loop run <task>` executes multi-node loop with dependency resolution, parallel execution, autonomy gates, tolerance checks, structured messaging, handoff recording.
- Existing battery wet run passes 29/29.
- Canonical simulation matrix and reusable runner now cover all 29 battery simulations and 6 categories; total and granular runs pass.

## Recent Changes
- `TODO.md`: operational standards plan and evidence log.
- `data/simulation_matrix.json`: canonical 29-case/6-category matrix.
- `scripts/run_simulation_matrix.py`: list, total, scenario, and category execution with JSON coverage.
- `AGENT_HANDOFF.md`: current detailed continuation state.
- `AGENT_POLICY.md`, `AGENT_POLICY.json`, `AGENT_MANIFESTO.md`: existing governance artifacts reviewed; no secrets added.

## Notes
- Set `RUN_MODEL_BIN=$PWD/scripts/run_model_omniroute.py` for local model calls; free routes only by default.
- Use `STAGEWARDEN_GOAL_LOOP_EXECUTION_MODE=mock` for deterministic goal-loop tests.
- Use pi mode for real AI-powered node execution (requires working provider).
- Preserve eleven pre-existing mode-only tracked changes, active `.pi-loop.json.lock`, and local `.codegraph/` index; no cleanup authorized.
- `.stagewarden_handoff.json` remains historical runtime state for completed goal-loop work; current standards activity is tracked in `AGENT_HANDOFF.md` and `TODO.md`.
