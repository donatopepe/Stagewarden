# Agent Handoff

## Current objective
Keep Stagewarden compatible across Codex CLI, Kilo CLI, and human maintainers while preserving the PRINCE2 critic, escalation, token-accounting, and shared JSON-schema work. Keep the OpenRouter live benchmark stable, and keep the local PRINCE2 benchmark stable while exposing rich default runtime data for analysis, statistics, and prompt-driven orchestration.

## Current state
- The live OpenRouter benchmark now uses three public suites: `general` (MMLU), `reasoning` (ARC-Challenge), and `truthfulness` (TruthfulQA-MC).
- `stagewarden/openrouter_benchmark.py` now returns a `suites` map, per-suite regression metadata, and an optional `history` block that compares the current run against the latest JSONL snapshot.
- The benchmark can append a history snapshot when `--openrouter-benchmark-history` is supplied, and it fails the run if the current accuracy regresses relative to the previous snapshot.
- The local PRINCE2 benchmark now runs through `--prince2-benchmark` and `prince2 benchmark`, with three prompt-driven suites: `governance`, `assurance`, and `recovery`.
- `stagewarden/prince2_benchmark.py` now derives orchestration from the live runtime graph, so the reported node count depends on the actual case execution rather than a hardcoded node list.
- `stagewarden/prince2_benchmark.py` now includes the full runtime payload for every case plus a rendered `detail` block that spells out nodes, roles, parent links, inbox/outbox counts, transitions, provider usage, provider-model variants, token totals, and timing in plain text.
- `data/prince2_benchmark_baseline.json` now uses more complex PRINCE2 prompts, and the escalation case explicitly includes `validate/review` language so the policy checker still marks it allowed while requiring escalation.
- `data/prince2_benchmark_baseline.json` now also includes an `advanced` suite built from public cloud-migration, records-governance, data-transformation, and procurement-delay traces.
- `data/prince2_benchmark_baseline.json` now also includes a `stress` suite with combined governance, recovery, and stakeholder-pressure cases.
- `data/prince2_benchmark_baseline.json` now also includes a `regulatory` suite with secure-by-design, DPIA, AI governance, and wet-run compliance cases.
- `data/prince2_benchmark_baseline.json` now also includes a `regulatory_stress` suite that mixes privacy incidents, audit readiness, AI change control, and compliance wet-run pressure.
- `data/prince2_benchmark_baseline.json` now also includes a `legal_stress` suite that mixes legal hold, contract risk, disclosure pressure, evidence preservation, and board escalation.
- `data/prince2_benchmark_baseline.json` now also includes an `incident_response` suite that mixes breach handling, outage recovery, rollback control, evidence preservation, and operational escalation.
- `data/prince2_benchmark_baseline.json` now also includes a `vendor_failure` suite that mixes supplier collapse, third-party risk, contract renegotiation, fallback planning, and board escalation.
- `data/prince2_benchmark_baseline.json` now also includes a `multi_vendor_crisis` suite that mixes cascading supplier failure, shared dependencies, fallback governance, and urgent board recovery decisions.
- `data/prince2_benchmark_baseline.json` now also includes a `supply_chain_failure` suite that mixes supply shortages, logistics collapse, procurement delays, inventory gaps, and continuity planning.
- `data/prince2_benchmark_baseline.json` now also includes a `regulatory_war_room` suite that mixes live board-room escalation, breach response, vendor risk, legal hold, and continuity control.
- `data/prince2_benchmark_baseline.json` now also includes a `board_crisis` suite that mixes quorum failure, executive escalation, crisis authority, and recovery decisions under pressure.
- `stagewarden/router.py` now scores routes dynamically with regulatory-aware profile detection and catalog-aware variant selection while preserving deterministic behavior for non-regulatory prompts.
- `tests/test_trace_cli.py`, `tests/test_prince2.py`, `tests/test_json_schema_registry.py`, and `stagewarden/commands.py` now cover the PRINCE2 benchmark command and schema registration.
- `python3 -m stagewarden.main --prince2-benchmark` now prints the full default benchmark report with structured runtime data and readable per-case node/transition detail.
- The PRINCE2 benchmark tests pass after the escalation-prompt fix, advanced-suite expansion, stress-suite expansion, regulatory-suite expansion, and regulatory_stress-suite expansion; the full unittest suite still has one flaky live OpenRouter test unrelated to this slice.

