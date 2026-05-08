# Agent Handoff

## Current objective
Keep Stagewarden compatible across Codex CLI, Kilo CLI, and human maintainers while preserving the PRINCE2 critic, escalation, token-accounting, and shared JSON-schema work. Keep the OpenRouter live benchmark stable, and keep the local PRINCE2 benchmark stable while exposing rich default runtime data for analysis and statistics.

## Current state
- The live OpenRouter benchmark now uses three public suites: `general` (MMLU), `reasoning` (ARC-Challenge), and `truthfulness` (TruthfulQA-MC).
- `stagewarden/openrouter_benchmark.py` now returns a `suites` map, per-suite regression metadata, and an optional `history` block that compares the current run against the latest JSONL snapshot.
- The benchmark can append a history snapshot when `--openrouter-benchmark-history` is supplied, and it fails the run if the current accuracy regresses relative to the previous snapshot.
- The local PRINCE2 benchmark now runs through `--prince2-benchmark` and `prince2 benchmark`, with three prompt-driven suites: `governance`, `assurance`, and `recovery`.
- `stagewarden/prince2_benchmark.py` now includes rich default runtime snapshots for every case, including the full node roster, role assignments, parent links, inbox/outbox counts, message transitions, wet-run evidence, and PRINCE2 prompt-packet assertions.
- `tests/test_trace_cli.py`, `tests/test_prince2.py`, `tests/test_json_schema_registry.py`, and `stagewarden/commands.py` now cover the PRINCE2 benchmark command and schema registration.
- `python3 -m stagewarden.main --prince2-benchmark` now prints the full default benchmark report with nodes, roles, and transitions for every case.
- `python3 -m unittest discover -s tests` passes: `381 tests`, `OK`.

## Recent changes
- `stagewarden/openrouter_benchmark.py`: added opt-in JSONL history tracking and regression comparison.
- `stagewarden/main.py`: added `--openrouter-benchmark-history` and wired it into the live benchmark command.
- `data/openrouter_benchmark_baseline.json`: added per-suite `regression_tolerance` values alongside the 3-suite public baseline.
- `stagewarden/prince2_benchmark.py`: added a local PRINCE2 benchmark runner with prompt-driven governance and assurance cases.
- `stagewarden/main.py`: added `--prince2-benchmark` and `--prince2-benchmark-output`.
- `data/prince2_benchmark_baseline.json`: added the baseline suites and prompt cases for PRINCE2 benchmark coverage.
- `stagewarden/prince2_benchmark.py`: expanded the default report with node runtime and transition snapshots for every case.
- `stagewarden/commands.py`: exposed `prince2 benchmark` in the command catalog.
- `stagewarden/json_schema_registry.py`: registered the new `prince2 benchmark` schema.
- `tests/test_prince2.py`: added a direct runner assertion for the PRINCE2 benchmark baseline.
- `tests/test_trace_cli.py`: added CLI coverage for `--prince2-benchmark`.
- `tests/test_json_schema_registry.py`: updated registry coverage for the new schema command.

## Important files
- `stagewarden/openrouter_benchmark.py`: live benchmark runner, history writer, and regression comparator.
- `data/openrouter_benchmark_baseline.json`: public prompt baseline used by the benchmark.
- `stagewarden/prince2_benchmark.py`: local PRINCE2 benchmark runner and executor harness.
- `data/prince2_benchmark_baseline.json`: prompt-driven PRINCE2 benchmark baseline.
- `tests/test_trace_cli.py`: CLI, history, and smoke-coverage assertions.
- `tests/test_prince2.py`: PRINCE2 policy and benchmark assertions.
- `tests/test_json_schema_registry.py`: schema command coverage.
- `stagewarden/commands.py`: command catalog exposure for `prince2 benchmark`.
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
- Decision: make the PRINCE2 benchmark prompt-driven and local.
  - Reason: PRINCE2 needs to measure governance, critic gating, wet-run evidence, and prompt-packet context, not just answer quality.
  - Trade-offs: the cases are synthetic, but they exercise the actual executor and critic paths deterministically.
- Decision: include a recovery suite that uses the real agent recovery lane.
  - Reason: PRINCE2 should measure exception handling and recovery closure, not only steady-state execution.
  - Trade-offs: the benchmark is slower, but it covers the flow that matters when a stage goes wrong.
- Decision: include node runtime and transition snapshots by default.
  - Reason: the benchmark should be useful for analysis and statistics without requiring a separate inspection command.
  - Trade-offs: the JSON is larger, but every case now carries the context needed to compare nodes, roles, and transitions over time.
  - Verification: `python3 -m stagewarden.main --prince2-benchmark` now emits the full node/transition detail for every case by default.

## Open issues
- Bugs: none known in the live benchmark slice.
- Risks: TruthfulQA-style prompts and PRINCE2 wet-run markers can still be sensitive to wording, so any future prompt edits should be re-wet-run before landing.
- Unknowns: whether to add more benchmark families or more PRINCE2 prompt suites before the next publish.

## Next steps
1. Decide whether to commit/push this benchmark slice.
2. Add more public benchmark families or more PRINCE2 prompt suites only if they stay stable under wet-run validation.
3. Keep `AGENT_HANDOFF.md`, `HANDOFF.md`, and `.stagewarden_handoff.json` synchronized after the next code change.

## Commands
```bash
./scripts/test_chatgpt_flow.sh
python3 -m unittest discover -s tests
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_openrouter_benchmark_cli_reports_multi_suite_baseline
python3 -m stagewarden.main --prince2-benchmark
python3 -m unittest tests.test_prince2.Prince2Tests.test_prince2_benchmark_reports_prompt_baseline
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_prince2_benchmark_cli_reports_prompt_baseline
```
