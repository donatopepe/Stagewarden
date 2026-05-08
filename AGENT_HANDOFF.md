# Agent Handoff

## Current objective
Keep Stagewarden compatible across Codex CLI, Kilo CLI, and human maintainers while extending PRINCE2 so every AI response is reviewed by a devil's-advocate critic, nodes can spawn child recovery threads, and per-node token accounting stays visible.
Split node token accounting into input/output buckets, attach model pricing to the business case, and source those prices from Artificial Analysis when refresh credentials are available.
Keep the OpenRouter transport tests using a real API key from the environment and keep the backend runner performing live OpenRouter requests instead of stubs.
Maintain the OpenRouter live benchmark command and smoke script so they exercise a stable public MMLU-style baseline, including a longer instruction-heavy suite for regression checks.
Centralize the versioned JSON schemas used by the machine-readable status/report commands so other agents can validate one shared contract source instead of per-command ad hoc literals.
Extend the same shared schema registry to the remaining stable JSON CLI surfaces, including help, commands, slash, catalog, goal, model usage, git, sessions, role views, project brief/design, system reports, and other register-style outputs.
Treat `--ljson-benchmark` as a stable machine-readable report and give it the same shared schema contract.
Treat `--openrouter-benchmark` as a stable machine-readable report and keep it aligned with the public benchmark baseline file.
Keep the `catalog status`, `catalog search`, and `catalog refresh` JSON payloads aligned with their specific command names so the machine-readable contract stays precise for downstream consumers.
Preserve the exact input command string in the `catalog` JSON fallback path so even unsupported subcommands remain distinguishable in machine-readable output.
Treat the generic `file` fallback as a shared JSON surface too, and preserve the exact input command string there so unsupported file subcommands remain distinguishable.
Treat the generic `update` fallback as a shared JSON surface too, and preserve the exact input command string there so unsupported update subcommands remain distinguishable.
Treat the generic `git` fallback as a shared JSON surface too, and preserve the exact input command string there so unsupported git subcommands remain distinguishable.
Treat the generic `external_io` fallback as a shared JSON surface too, and preserve the exact input command string there so malformed or unsupported external-IO commands remain distinguishable.

