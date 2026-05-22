# AGENTS.md

## Purpose

This repository is maintained by AI coding agents.
All agents must preserve continuity, safety, architectural consistency, and auditability across sessions.

Primary agents:
- Codex CLI
- Kilo CLI
- Human maintainers

## Mandatory startup protocol

At the beginning of every session or resumed session:

1. Read this file: `AGENTS.md`
2. Read the current handoff: `AGENT_HANDOFF.md`
3. Inspect the repository state:
   - current branch
   - `git status`
   - recently modified files
   - relevant tests
4. Restate the active objective before making changes.
5. Identify risks before editing code.

Do not start implementation before understanding the current handoff and repo state.

## Mandatory handoff protocol

Always maintain `AGENT_HANDOFF.md`.

Update it:
- after every meaningful code change
- after every architectural decision
- after discovering a bug or blocker
- before ending a response
- before stopping work
- after running tests or builds

Keep `HANDOFF.md` and `.stagewarden_handoff.json` aligned with the agent handoff state.

The handoff must be concise but sufficient for another agent to continue without prior chat history.

Never delete important context. Compress and reorganize instead.

## Required `AGENT_HANDOFF.md` structure

```md
# Agent Handoff

## Current objective
What we are trying to achieve.

## Current state
What has been completed and what currently works.

## Recent changes
- File/path: summary of change

## Important files
- File/path: why it matters

## Technical decisions
- Decision:
  - Reason:
  - Trade-offs:

## Open issues
- Bugs:
- Risks:
- Unknowns:

## Next steps
1.
2.
3.

## Commands
```bash
# install
# run
# test
# build
```
```

## Validation rule

- Prefer wet-run validation whenever the environment allows it.
- Dry-run only supplements a wet-run; it is not a substitute for it.
- For agent simulations, logs and runtime effects must be checked in real execution paths.
