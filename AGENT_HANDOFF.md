# Agent Handoff

## Current objective
Completa contesto isolato per nodo, token budget provider/modello, compattazione automatica e codemode ristretto; decision model va chiamato genericamente, non come nome di modello. Preservare routing/provider/fallback/policy e serialità v3.

## Current state
- Implementati contesto/revision UUID-scoped per nodo, budget input da catalogo/config con riserva output/margine, compattazione, persistenza knowledge e append/read contestuale.
- Budget finale ora controlla prompt standard più skills assegnate dopo caricamento: fallisce chiuso se supera limite disponibile; context node limitato al residuo. Conteggio euristico 3 char/token.
- Requisito test confermato: ogni test con modello remoto deve usare solo modelli esplicitamente free e fallire chiuso senza candidato free. `scripts/run_model_omniroute.py` filtra ora requested e fallback via marker `:free`, `-free`, `/free`, `free-`; mai invia candidato non marcato.
- Memory loader usa token count solo con contatore esplicito; non è integrato tokenizer reale.
- Terminologia decision model: usare nome generico, non nominare JEV come modello.
- Context snapshot knowledge include UUID nel provenance; recovery seleziona snapshot UUID-scoped di revision >= capsule (snapshot wins on tie), evita capsule stale. Test restart e precedence aggiunti.
- `compileall`, JSON handoff e `git diff --check` passano.
- Test recovery/context mirati aggiornati: eseguiti test restore e precedence; full suite da ripetere dopo ultimo fix tie-break. Ultima full suite prima di fix: 747 passed, 5 skipped, 301 subtests.

## Recent changes
- `stagewarden/goal_loop_orchestrator.py`, `stagewarden/node_knowledge.py`: token budget skills, compaction, snapshot UUID provenance e recovery post-restart.
- `tests/test_goal_loop_orchestrator.py`: regressione resume snapshot context node-scoped.
- `tests/test_goal_loop_orchestrator.py`: regressione skill eccedente budget fail-closed.
- `scripts/run_model_omniroute.py`, `tests/test_omniroute_adapter.py`: filtraggio free-only con fallback e fail-closed testati offline.
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
1. Eseguire test focused e full suite dopo fix recovery tie-break.
2. Integrare tokenizer/cap backend reale oppure fail-closed.
3. Wet-run mock e verificare free-model marker contro catalogo autorevole.

## Commands
```bash
python -m compileall -q stagewarden tests
python -m pytest --ignore=external_sources -q
python -m json.tool .stagewarden_handoff.json
```
