# Agent Handoff

## Current objective
Keep Stagewarden compatible across Codex CLI, Kilo CLI, and human maintainers while preserving the PRINCE2 critic, escalation, token-accounting, and shared JSON-schema work. Keep the OpenRouter live benchmark stable, comparable, and able to fail on real regressions over time.

## Current state
- The live OpenRouter benchmark now uses three public suites: `general` (MMLU), `reasoning` (ARC-Challenge), and `truthfulness` (TruthfulQA-MC).
- `stagewarden/openrouter_benchmark.py` now returns a `suites` map, per-suite regression metadata, and an optional `history` block that compares the current run against the latest JSONL snapshot.
- The benchmark can append a history snapshot when `--openrouter-benchmark-history` is supplied, and it fails the run if the current accuracy regresses relative to the previous snapshot.
- `tests/test_trace_cli.py` and `scripts/test_chatgpt_flow.sh` now validate the 3-suite benchmark plus the opt-in history path using a fixed real OpenRouter model for stability.
- `tests/test_handoff.py` also uses the same fixed real OpenRouter model for transport coverage.
- `python3 -m unittest discover -s tests` passes: `379 tests`, `OK`.

## Recent changes
- `stagewarden/openrouter_benchmark.py`: added opt-in JSONL history tracking and regression comparison.
- `stagewarden/main.py`: added `--openrouter-benchmark-history` and wired it into the live benchmark command.
- `data/openrouter_benchmark_baseline.json`: added per-suite `regression_tolerance` values alongside the 3-suite public baseline.
- `tests/test_trace_cli.py`: updated benchmark assertions for the new history block and regression helper.
- `scripts/test_chatgpt_flow.sh`: now checks the written history snapshot in addition to the benchmark output file.
- `tests/test_handoff.py`: still uses the fixed OpenRouter model for live transport coverage.

## Important files
- `stagewarden/openrouter_benchmark.py`: live benchmark runner, history writer, and regression comparator.
- `data/openrouter_benchmark_baseline.json`: public prompt baseline used by the benchmark.
- `tests/test_trace_cli.py`: CLI, history, and smoke-coverage assertions.
- `scripts/test_chatgpt_flow.sh`: live smoke entrypoint.
- `stagewarden/json_schema_registry.py`: schema contract registry for machine-readable outputs.

## Technical decisions
- Decision: use a fixed OpenRouter model in the live test wrappers.
  - Reason: `openrouter/auto` had shown flaky routing behavior on some prompts.
  - Trade-offs: less routing variance in tests, but still real OpenRouter traffic.
- Decision: keep the benchmark output keyed by suite id.
  - Reason: it makes comparisons across benchmark families explicit.
  - Trade-offs: slightly larger report, but clearer downstream parsing.
- Decision: make history tracking opt-in via `--openrouter-benchmark-history`.
  - Reason: the benchmark should stay side-effect free unless the caller explicitly wants durable snapshots.
  - Trade-offs: one extra CLI flag, but no accidental runtime files.
- Decision: fail the benchmark when the current snapshot regresses against the previous snapshot.
  - Reason: the benchmark is meant to detect real quality drift, not just threshold failures.
  - Trade-offs: stricter gating, but much better baseline control over time.

## Open issues
- Bugs: none known in the live benchmark slice.
- Risks: TruthfulQA-style prompts can still be sensitive to wording, so any future prompt edits should be re-wet-run before landing.
- Unknowns: whether to add more benchmark families before the next publish.

## Next steps
1. Decide whether to commit/push this benchmark history slice.
2. Add more public benchmark families only if they stay stable under wet-run validation.
3. Keep `AGENT_HANDOFF.md`, `HANDOFF.md`, and `.stagewarden_handoff.json` synchronized after the next code change.

## Commands
```bash
./scripts/test_chatgpt_flow.sh
python3 -m unittest discover -s tests
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_openrouter_benchmark_cli_reports_multi_suite_baseline
```