## Recent changes
- `stagewarden/openrouter_benchmark.py`: added opt-in JSONL history tracking and regression comparison.
- `stagewarden/main.py`: added `--openrouter-benchmark-history` and wired it into the live benchmark command.
- `data/openrouter_benchmark_baseline.json`: added per-suite `regression_tolerance` values alongside the 3-suite public baseline.
- `stagewarden/prince2_benchmark.py`: added a local PRINCE2 benchmark runner with prompt-driven governance and assurance cases.
- `stagewarden/main.py`: added `--prince2-benchmark` and `--prince2-benchmark-output`.
- `data/prince2_benchmark_baseline.json`: added the baseline suites and prompt cases for PRINCE2 benchmark coverage.
- `stagewarden/prince2_benchmark.py`: expanded the default report with the full runtime payload, dynamic orchestration selection, and rendered node/transition detail for every case.
- `data/prince2_benchmark_baseline.json`: rewrote the PRINCE2 prompts to be more complex and evaluative while preserving checker compatibility.
- `data/prince2_benchmark_baseline.json`: added the `advanced` suite based on public traces from Welsh Government, Dedalus/NHS, Staffordshire, Surrey, and World Bank case material.
- `data/prince2_benchmark_baseline.json`: added the `stress` suite with combined governance, recovery, and stakeholder-pressure cases.
- `data/prince2_benchmark_baseline.json`: added the `regulatory` suite with secure-by-design, privacy, AI governance, and compliance wet-run cases.
- `data/prince2_benchmark_baseline.json`: added the `regulatory_stress` suite with privacy, audit, AI governance, and wet-run pressure cases.
- `data/prince2_benchmark_baseline.json`: added the `legal_stress` suite with legal hold, contract risk, disclosure, and evidence-preservation cases.
- `data/prince2_benchmark_baseline.json`: added the `incident_response` suite with breach, outage, rollback, and incident-response cases.
- `data/prince2_benchmark_baseline.json`: added the `vendor_failure` suite with supplier collapse, third-party risk, and contingency cases.
- `data/prince2_benchmark_baseline.json`: added the `multi_vendor_crisis` suite with cascading supplier failure and shared-dependency cases.
- `data/prince2_benchmark_baseline.json`: added the `supply_chain_failure` suite with logistics, inventory, and continuity cases.
- `data/prince2_benchmark_baseline.json`: added the `regulatory_war_room` suite with live escalation, breach, vendor, and continuity cases.
- `data/prince2_benchmark_baseline.json`: added the `board_crisis` suite with quorum failure, executive recovery, and board-authority cases.
- `stagewarden/router.py`: added a regulatory-aware route recommendation path and catalog-aware variant scoring.
- `stagewarden/commands.py`: exposed `prince2 benchmark` in the command catalog.
- `stagewarden/json_schema_registry.py`: registered the new `prince2 benchmark` schema.
- `tests/test_prince2.py`: added a direct runner assertion for the PRINCE2 benchmark baseline.
- `tests/test_prince2.py`: added a regression test for the complex escalation prompt with validation language.
- `tests/test_router.py`: added a regulatory routing regression check.
- `tests/test_trace_cli.py`: added CLI coverage for `--prince2-benchmark` and the detail block.
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
  - Verification: `python3 -m stagewarden.main --prince2-benchmark` now emits the full runtime payload and readable node/transition detail for every case by default.
- Decision: derive benchmark orchestration from the live runtime graph rather than a fixed node list.
  - Reason: the node count should follow actual case execution and prompt-driven state changes.
  - Trade-offs: counts can differ across cases, but the report now reflects real orchestration instead of a static slice.
- Decision: keep the PRINCE2 escalation case complex but explicitly validated.
  - Reason: the benchmark should remain realistic and evaluative without tripping the policy gate on missing validation language.
  - Trade-offs: the prompt is slightly more verbose, but it stays complex while still exercising allowed+escalate behavior.
