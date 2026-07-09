# Agent Handoff

## Current objective
Complete remaining goal-loop features: interactive autonomy gate, goal loop status command, improved observability.

## Current state
- **Interactive autonomy gate**: when `goal loop run` runs without `--json`, high-risk decisions prompt user via stdin with `y/N`. User decline marks node as "blocked".
- **`goal loop status` command**: shows running/completed state, node statuses, latest phase, summary, total actions from handoff entries.
- **Schema coverage**: `goal loop status` registered in JSON schema registry.
- **All 4 goal-loop tests pass**.
- **Everything committed and pushed** to `origin/main`.

## Recent changes
- `stagewarden/goal_loop_orchestrator.py`: `json_mode` parameter, interactive `_autonomy_gate` with `input()` prompt.
- `stagewarden/cli_dispatch.py`: pass `json_mode` to orchestrator, route `goal loop status`.
- `stagewarden/goal_loop_views.py`: `goal_loop_status_report()` and `render_goal_loop_status()` functions.
- `stagewarden/commands.py`: `goal loop status` command spec + help topic update.
- `stagewarden/json_schema_registry.py`: `stagewarden.goal_loop_status` schema id.
- `tests/test_json_schema_registry.py`: `goal loop status` in expected set.

## Important files
- `stagewarden/goal_loop_orchestrator.py`: interactive autonomy gate.
- `stagewarden/goal_loop_views.py`: status report builder + renderer.
- `stagewarden/cli_dispatch.py`: routing for all goal loop commands.
- `stagewarden/commands.py`: command specs + help topics.
- `stagewarden/json_schema_registry.py`: schema ids.

## Technical decisions
- Decision: `running` = `goal_loop_start` present AND no `goal_loop_end` present.
  - Reason: a session can have both start and end entries; end supersedes running.
- Decision: autonomy gate uses `input()` for interactive prompt.
  - Reason: simplest cross-platform approach for non-JSON mode.
  - Trade-offs: blocks on stdin; may hang in CI without TTY.

## Next steps
1. Add custom node implementations via Stagewarden extensions (sandboxed execution).
2. Add control socket for external node injection into running goal loops.
3. Run full pi benchmark against orchestration surface.

## Commands
```bash
# test
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_goal_loop_run_executes_all_nodes_and_reports_final_status tests.test_trace_cli.TraceAndCliTests.test_goal_loop_blueprint_surfaces_scope_graph_validation_and_pi_benchmark
# wet-run (mock)
STAGEWARDEN_GOAL_LOOP_EXECUTION_MODE=mock python3 -m stagewarden.main "goal loop run Build a multi-node goal loop" --json
# status
python3 -m stagewarden.main "goal loop status"
```
