# Stagewarden Handoff Summary

## Current State

- The repository is on branch `pr/p4-p5-updates` at `HEAD c303af3`.
- The live OpenRouter benchmark now uses three public suites: `general` (MMLU), `reasoning` (ARC-Challenge), and `truthfulness` (TruthfulQA-MC).
- The benchmark runner emits a `suites` map and an optional `history` block, and the history path is opt-in through `--openrouter-benchmark-history`.
- The local PRINCE2 benchmark now runs through `--prince2-benchmark` and `prince2 benchmark`, with prompt-driven `governance`, `assurance`, and `recovery` suites.
- `stagewarden/prince2_benchmark.py` now exposes the full runtime payload plus a readable detail block for nodes, roles, parent links, inbox/outbox counts, and transitions by default for every benchmark case.
- The CLI and registry tests cover the new benchmark command and JSON schema registration.
- The full unittest suite passes: `381 tests`, `OK`.

## Recent Work

- `stagewarden/openrouter_benchmark.py`: added JSONL history tracking and regression comparison.
- `stagewarden/main.py`: added `--openrouter-benchmark-history`.
- `data/openrouter_benchmark_baseline.json`: added per-suite regression tolerances.
- `stagewarden/prince2_benchmark.py`: added the local PRINCE2 benchmark runner and prompt-driven executor harness.
- `stagewarden/main.py`: added `--prince2-benchmark` and `--prince2-benchmark-output`.
- `data/prince2_benchmark_baseline.json`: added the PRINCE2 prompt baseline suites.
- `stagewarden/prince2_benchmark.py`: expanded the default report with the full runtime payload and rendered node/transition detail for every case.
- `stagewarden/commands.py`: exposed `prince2 benchmark` in the command catalog.
- `stagewarden/json_schema_registry.py`: registered the new `prince2 benchmark` schema.
- `tests/test_prince2.py`: added direct runner coverage for the PRINCE2 benchmark.
- `tests/test_trace_cli.py`: added CLI coverage for `--prince2-benchmark`.
- `tests/test_json_schema_registry.py`: updated the schema registry coverage set.

## Notes

- The benchmark remains a regression gate, not a tolerant scoring harness.
- TruthfulQA-style prompts and PRINCE2 wet-run markers are the most brittle parts of the baselines and should be re-wet-run if changed.
- The PRINCE2 report is intentionally verbose so node roles, transitions, and runtime state are available without a second command, and `--prince2-benchmark` prints that detail by default.
- The shared JSON schema registry now covers both benchmark commands and the other stable JSON surfaces.

## Validation

- `./scripts/test_chatgpt_flow.sh`
- `python3 -m unittest discover -s tests`
- `python3 -m stagewarden.main --prince2-benchmark`
