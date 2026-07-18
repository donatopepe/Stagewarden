# Agent Handoff

## Current objective
Make public portfolio build reproducible and route Stagewarden live model checks through local OmniRoute free models.

## Current state
- Local OmniRoute adapter added at `scripts/run_model_omniroute.py`; defaults to free routes and falls back across `auto/coding:free`, `auto/best-free`, and `coding-free-fallback`.
- `scripts/test_omniroute_free.sh` and unit/opt-in live tests pass against local OmniRoute at `127.0.0.1:20128`.
- Live OpenRouter tests skip when their external key is absent instead of failing the offline suite.
- Full offline suite is green: 470 tests passed with 5 intentional skips (external/live integrations).
- **Interactive autonomy gate**: when `goal loop run` runs without `--json`, high-risk decisions prompt user via stdin with `y/N`. User decline marks node as "blocked".
- **`goal loop status` command**: shows running/completed state, node statuses, latest phase, summary, total actions from handoff entries.
- **Schema coverage**: `goal loop status` registered in JSON schema registry.
- **All 4 goal-loop tests pass**.
- **Everything committed and pushed** to `origin/main`.

## Recent changes
- `scripts/run_model_omniroute.py`: OpenAI-compatible local adapter with free-route fallback.
- `scripts/test_omniroute_free.sh`: local free model smoke test.
- `tests/test_omniroute_adapter.py`: deterministic fallback test plus opt-in live test.
- `README.md`: local OmniRoute free-model setup.
- `tests/test_agent_integration.py`, `tests/test_handoff.py`: external OpenRouter tests skip without key.
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
1. Keep network live tests opt-in via `RUN_OMNIROUTE_LIVE_TEST=1`.
2. Remove tracked legacy virtualenv artifacts in a dedicated cleanup commit.
3. Continue goal-loop extension work.

## Commands
```bash
# test
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_goal_loop_run_executes_all_nodes_and_reports_final_status tests.test_trace_cli.TraceAndCliTests.test_goal_loop_blueprint_surfaces_scope_graph_validation_and_pi_benchmark
# wet-run (mock)
STAGEWARDEN_GOAL_LOOP_EXECUTION_MODE=mock python3 -m stagewarden.main "goal loop run Build a multi-node goal loop" --json
# status
python3 -m stagewarden.main "goal loop status"
```
