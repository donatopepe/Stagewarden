# Agent Handoff

## Current objective
Implement actual multi-node `goal loop run` orchestration that executes nodes sequentially, respects dependencies, sends structured messages, tracks tolerances, records handoff actions, and compiles pi learning benchmark.

## Current state
- **Goal loop blueprint** (`goal loop <task>`): scope, node graph, child prompts, execution order, tolerance matrix, exception policy, validation plan, final report.
- **Goal loop execution** (`goal loop run <task>`): orchestrator runs 8 nodes with dependency resolution, parallel execution (ThreadPoolExecutor), autonomy gates, tolerance checks, structured messaging, handoff recording.
- **Configurable execution mode**: `mock` (default for tests), `auto` (try pi, fallback to mock), `pi` (fail if pi unavailable).
- **All 4 goal-loop tests pass** (blueprint, execution, persistence, schema).
- **pi learning benchmark** compiled from pi docs: prompt-templates, extensions, skills, SDK, RPC, session control, TUI, packages.

## Recent changes
- `stagewarden/goal_loop_orchestrator.py`: full rewrite with _execute_node, _mock_execution, _pi_execution, _autonomy_gate, _tolerance_gate, ThreadPoolExecutor parallel execution, env-based mode configuration.
- `stagewarden/cli_dispatch.py`: route `goal loop run` with execution_mode.
- `stagewarden/commands.py`: command spec for `goal loop run`.
- `stagewarden/json_schema_registry.py`: schema id for `goal loop run`.
- `tests/test_trace_cli.py`: mock-mode execution test, shutil/re imports, env-aware run_main_capture.
- `.pi/pi-learning-benchmark.md`: 8-dimension benchmark with priority roadmap.

## Important files
- `stagewarden/goal_loop_orchestrator.py`: orchestrator with parallel execution, pi subsession, autonomy/tolerance gates.
- `stagewarden/goal_loop_views.py`: blueprint builder.
- `.pi/prompts/*.md`: prompt templates.
- `.pi/pi-learning-benchmark.md`: pi agent study findings.
- `tests/test_trace_cli.py`: blueprint + execution tests.

## Technical decisions
- Decision: execution mode configurable via env var `STAGEWARDEN_GOAL_LOOP_EXECUTION_MODE`.
  - Reason: allows automated tests to force mock mode without patching subprocess.
- Decision: `_pi_execution` uses `@file` syntax to avoid YAML frontmatter parsing issues.
  - Reason: `---` in prompt templates is interpreted as CLI flags by pi's argument parser.
- Decision: autonomy gate logs classification and proceeds for non-critical decisions.
  - Reason: interactive ask-user would block CLI non-interactive mode.
- Decision: tolerance gate marks node as "blocked" on violation but continues loop.
  - Reason: allows partial completion for diagnostic purposes.

## Open issues
- Real `pi --print` execution requires provider configuration; mock mode is fallback.
- No interactive user prompt for high-risk decisions yet.
- No control socket for external node injection.

## Next steps
1. Add interactive user prompt for high-risk autonomy decisions (when not in JSON mode).
2. Add control socket for external node injection into running goal loops.
3. Add custom node implementations via Stagewarden extensions.
4. Run full pi benchmark against the orchestration surface.

## Commands
```bash
# test
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_goal_loop_run_executes_all_nodes_and_reports_final_status tests.test_trace_cli.TraceAndCliTests.test_goal_loop_blueprint_surfaces_scope_graph_validation_and_pi_benchmark
# wet-run (mock mode)
STAGEWARDEN_GOAL_LOOP_EXECUTION_MODE=mock python3 -m stagewarden.main "goal loop run Build a multi-node goal loop" --json
# wet-run (pi mode, requires provider)
python3 -m stagewarden.main "goal loop run Build a multi-node goal loop" --json
```
