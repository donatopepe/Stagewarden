# Agent Handoff

## Current objective
Keep Stagewarden compatible across Codex CLI, Kilo CLI, and human maintainers while preserving the PRINCE2 critic, escalation, token-accounting, and shared JSON-schema work. Keep the OpenRouter live benchmark stable and comparable against public benchmarks.

## Current state
- The live OpenRouter benchmark now uses three public suites: `general` (MMLU), `reasoning` (ARC-Challenge), and `truthfulness` (TruthfulQA-MC).
- `stagewarden/openrouter_benchmark.py` now returns a `suites` map and per-suite report blocks, and the JSON snapshot remains machine readable.
- `tests/test_trace_cli.py` and `scripts/test_chatgpt_flow.sh` run the benchmark through a fixed real OpenRouter model for stability, not `openrouter/auto`.
- `tests/test_handoff.py` also uses the same fixed real OpenRouter model for transport coverage.
- `python3 -m unittest discover -s tests` passes: `378 tests`, `OK`.

## Recent changes
- `stagewarden/openrouter_benchmark.py`: generalized benchmark reporting to `suites`.
- `data/openrouter_benchmark_baseline.json`: expanded the baseline from two MMLU suites to `general`, `reasoning`, and `truthfulness`.
- `tests/test_trace_cli.py`: updated the CLI benchmark assertions to the 3-suite baseline.
- `scripts/test_chatgpt_flow.sh`: updated the smoke path to validate the 3-suite benchmark snapshot.
- `tests/test_handoff.py`: switched the live transport stub to a fixed OpenRouter model.

## Important files
- `stagewarden/openrouter_benchmark.py`: live benchmark runner and report shape.
- `data/openrouter_benchmark_baseline.json`: public prompt baseline used by the benchmark.
- `tests/test_trace_cli.py`: CLI and smoke-coverage assertions.
- `scripts/test_chatgpt_flow.sh`: live smoke entrypoint.
- `stagewarden/json_schema_registry.py`: schema contract registry for machine-readable outputs.

## Technical decisions
- Decision: use a fixed OpenRouter model in the live test wrappers.
  - Reason: `openrouter/auto` had already shown flaky routing behavior on some prompts.
  - Trade-offs: less routing variance in tests, but still real OpenRouter traffic.
- Decision: keep the benchmark output keyed by suite id.
  - Reason: it makes comparisons across benchmark families explicit.
  - Trade-offs: slightly larger report, but clearer downstream parsing.
- Decision: keep threshold accuracy at `1.0` for the live baseline.
  - Reason: the suite is meant to catch regressions, not tolerate partial correctness.
  - Trade-offs: brittle prompts will fail fast instead of being masked.

## Open issues
- Bugs: none known in the live benchmark slice.
- Risks: TruthfulQA-style prompts can be sensitive to wording, so any future prompt edits should be re-wet-run before landing.
- Unknowns: whether to add more benchmark families before the next publish.

## Next steps
1. Decide whether to commit/push this benchmark expansion.
2. Add more public benchmark families only if they stay stable under wet-run validation.
3. Keep `AGENT_HANDOFF.md`, `HANDOFF.md`, and `.stagewarden_handoff.json` synchronized after the next code change.

## Commands
```bash
./scripts/test_chatgpt_flow.sh
python3 -m unittest discover -s tests
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_openrouter_benchmark_cli_reports_multi_suite_baseline
```
