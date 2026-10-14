# Agent Handoff

## Current objective
Completa contesto isolato per nodo, token budget provider/modello, compattazione automatica e codemode ristretto; decision model va chiamato genericamente, non come nome di modello. Preservare routing/provider/fallback/policy e serialità v3.

## Current state
- Implementati contesto/revision UUID-scoped per nodo, budget input da catalogo/config con riserva output/margine, compattazione, persistenza knowledge e append/read contestuale.
- Budget finale controlla prompt standard + skills; over-budget fail-closed, context node limitato al residuo. Metadata dichiara `token_counter=utf8_byte_upper_bound_v1` e `accounting_unit=utf8_bytes_upper_bound_not_provider_tokens`; test verifica marker su NodeState e WorkPacket. Goal-loop 74 passed/28 subtests; full suite 761 passed/5 skipped/320 subtests (317.82s).
- Test remoto ora free-only anche nei benchmark OpenRouter espliciti: `STAGEWARDEN_TEST_FREE_MODEL` default `auto/coding:free`; live test saltano se override non termina `:free`, smoke shell fallisce chiuso. OmniRoute free detection accetta suffisso `:free` e due alias fallback esatti (`auto/best-free`, `coding-free-fallback`); respinge `/free/` segmento permissivo e substring incidentali. Adapter: 11 passed/1 skipped/20 subtests; full suite: 765 passed/5 skipped/329 subtests (438.64s).
- Memory loader usa token count solo con contatore esplicito; tokenizer runtime non presente (`transformers`, `tiktoken`, `tokenizers`, `sentencepiece` assenti). Wet mock `run_loop` verifica nodi/eventi/capsule e restart terminale; fix resume precedente ignorava capsule completed/failed, ora ripristina stato terminale e campi bounded (context/revision/messages/output/error). OmniRoute riceve max_tokens clampato a minimo tra cap catalogo, reserve e override, ma è richiesta non garanzia provider; env max tokens OmniRoute e limiti goal-loop input/output/reserve/margin validati come interi positivi; config malformata fallisce chiusa invece di annullare silently tutti i limiti. Opt-in `STAGEWARDEN_GOAL_LOOP_REQUIRE_OUTPUT_CAP=true` fail-closes prima subprocess sia con Pi che OmniRoute: nessuno dei due backend dimostra enforcement. Default off preserva behavior esistente.
- Terminologia decision model: usare nome generico, non nominare JEV come modello.
- Context snapshot knowledge include UUID nel provenance; recovery seleziona snapshot UUID-scoped di revision >= capsule (snapshot wins on tie), evita capsule stale. Test restart e precedence aggiunti.
- Stima token fallback modificata da 3 char/token a UTF-8 byte bound, gestendo correttamente testo Unicode; compattazione ora rispetta cap byte. Non equivale a tokenizer provider reale.
- Strict budget env distingue unset (default) da vuoto/whitespace (errore). OmniRoute max_tokens bound 1..131072 (default 4096), over-range fail-fast JSON/exit 2; adapter tests 10 passed/1 skipped/12 subtests. Full suite 764 passed/5 skipped/321 subtests (317.74s). `STAGEWARDEN_GOAL_LOOP_REQUIRE_OUTPUT_CAP` valida boolean fail-closed. Opt-in input-budget tested: 75 passed/28 subtests; full suite 762 passed/5 skipped/320 subtests (318.85s). `STAGEWARDEN_GOAL_LOOP_REQUIRE_INPUT_BUDGET=true` rifiuta limit unknown, input override esplicito consente progress. Policy input budget valida ora boolean literal; `maybe`/`2`/`enabled` rifiutati.

## Recent changes
- `stagewarden/goal_loop_orchestrator.py`, `stagewarden/node_knowledge.py`: token budget skills, UTF-8 byte estimator/compaction, snapshot UUID provenance e recovery post-restart.
- `tests/test_goal_loop_orchestrator.py`: test estimator Unicode e byte-cap compaction.
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
- Token accounting provider-exact richiede tokenizer/usage backend caller; UTF-8 byte estimator è fallback conservativo, non equivalenza esatta. Il nome metadata dichiara esplicitamente algoritmo, non tokenizer reale.
- Context node UUID-owned; codemode read/append soltanto, niente eval/shell/tool calls.
- Budget da catalogo/env; limiti ignoti non si inventano.

## Open issues
- Stima token e overhead tool/schema/system non verificati su backend.
- Memory token compaction non collegata al caller; compattazione non semantica.
- Verificare prompt custom/skills e preservazione sezioni obbligatorie.
- Testare restore post-restart e wet-run con ambiente pytest funzionante.

## Next steps
1. Eseguire focused/full regression dopo input-budget policy boolean validation.
2. Integrare tokenizer/usage solo con evidence provider; mantenere UTF-8 estimator fallback.
3. Output-cap enforcement richiede evidence backend, non request metadata; test remoti restano free-only.

## Commands
```bash
python -m compileall -q stagewarden tests
python -m pytest --ignore=external_sources -q
python -m json.tool .stagewarden_handoff.json
```
