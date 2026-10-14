# Agent Handoff

## Current objective
Completa contesto isolato per nodo, token budget provider/modello, compattazione automatica e codemode ristretto; decision model va chiamato genericamente, non come nome di modello. Preservare routing/provider/fallback/policy e serialità v3.

## Current state
- Implementati contesto/revision UUID-scoped per nodo, budget input da catalogo/config con riserva output/margine, compattazione, persistenza knowledge e append/read contestuale.
- Budget finale ora controlla prompt standard più skills assegnate dopo caricamento: fallisce chiuso se supera il limite disponibile; context node viene limitato al residuo. Conteggio resta euristica 3 char/token.
- Memory loader usa token count solo con contatore esplicito; non è integrato tokenizer reale.
- Terminologia decision model: usare nome generico, non nominare JEV come modello.
- Ultima modifica runtime aggiunge persistenza knowledge e evento revision/hash.
- `compileall`, JSON handoff e `git diff --check` passano.
- Ultima validazione dopo budget hardening: suite mirata `tests.test_goal_loop_orchestrator tests.test_memory_context`: 66 passed, 16 subtests. Full suite passata prima dell’hardening: 743 passed, 5 skipped, 301 subtests; da rieseguire.

## Recent changes
- `stagewarden/goal_loop_orchestrator.py`: token budget finale inclusivo delle skills, compaction e persistence context node-scoped.
- `tests/test_goal_loop_orchestrator.py`: regressione skill eccedente budget fail-closed.
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
1. Eseguire suite completa dopo hardening e risolvere regressioni.
2. Integrare tokenizer/cap backend reale oppure fail-closed.
3. Test restore post-restart e wet-run mock.
4. Test restore e wet-run mock; allineare handoff e TODO.

## Commands
```bash
python -m compileall -q stagewarden tests
python -m pytest --ignore=external_sources -q
python -m json.tool .stagewarden_handoff.json
```
