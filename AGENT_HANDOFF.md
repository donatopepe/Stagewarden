# Agent Handoff

## Current objective
Keep Stagewarden compatible across Codex CLI, Kilo CLI, and human maintainers while extending PRINCE2 so every AI response is reviewed by a devil's-advocate critic, nodes can spawn child recovery threads, and per-node token accounting stays visible.
Centralize the versioned JSON schemas used by the machine-readable status/report commands so other agents can validate one shared contract source instead of per-command ad hoc literals.
Extend the same shared schema registry to the remaining stable JSON CLI surfaces, including help, commands, slash, catalog, goal, model usage, git, sessions, role views, project brief/design, system reports, and other register-style outputs.
Treat `--ljson-benchmark` as a stable machine-readable report and give it the same shared schema contract.
Keep the `catalog status`, `catalog search`, and `catalog refresh` JSON payloads aligned with their specific command names so the machine-readable contract stays precise for downstream consumers.
Preserve the exact input command string in the `catalog` JSON fallback path so even unsupported subcommands remain distinguishable in machine-readable output.
Treat the generic `file` fallback as a shared JSON surface too, and preserve the exact input command string there so unsupported file subcommands remain distinguishable.
Treat the generic `update` fallback as a shared JSON surface too, and preserve the exact input command string there so unsupported update subcommands remain distinguishable.
Treat the generic `git` fallback as a shared JSON surface too, and preserve the exact input command string there so unsupported git subcommands remain distinguishable.

## Current state
- `AGENTS.md` has been added as the startup and continuity protocol for all agents.
- `AGENT_HANDOFF.md` is now the agent-facing handoff mirror.
- Existing Stagewarden handoff artifacts remain in place and should stay aligned with the agent handoff state.
- The current runtime work now includes PRINCE2 escalation child spawning, per-node thread token accounting, per-node antagonists, and wet-run battery coverage.
- The current runtime work now includes PRINCE2 escalation child spawning, per-node thread token accounting, per-node antagonists, devil's-advocate AI review passes, and wet-run battery coverage.
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
- The current compatibility slice remains complete and validated with wet-run tests.

## Recent changes
- `AGENTS.md`: added mandatory startup and handoff protocol.
- `AGENT_HANDOFF.md`: added the compatibility handoff structure.
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

## Commands
```bash
python3 -m unittest discover -s tests -p 'test_trace_cli.py'
python3 -m unittest tests.test_policy_docs
python3 -m stagewarden.main battery --json
```