## Current state
- `AGENTS.md` has been added as the startup and continuity protocol for all agents.
- `AGENT_HANDOFF.md` is now the agent-facing handoff mirror.
- Existing Stagewarden handoff artifacts remain in place and stay aligned with the agent handoff state.
- The repo is currently on branch `pr/p4-p5-updates` at `HEAD ae8cab7` (`stagewarden: initialize workspace`) with uncommitted edits in the executor, CLI battery stub, tests, and handoff artifacts.
- Date-sensitive test fixtures were corrected so live block windows are only future-dated where the runtime must see them as active, while the historical snapshot tests keep their original 2026 dates.
- The OpenRouter transport tests now perform live API requests through a temporary `RUN_MODEL_BIN` wrapper instead of stubbed no-op output.
- The smoke script now performs live OpenRouter API calls through `RUN_MODEL_BIN` and drives the same benchmark command used by CLI tests.
- The new `openrouter benchmark` CLI command runs the public baseline live, emits a shared JSON schema, and writes an optional snapshot file.
- The devil's-advocate critic now blocks invalid review payloads explicitly with `critic_invalid_output` instead of falling through as if the review were accepted.
- The battery stub and integration stubs now emit valid critic review JSON for review prompts so the wet-run simulations stay aligned with the runtime contract.
- The full `python3 -m unittest discover -s tests` suite now passes after those alignment fixes and the new benchmark command wiring.
- The current runtime work now includes PRINCE2 escalation child spawning, per-node thread token accounting, per-node antagonists, devil's-advocate AI review passes, and wet-run battery coverage.
- The current runtime work now includes PRINCE2 escalation child spawning, per-node thread token accounting split into input/output buckets, per-node pricing sourced from the shared model catalog, per-node antagonists, devil's-advocate AI review passes, and wet-run battery coverage.
- `status --json`, `statusline --json`, `overview --json`, `health --json`, `preflight --json`, `report --json`, `handoff --json`, `boundary --json`, and `board --json` now include versioned `schema` blocks so other agents can validate the payload contracts explicitly.
- Those schema names and versions are now centralized in `stagewarden/json_schema_registry.py`.
- The shared registry now also covers stable JSON surfaces for `help`, `commands`, `slash`, `slash choose`, `catalog`, `catalog status`, `catalog search`, `catalog refresh`, `goal`, `goal set`, `goal status`, `goal clear`, `doctor`, `models`, `model`, `model inspect`, `model limits`, `model limit-record`, `model limit-clear`, `account limit-record`, `account limit-clear`, `project brief`, `project brief set`, `project brief clear`, `project design`, `project tree propose`, `project tree approve`, `roles`, `roles domains`, `roles tree`, `roles tree approve`, `roles baseline`, `roles baseline matrix`, `roles context`, `roles active`, `roles control`, `roles queues`, `roles messages`, `roles runtime`, `roles tick`, `roles check`, `roles flow`, `roles matrix`, `shell backend use`, `web search`, `download`, `checksum`, `compress`, `archive verify`, `models usage`, `accounts`, `permissions`, `git status`, `git log`, `git history`, `git show`, `sessions`, `risks`, `issues`, `quality`, `exception`, `lessons`, `todo`, `transcript`, `resume --show`, `resume context`, and `resume --clear`.
- The shared registry also covers `ljson benchmark` so the benchmark report is machine-readable and cross-agent compatible.
- The `statusline` path inside the interactive mode command handler now also uses the shared schema wrapper, keeping the JSON contract consistent between shell rewrite and top-level dispatch.
- The help system now exposes an `agent` topic that documents the multi-agent startup/handoff protocol.
- The `catalog` JSON helper reports now use the specific command names `catalog status`, `catalog search`, and `catalog refresh` instead of a generic `catalog` label.
- The `catalog` JSON fallback now preserves the exact user-entered command string in the payload instead of collapsing to a generic label.
- The `file` JSON fallback now preserves the exact user-entered command string in the payload and uses a shared `file` schema contract.
- The `update` JSON fallback now preserves the exact user-entered command string in the payload and uses a shared `update` schema contract.
- The `git` JSON fallback now preserves the exact user-entered command string in the payload and uses a shared `git` schema contract.
- The `external_io` JSON fallback now preserves the exact user-entered command string in the payload and uses a shared `external_io` schema contract for malformed or unsupported IO commands.
- The current compatibility slice remains complete and validated with wet-run tests.

