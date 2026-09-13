# Stagewarden Handoff Summary

## Current State
- Provider model tree/runtime and Hermes/Obsidian memory activity recorded on `main`; current operational plan is `TODO.md`.
- CodeGraph index current: 125 files, 3422 nodes, 10937 edges.
- `models/providers/index.json` plus five provider JSON files generated from legacy catalog; 238 records conserved; provider-tree tests 3/3.
- Local model execution can use `scripts/run_model_omniroute.py` with free routes `auto/coding:free`, `auto/best-free`, and `coding-free-fallback`; prior smoke and opt-in live tests pass.
- `goal loop <task>` produces blueprint with scope, node graph, child prompts, execution order, tolerance matrix, exception policy, validation plan, final report.
- `goal loop run <task>` executes multi-node loop with dependency resolution, parallel execution, autonomy gates, tolerance checks, structured messaging, handoff recording.
- Existing battery wet run passes 29/29; targeted matrix/policy tests pass 9/9 and battery CLI test passes 1/1.
- Full suite passes 487/487 with 5 intentional skips after restoring executable modes 0755.
- Canonical simulation matrix and reusable runner cover all 29 battery simulations and 6 categories; total and granular runs pass.
- Hermes/Obsidian Markdown memory MVP and provider runtime integration are complete; valid provider tree takes precedence and malformed/missing tree falls back to legacy catalog. Local OmniRoute fixed evidence is 3/4; loop #204 found stable `2102`-model inventory across three snapshots (SHA-256 `43b9050701fa0ce7c85ec4c04e797f57f760f525a5734e58e95a989b0e2a684a`), all five expected routes present, and all local gates green. No route behavior change was observed. Prior bounded `auto/best-coding-fast` retry (`max_steps=2`, timeout `120s`) returned `ok=false`, `steps=2`, with one failed model call and same non-terminal action-flow blocker; no new retry. Full suite remains `487/487` with `5` intentional skips.

## Recent Changes
- `TODO.md`: current provider-tree and Hermes/Obsidian memory plan, including loop iterations #190–#204 evidence.
- `data/simulation_matrix.json`: canonical 29-case/6-category matrix.
- `scripts/run_simulation_matrix.py`: list, total, scenario, and category execution with JSON coverage.
- `models/providers/index.json`, `models/providers/*.json`: provider tree.
- `scripts/generate_provider_model_tree.py`: reproducible provider-tree generator.
- `stagewarden/memory_context.py`: configured Markdown memory loader; `memory status` CLI exposes diagnostics.
- `stagewarden/model_catalog.py`: validated provider-tree precedence with legacy fallback.
- `AGENT_HANDOFF.md`: current detailed continuation state.
- `AGENT_POLICY.md`, `AGENT_POLICY.json`, `AGENT_MANIFESTO.md`: governance artifacts reviewed; `AGENT_POLICY.md` links TODO/matrix/runner; no secrets added.

## Loop contract
- Recurring work must follow `TODO.md` one bounded iteration at a time.
- Re-read Hermes memory and CodeGraph before each iteration.
- Stop on green acceptance, repeated blocker, or user cancellation.
- Preserve fail-closed parser and no-secret boundaries.

## Notes
- Set `RUN_MODEL_BIN=$PWD/scripts/run_model_omniroute.py` for local model calls; free routes only by default.
- Use `STAGEWARDEN_GOAL_LOOP_EXECUTION_MODE=mock` for deterministic goal-loop tests.
- Use pi mode for real AI-powered node execution (requires working provider).
- Preserve active `.pi-loop.json.lock` and local `.codegraph/` index; executable tracked files are restored to 0755.
- `.stagewarden_handoff.json` records provider-tree evidence, open memory/config work, and residual risks; `AGENT_HANDOFF.md` and `TODO.md` remain detailed continuation sources.
