# Stagewarden Handoff Summary

## Current State
- Local model execution can use `scripts/run_model_omniroute.py` with free routes `auto/coding:free`, `auto/best-free`, and `coding-free-fallback`; smoke and opt-in live tests pass.
- External OpenRouter integration tests skip when no external key exists; remaining full-suite failures are unrelated deterministic test issues.
- `goal loop <task>` produces blueprint with scope, node graph, child prompts, execution order, tolerance matrix, exception policy, validation plan, final report.
- `goal loop run <task>` executes multi-node loop with dependency resolution, parallel execution, autonomy gates, tolerance checks, structured messaging, handoff recording.
- Configurable execution mode: mock / auto / pi.
- pi learning benchmark compiled.

## Recent Changes
- `scripts/run_model_omniroute.py`: local OpenAI-compatible adapter with free route fallback.
- `scripts/test_omniroute_free.sh`, `tests/test_omniroute_adapter.py`: smoke, fallback, and opt-in live coverage.
- `stagewarden/goal_loop_orchestrator.py`: _execute_node, _mock_execution, _pi_execution, _autonomy_gate, _tolerance_gate, ThreadPoolExecutor parallel execution, env var config.
- `stagewarden/cli_dispatch.py`: goal loop run routing.
- `stagewarden/commands.py`: goal loop run spec.
- `stagewarden/json_schema_registry.py`: goal loop run schema.
- `tests/test_trace_cli.py`: env-aware run_main_capture, mock-mode execution test.
- `.pi/pi-learning-benchmark.md`: 8-dimension pi agent benchmark.

## Notes
- Set `RUN_MODEL_BIN=$PWD/scripts/run_model_omniroute.py` for local model calls; free routes only by default.
- Use `STAGEWARDEN_GOAL_LOOP_EXECUTION_MODE=mock` for deterministic test execution.
- Use `pi` mode for real AI-powered node execution (requires working provider).
