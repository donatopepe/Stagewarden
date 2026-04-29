# Agent Handoff

## Current objective
Keep Stagewarden compatible across Codex CLI, Kilo CLI, and human maintainers while extending PRINCE2 so every AI response is reviewed by a devil's-advocate critic, nodes can spawn child recovery threads, and per-node token accounting stays visible.
Centralize the versioned JSON schemas used by the machine-readable status/report commands so other agents can validate one shared contract source instead of per-command ad hoc literals.
Extend the same shared schema registry to the other stable JSON CLI surfaces, including help, commands, slash, catalog, goal, model usage, git, sessions, and register reports.

## Current state
- `AGENTS.md` has been added as the startup and continuity protocol for all agents.
- `AGENT_HANDOFF.md` is now the agent-facing handoff mirror.
- Existing Stagewarden handoff artifacts remain in place and should stay aligned with the agent handoff state.
- The current runtime work now includes PRINCE2 escalation child spawning, per-node thread token accounting, per-node antagonists, and wet-run battery coverage.
- The current runtime work now includes PRINCE2 escalation child spawning, per-node thread token accounting, per-node antagonists, devil's-advocate AI review passes, and wet-run battery coverage.
- `status --json`, `statusline --json`, `overview --json`, `health --json`, `preflight --json`, `report --json`, `handoff --json`, `boundary --json`, and `board --json` now include versioned `schema` blocks so other agents can validate the payload contracts explicitly.
- Those schema names and versions are now centralized in `stagewarden/json_schema_registry.py`.
- The shared registry now also covers stable JSON surfaces for `help`, `commands`, `slash`, `slash choose`, `catalog status`, `catalog search`, `goal`, `goal set`, `goal status`, `goal clear`, `doctor`, `models`, `model limits`, `models usage`, `accounts`, `permissions`, `git status`, `git log`, `git history`, `git show`, `sessions`, `risks`, `issues`, `quality`, `exception`, `lessons`, `todo`, `transcript`, `resume --show`, and `resume context`.
- The help system now exposes an `agent` topic that documents the multi-agent startup/handoff protocol.
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