## Recent changes
- `AGENTS.md`: added mandatory startup and handoff protocol.
- `AGENT_HANDOFF.md`: added the compatibility handoff structure.
- `stagewarden/executor.py`: invalid devil's-advocate reviews now stop the step with `critic_invalid_output` instead of falling through.
- `stagewarden/main.py`: battery stubs now emit valid critic review JSON when a review prompt is executed.
- `tests/test_handoff.py`: relevant backend-injection tests now perform live OpenRouter API calls through a temporary `RUN_MODEL_BIN` wrapper instead of simulated account tokens, and one of those calls uses a small public MMLU benchmark suite.
- `scripts/test_chatgpt_flow.sh`: replaced the ChatGPT smoke flow with a direct OpenRouter-backed smoke check that performs live OpenRouter requests on a small public MMLU benchmark suite and avoids secret-store simulation.
- `stagewarden/openrouter_benchmark.py`: new live benchmark runner that loads the shared baseline, executes OpenRouter prompts, and renders a machine-readable report.
- `data/openrouter_benchmark_baseline.json`: shared public benchmark baseline with simple and extended MMLU-style suites.
- `stagewarden/main.py`: added `--openrouter-benchmark` and optional output snapshot wiring.
- `tests/test_trace_cli.py`: added live CLI coverage for the new benchmark command.
- `tests/test_json_schema_registry.py`: added the new benchmark schema contract to the registry coverage.
- `scripts/test_chatgpt_flow.sh`: now invokes the benchmark CLI directly and checks the written snapshot.
- `tests/test_trace_cli.py` and `/Users/donato/Stagewarden/run_model_stub`: integration and CLI stubs now distinguish primary model calls from devil's-advocate review prompts.
- `tests/test_executor.py`: added coverage for invalid devil's-advocate output blocking.
- `tests/test_trace_cli.py`: battery now covers provider limits, permission denial, PRINCE2 runtime failure modes, escalation child spawn/token accounting, and antagonist KPI controls.
- `stagewarden/main.py`, `stagewarden/executor.py`, and `stagewarden/project_handoff.py`: escalation now materializes recovery child nodes, tracks per-node thread tokens, runs a devil's-advocate review pass on model responses, and surfaces per-node antagonists.
- `stagewarden/main.py`: `status --json` and `statusline --json` now emit versioned schema blocks for cross-agent compatibility.
- `stagewarden/main.py`: the operational and supporting JSON views now emit versioned schema blocks for cross-agent compatibility.
- `stagewarden/json_schema_registry.py`: shared source of truth for operational JSON schema names and versions.
- `stagewarden/commands.py`: added `/help agent` and a dedicated agent-compatibility help topic.
- `README.md` and `README_IT.md`: documented the multi-agent protocol and the new help entry.
- `stagewarden/main.py`: expanded the shared JSON schema wrapper to the remaining CLI surfaces, including role views, project brief/design, model inspection, catalog refresh, shell backend use, and register reports.
- `stagewarden/main.py`: aligned the `catalog` JSON helper reports with specific command names for status/search/refresh.
- `stagewarden/main.py`: made the `catalog` JSON fallback preserve the exact input command string in JSON.
- `stagewarden/main.py`: made the `file` JSON fallback preserve the exact input command string in JSON and assigned it a shared `file` schema.
- `stagewarden/main.py`: made the `update` JSON fallback preserve the exact input command string in JSON and assigned it a shared `update` schema.
- `stagewarden/main.py`: made the `git` JSON fallback preserve the exact input command string in JSON and assigned it a shared `git` schema.
- `stagewarden/main.py`: made the `external_io` JSON fallback preserve the exact input command string in JSON and assigned it a shared `external_io` schema.
- `stagewarden/model_catalog.py`: added optional Artificial Analysis pricing ingestion so the catalog can refresh input/output token prices from the network when an API key is available.
- `stagewarden/project_handoff.py`: split node business-case token accounting into input/output buckets, attached node pricing/cost fields, and propagated them through runtime, active, and control views.
- `tests/test_model_catalog.py`, `tests/test_persistence.py`, and `tests/test_trace_cli.py`: covered the Artificial Analysis pricing ingestion and the split node token accounting views.

## Important files
- `AGENTS.md`: startup and handoff rules for agents.
- `AGENT_HANDOFF.md`: agent-facing continuity record.
- `HANDOFF.md`: human-readable project handoff summary.
- `.stagewarden_handoff.json`: runtime source of truth for project state.
- `stagewarden/main.py`: CLI dispatch, battery, and interactive shell flows.

## Technical decisions
- Decision: keep `AGENT_HANDOFF.md`, `HANDOFF.md`, and `.stagewarden_handoff.json` aligned.
  - Reason: different agents and tools consume different handoff surfaces.
  - Trade-offs: small duplication, but better continuity and lower resume risk.
- Decision: wet-run remains the default validation standard for simulations.
  - Reason: the agent must prove actual behavior, not just parseable output.
  - Trade-offs: slower validation, but stronger evidence.
- Decision: primary model outputs should pass through a devil's-advocate review before acceptance.
  - Reason: the model can be superficial or assume too much; a second pass catches unsupported claims and missing wet-run evidence.
  - Trade-offs: extra model calls and slightly higher latency, but stronger control over false confidence.

## Open issues
- Bugs: none known from the compatibility protocol itself.
- Risks: the repository has many provider and model surfaces, so static test assertions can drift when provider catalogs expand.
- Unknowns: how far Kilo CLI-specific UX should be mirrored versus adapted for Stagewarden conventions.

## Next steps
1. Keep the handoff files synchronized after the next meaningful code change.
2. Extend wet-run battery coverage to any remaining denied or escalation edge cases.
3. Extend the PRINCE2 runtime controls if more escalation branches need wet-run coverage.
4. Keep the node pricing source in sync with Artificial Analysis when the catalog refresh workflow is re-run.

## Commands
```bash
python3 -m unittest discover -s tests -p 'test_trace_cli.py'
python3 -m unittest tests.test_policy_docs
python3 -m stagewarden.main battery --json
```
