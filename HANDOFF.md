# Stagewarden Handoff Summary

## Current State

- The repository is on branch `pr/p4-p5-updates` at `HEAD c303af3`.
- The live OpenRouter benchmark now uses three public suites: `general` (MMLU), `reasoning` (ARC-Challenge), and `truthfulness` (TruthfulQA-MC).
- The benchmark runner emits a `suites` map and an optional `history` block, and the history path is opt-in through `--openrouter-benchmark-history`.
- The local PRINCE2 benchmark now runs through `--prince2-benchmark` and `prince2 benchmark`, with prompt-driven `governance`, `assurance`, `recovery`, `advanced`, `stress`, `regulatory`, `regulatory_stress`, `legal_stress`, `incident_response`, `vendor_failure`, `multi_vendor_crisis`, `supply_chain_failure`, `regulatory_war_room`, and `board_crisis` suites.
- `stagewarden/prince2_benchmark.py` now derives benchmark orchestration from the live runtime graph, so the reported node count varies with the actual case execution.
- `stagewarden/prince2_benchmark.py` now exposes the full runtime payload plus a readable detail block for nodes, roles, parent links, inbox/outbox counts, transitions, provider usage, provider-model variants, token totals, and timing by default for every benchmark case.
- `data/prince2_benchmark_baseline.json` now uses more complex PRINCE2 prompts, and the escalation case includes explicit `review/validate` language so the policy checker still allows it while requiring escalation.
- `data/prince2_benchmark_baseline.json` now also includes an `advanced` suite built from public traces covering cloud migration, records governance, data transformation, and procurement delays.
- `data/prince2_benchmark_baseline.json` now also includes a `stress` suite that mixes governance pressure, recovery, and stakeholder conflict.
- `data/prince2_benchmark_baseline.json` now also includes a `regulatory` suite covering secure-by-design, DPIA, AI governance, and wet-run compliance cases.
- `data/prince2_benchmark_baseline.json` now also includes a `regulatory_stress` suite that mixes privacy incidents, audit readiness, AI change control, and compliance wet-run pressure.
- `data/prince2_benchmark_baseline.json` now also includes a `legal_stress` suite that mixes legal hold, contract risk, disclosure pressure, evidence preservation, and board escalation.
- `data/prince2_benchmark_baseline.json` now also includes an `incident_response` suite that mixes breach handling, outage recovery, rollback control, evidence preservation, and operational escalation.
- `data/prince2_benchmark_baseline.json` now also includes a `vendor_failure` suite that mixes supplier collapse, third-party risk, contract renegotiation, fallback planning, and board escalation.
- `data/prince2_benchmark_baseline.json` now also includes a `multi_vendor_crisis` suite that mixes cascading supplier failure, shared dependencies, fallback governance, and urgent board recovery decisions.
- `data/prince2_benchmark_baseline.json` now also includes a `supply_chain_failure` suite that mixes supply shortages, logistics collapse, procurement delays, inventory gaps, and continuity planning.
- `data/prince2_benchmark_baseline.json` now also includes a `regulatory_war_room` suite that mixes live board-room escalation, breach response, vendor risk, legal hold, and continuity control.
- `data/prince2_benchmark_baseline.json` now also includes a `board_crisis` suite that mixes quorum failure, executive escalation, crisis authority, and recovery decisions under pressure.
- `stagewarden/router.py` now biases model selection dynamically for regulatory prompts while leaving the existing deterministic path intact for the rest.
- The CLI and registry tests cover the new benchmark command and JSON schema registration.
- The PRINCE2 benchmark tests pass after the escalation-prompt fix, advanced-suite expansion, stress-suite expansion, regulatory-suite expansion, regulatory_stress-suite expansion, legal_stress-suite expansion, incident_response-suite expansion, vendor_failure-suite expansion, multi_vendor_crisis-suite expansion, supply_chain_failure-suite expansion, regulatory_war_room-suite expansion, and board_crisis-suite expansion; the full unittest suite currently has one flaky live OpenRouter test that retries cleanly outside this slice.

## Recent Work

- `stagewarden/openrouter_benchmark.py`: added JSONL history tracking and regression comparison.
- `stagewarden/main.py`: added `--openrouter-benchmark-history`.
- `data/openrouter_benchmark_baseline.json`: added per-suite regression tolerances.
- `stagewarden/prince2_benchmark.py`: added the local PRINCE2 benchmark runner and prompt-driven executor harness.
- `stagewarden/main.py`: added `--prince2-benchmark` and `--prince2-benchmark-output`.
- `data/prince2_benchmark_baseline.json`: added the PRINCE2 prompt baseline suites, then tightened them to stay evaluative without tripping policy checks.
- `data/prince2_benchmark_baseline.json`: added the `advanced` suite based on public trace material from Welsh Government, Dedalus/NHS, Staffordshire, Surrey, and World Bank sources.
- `data/prince2_benchmark_baseline.json`: added the `stress` suite with combined governance, recovery, and stakeholder-pressure cases.
- `data/prince2_benchmark_baseline.json`: added the `regulatory` suite with secure-by-design, privacy, AI governance, and compliance wet-run cases.
- `stagewarden/router.py`: added a regulatory-aware route recommendation path and catalog-aware variant scoring.
- `stagewarden/prince2_benchmark.py`: expanded the default report with the full runtime payload, dynamic orchestration selection, and rendered node/transition detail for every case.
- `stagewarden/commands.py`: exposed `prince2 benchmark` in the command catalog.
- `stagewarden/json_schema_registry.py`: registered the new `prince2 benchmark` schema.
- `tests/test_prince2.py`: added direct runner coverage for the PRINCE2 benchmark.
- `tests/test_prince2.py`: added a regression check for the complex escalation prompt with validation language.
- `tests/test_trace_cli.py`: added CLI coverage for `--prince2-benchmark`.
- `tests/test_json_schema_registry.py`: updated the schema registry coverage set.

## Notes

- The benchmark remains a regression gate, not a tolerant scoring harness.
- TruthfulQA-style prompts and PRINCE2 wet-run markers are the most brittle parts of the baselines and should be re-wet-run if changed.
- The PRINCE2 report is intentionally verbose so node roles, transitions, runtime state, token consumption, provider/model routing, and timing are available without a second command, and `--prince2-benchmark` prints that detail by default.
- The shared JSON schema registry now covers both benchmark commands and the other stable JSON surfaces.

## Validation

- `./scripts/test_chatgpt_flow.sh`
- `python3 -m unittest discover -s tests`
- `python3 -m stagewarden.main --prince2-benchmark`
