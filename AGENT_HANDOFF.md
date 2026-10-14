# Agent Handoff

## Current objective
Completa contesto isolato per nodo, token budget provider/modello, compattazione automatica e codemode ristretto; decision model va chiamato genericamente, non come nome di modello. Preservare routing/provider/fallback/policy e serialità v3.

## Current state
- Implementati contesto/revision UUID-scoped per nodo, budget input da catalogo/config con riserva output/margine, compattazione, persistenza knowledge e append/read contestuale.
- Memory loader usa token count solo con contatore esplicito; non è integrato tokenizer reale.
- Terminologia decision model: usare nome generico, non nominare JEV come modello.
- Ultima modifica runtime aggiunge persistenza knowledge e evento revision/hash.
- `compileall`, JSON handoff e `git diff --check` passano.
- Test non eseguiti: interpreter `/tmp/stagewarden-test-venv` non esiste più; pytest non installato nel Python attivo. `venv_pytest` ha link interpreter Mac non valido qui. Prima delle ultime modifiche: suite mirati 94 passed/26 subtests; suite complessiva 743 passed, 5 skipped, 301 subtests.

## Recent changes
- `stagewarden/goal_loop_orchestrator.py`: token budget, compaction e persistence context node-scoped.
- `stagewarden/memory_context.py`: loader bounded con token counter esplicito.
- `tests/test_goal_loop_orchestrator.py`, `tests/test_memory_context.py`: isolamento, overflow e codemode.
- `TODO.md`, `HANDOFF.md`, `.stagewarden_handoff.json`: contesto e roadmap.

## Important files
- `stagewarden/goal_loop_orchestrator.py`: node prompts/budget/compaction/codemode.
- `stagewarden/memory_context.py`: loader Markdown.
- `stagewarden/model_catalog.py`: limiti provider/modello.
- `stagewarden/node_knowledge.py`: store persistente per nodo.

## Technical decisions
- Token accounting esatto richiede tokenizer caller; stima goal-loop resta 3 chars/token, non garanzia.
- Context node UUID-owned; codemode read/append soltanto, niente eval/shell/tool calls.
- Budget da catalogo/env; limiti ignoti non si inventano.

## Open issues
- Stima token e overhead tool/schema/system non verificati su backend.
- Memory token compaction non collegata al caller; compattazione non semantica.
- Verificare prompt custom/skills e preservazione sezioni obbligatorie.
- Testare restore post-restart e wet-run con ambiente pytest funzionante.

## Next steps
1. Procurare Python/pytest valido e rieseguire suite mirati e completa.
2. Hardening prompt budgeting con sezioni obbligatorie e test overflow.
3. Integrare tokenizer/cap backend reale oppure fail-closed.
4. Test restore e wet-run mock; allineare handoff e TODO.

## Commands
```bash
python -m compileall -q stagewarden tests
python -m pytest --ignore=external_sources -q
python -m json.tool .stagewarden_handoff.json
```
