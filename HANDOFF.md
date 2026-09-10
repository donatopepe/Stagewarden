# Stagewarden Handoff Summary

## Current State
- Hermes Memory standard alignment activity active on `main`; current operational plan is `TODO.md`.
- CodeGraph index current: 119 files, 3330 nodes, 10744 edges.
- Local model execution can use `scripts/run_model_omniroute.py` with free routes `auto/coding:free`, `auto/best-free`, and `coding-free-fallback`; prior smoke and opt-in live tests pass.
- `goal loop <task>` produces blueprint with scope, node graph, child prompts, execution order, tolerance matrix, exception policy, validation plan, final report.
- `goal loop run <task>` executes multi-node loop with dependency resolution, parallel execution, autonomy gates, tolerance checks, structured messaging, handoff recording.
- Existing battery wet run passes 29/29; targeted matrix/policy tests pass 9/9 and battery CLI test passes 1/1.
- Initial full suite had 472 pass, 3 interactive-shell `hello.txt` failures, 5 intentional skips. Restored executable modes 0755; all three shell tests now pass targeted. Full suite rerun pending.
- Canonical simulation matrix and reusable runner now cover all 29 battery simulations and 6 categories; total and granular runs pass.

## Recent Changes
- `TODO.md`: operational standards plan and evidence log.
- `data/simulation_matrix.json`: canonical 29-case/6-category matrix.
- `scripts/run_simulation_matrix.py`: list, total, scenario, and category execution with JSON coverage.
- `AGENT_HANDOFF.md`: current detailed continuation state.
- `AGENT_POLICY.md`, `AGENT_POLICY.json`, `AGENT_MANIFESTO.md`: governance artifacts reviewed; `AGENT_POLICY.md` links TODO/matrix/runner; no secrets added.

## Notes
- Set `RUN_MODEL_BIN=$PWD/scripts/run_model_omniroute.py` for local model calls; free routes only by default.
- Use `STAGEWARDEN_GOAL_LOOP_EXECUTION_MODE=mock` for deterministic goal-loop tests.
- Use pi mode for real AI-powered node execution (requires working provider).
- Preserve eleven pre-existing mode-only tracked changes, active `.pi-loop.json.lock`, and local `.codegraph/` index; no cleanup authorized.
- `.stagewarden_handoff.json` now records current standards activity, final evidence, blocker, and residual risks; `AGENT_HANDOFF.md` and `TODO.md` remain detailed continuation sources.