- Decision: add an `advanced` benchmark suite sourced from public project traces.
  - Reason: the baseline needed harder, more realistic cases with conflict, recovery, and governance pressure.
  - Trade-offs: more verbose prompts and more cases to maintain, but better coverage for real PRINCE2 stress conditions.
- Decision: add a `stress` suite that mixes multiple trace themes in one benchmark family.
  - Reason: a second layer of harder cases helps catch regressions in combined governance, recovery, and stakeholder pressure scenarios.
  - Trade-offs: the baseline grows again, but the benchmark becomes more representative of real project turbulence.
- Decision: add a `regulatory` suite and make the router compliance-aware.
  - Reason: regulatory work is where model selection should bias toward deeper reasoning, auditability, and better evidence handling.
  - Trade-offs: the router is a little more complex, but it stays deterministic for non-regulatory prompts and becomes more useful where it matters.
- Decision: add a `regulatory_stress` suite to combine compliance, privacy, audit, and wet-run pressure in a single benchmark family.
  - Reason: the benchmark needed at least one harder family that forces the router and executor to deal with overlapping governance constraints.
  - Trade-offs: the baseline grows again, but the resulting cases are closer to the real conflicts the project is meant to handle.
- Decision: add a `legal_stress` suite to force legal-hold, contract, and disclosure pressure through the same PRINCE2 controls.
  - Reason: legal and contractual conflict is another real-world stress axis that should influence routing and recovery behavior.
  - Trade-offs: the benchmark grows again, but the model-selection path now sees another high-pressure governance signal.
- Decision: add an `incident_response` suite to force breach, outage, and rollback pressure through the same PRINCE2 controls.
  - Reason: incident handling is another high-pressure path where the router should prefer more capable providers and the benchmark should verify recovery behavior.
  - Trade-offs: the benchmark grows again, but it now reflects operational incidents in addition to compliance and legal stress.
- Decision: add a `vendor_failure` suite to force supplier collapse and third-party risk through the same PRINCE2 controls.
  - Reason: vendor failure is a realistic delivery shock that should influence routing, recovery planning, and board escalation.
  - Trade-offs: the benchmark grows again, but it now covers contingency behavior under supplier pressure.
- Decision: add a `multi_vendor_crisis` suite to force cascading supplier failure and dependency collapse through the same PRINCE2 controls.
  - Reason: multi-supplier failures are a harsher version of vendor risk and should stress the router and recovery paths further.
  - Trade-offs: the benchmark grows again, but it now covers coordinated fallback behavior across multiple dependencies.
- Decision: add a `supply_chain_failure` suite to force logistics, inventory, and procurement pressure through the same PRINCE2 controls.
  - Reason: supply-chain shocks are another realistic continuity hazard that should influence routing and recovery planning.
  - Trade-offs: the benchmark grows again, but it now covers procurement and logistics continuity under pressure.
- Decision: add a `regulatory_war_room` suite to combine breach, vendor outage, legal hold, and regulatory escalation in one benchmark family.
  - Reason: the hardest real-world failures are the ones where multiple governance paths collide at once.
  - Trade-offs: the benchmark grows again, but it now stresses the router and executor with a true crisis-room blend.
- Decision: add a `board_crisis` suite to combine quorum failure, executive escalation, and board-authority pressure in one benchmark family.
  - Reason: board deadlock is a distinct failure mode that should drive routing and recovery behavior.
  - Trade-offs: the benchmark grows again, but it now covers governance failure at the top of the decision chain.

## Open issues
- Bugs: none known in the local PRINCE2 benchmark slice after the prompt fix and advanced/stress/regulatory/regulatory_stress/legal_stress/incident_response/vendor_failure/multi_vendor_crisis/supply_chain_failure/regulatory_war_room/board_crisis-suite expansion.
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
python3 -m unittest tests.test_prince2.Prince2Tests.test_policy_allows_complex_escalation_prompt_with_validation_language
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_prince2_benchmark_cli_reports_prompt_baseline
```
