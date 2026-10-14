# Agent Handoff

## Current objective
Riprendere e completare contesto isolato per ogni nodo, token budgeting per modello, auto-compattazione e codemode limitato; conservare serialità/policy/routing v3. Nessuna implementazione codice ancora in questa ripresa.

## Current state
- Supporto skill nodali preesistente: workspace `.stagewarden/skills`, assegnazione per node ID, solo Markdown bounded/non eseguibile.
- Sorgenti shallow in `external_sources/` aggiornate/scaricate: Pi `2688aba7dc177020ef5da5492a966ed28ad619bd`, Claude Code `9b4f0d6ef8ceaf62f6b46babb9a4d84bec541a2e`, Codex `7eed30ad1beaebc20b7d848ce9ee887525a379b0`. Directory ignored da Git; provenienza e refs in TODO. Non ancora analizzate comparativamente.
- Baseline `tests/test_memory_context.py tests/test_goal_loop_orchestrator.py`: 63 passed, 16 subtests; `compileall` + diff check puliti. pytest installato in `/tmp/stagewarden-test-venv`; suite completa non eseguita.
- Contesto configurato già ha `max_chars`, ma non è token-aware né specifico per profilo modello; auto-compattazione e codemode di contesto nodale non dimostrati/implementati.

## Recent changes
- `TODO.md`: obiettivo, refs upstream, rischi, criteri e piano incrementale aggiornati.
- Nessun codice applicativo modificato.

## Important files
- `stagewarden/goal_loop_views.py`: skill discovery and persistence.
- `stagewarden/goal_loop_orchestrator.py`: per-node prompt assembly.
- `.stagewarden/goal_loop_skills.json`: workspace assignments (created by CLI).
- `.stagewarden/skills/`: Markdown skill root.

## Technical decisions
- Skill content is prompt data only, never executed. Workspace-bounded discovery prevents arbitrary external-path loading for named skills.
- Assignments keyed to node ID, avoiding shared/global prompt contamination. Node UUID isolation remains existing behavior.
- Legacy custom `skill_path` supported for compatibility; named skills use bounded registry.

## Open issues
- Assignment references must be maintained when node IDs change; no migration/update helper yet.
- Skill content is untrusted prompt data; model prompt injection remains a residual risk, mitigated only by labeling/limits and policy boundaries.

## Next steps
1. Test CLI commands end-to-end from a temporary workspace and inspect assignment JSON.
2. Consider report command to show assignments/hashes by node.
3. Avoid wiring skills into tools/capabilities without explicit design authorization.

## Commands
```bash
python -m compileall -q stagewarden tests
/tmp/stagewarden-venv/bin/python -m pytest -q
codegraph status .
```
