# Agent Handoff

## Current objective
Keep Stagewarden compatible across Codex CLI, Kilo CLI, and human maintainers while extending PRINCE2 escalation so nodes can spawn child recovery threads and track per-node token accounting.

## Current state
- `AGENTS.md` has been added as the startup and continuity protocol for all agents.
- `AGENT_HANDOFF.md` is now the agent-facing handoff mirror.
- Existing Stagewarden handoff artifacts remain in place and should stay aligned with the agent handoff state.
- The current runtime work now includes PRINCE2 escalation child spawning, per-node thread token accounting, and wet-run battery coverage.
- The help system now exposes an `agent` topic that documents the multi-agent startup/handoff protocol.
- The current compatibility slice remains complete and validated with wet-run tests.

## Recent changes
- `AGENTS.md`: added mandatory startup and handoff protocol.
- `AGENT_HANDOFF.md`: added the compatibility handoff structure.
- `tests/test_trace_cli.py`: battery now covers provider limits, permission denial, PRINCE2 runtime failure modes, and escalation child spawn/token accounting.
- `stagewarden/main.py` and `stagewarden/project_handoff.py`: escalation now materializes recovery child nodes and tracks per-node thread tokens.
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
