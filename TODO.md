# Stagewarden — TODO unico

**Stato:** MVP runtime node-first autorizzato per test con OmniRoute free; implementazione v3 completa ancora incrementale
**Owner decisioni prodotto:** utente
**Branch/worktree:** `main`, unico worktree
**Regola:** ogni attività pianificata deve stare in questo file. Nessun backlog parallelo in README, ROADMAP, handoff o documenti di ricerca.

## Obiettivo attivo

Implementare e validare MVP node-first su OmniRoute free: scheduler seriale bottom-up, WorkPacket/ResultPacket, banner terminale con purpose, Node Knowledge Store SQLite con storia/retrieval e code-aware Python index. Poi estendere gradualmente verso v3 completa.

### Prossima iterazione bounded — unified scenario/full wet runner

- **Obiettivo:** eseguire canonical simulation matrix, targeted MVP suites, full unittest discovery, CLI smoke e documentation/link checks through one reusable bounded runner; non modificare runtime policy.
- **Metrica/soglia:** 100% runner gates verdi: matrix total, targeted node/context/event/mutation suites, full discovery, CLI/status smoke and docs hygiene; soglia 6/6 gate groups.
- **Baseline:** `/tmp/full-matrix-baseline.log`: no unified runner in `tests/data`; canonical matrix exists under `data/simulation_matrix.json` and `scripts/run_simulation_matrix.py`, but full combined gate not run in current iteration.
- **Casi fissi/ordine:** simulation matrix total; targeted MVP suites; full unittest discovery; CLI `baseline --json`, `model limits --json`, `events replay --json`; UTF-8/BOM, links and diff checks.
- **Gate completato precedente:** Node Knowledge Store/index matrix 6/6; tree/packet 6/6; context 6/6; mutation 16/16.
- **Priorità corrente:** estendere Node Knowledge code index con moduli, relazioni import/call/read/write e freshness/versioning; non cambiare runtime policy.

### Sotto-iterazione bounded corrente — relazioni/freshness code index

- **Obiettivo:** estendere esclusivamente `NodeKnowledgeStore.index_python()` oltre classi/funzioni, persistendo module/import/call/read/write relations con file hash/version freshness e node scope.
- **Metrica/soglia:** 100% dei 6 casi fissi verdi: module/import symbols; call relation; import relation; source read/write relation; unchanged reindex freshness; changed-file version replacement; soglia 6/6.
- **Baseline:** `/tmp/code-index-relations-baseline.log`: suite Node Knowledge `5/5 OK`, ma schema ha solo `code_symbols` senza relations/version table; probe indexa `1` function e `0` import/call/read/write relations.
- **Casi fissi/ordine:** module/import extraction; local call edge; import edge; source read/write metadata; unchanged reindex reports fresh/no duplicate; changed content updates version/hash and removes stale symbols.
- **Variabile unica:** Python AST index schema/relation extraction; no scheduler, provider/model, fallback, OmniRoute parser or parallelism change.
- **Test wet target:** nuova matrice `6/6` in `tests/test_node_knowledge.py`, poi unified targeted runner.
- **Esito:** relation/freshness matrix `6/6`; targeted MVP `104/104`; unified runner `6/6`; direct OmniRoute smoke green; CodeGraph `139/3723/12503`.

### Sotto-iterazione bounded corrente — serial gate fail-closed

- **Obiettivo:** verificare che goal-loop execution mode resti seriale anche quando riceve valore non supportato, senza introdurre parallelismo legacy o collision-prone behavior.
- **Metrica/soglia:** casi fissi `3/3` verdi: default mode is `auto` but one ready node; explicit `mock` remains serial; unsupported `parallel`/`bogus` values fail closed or are normalized to serial-safe mode. Soglia 3/3.
- **Baseline:** `/tmp/serial-mode-baseline.log`: constructor accepts `parallel` and `bogus` unchanged; `_execute_node` comment says serial but no mode validation exists.
- **Casi fissi/ordine:** default constructor; explicit mock run; unsupported mode rejection/normalization. No provider/model or scheduler policy change beyond fail-closed validation.
- **Variabile unica:** execution-mode validation at orchestrator boundary; no legacy parallel implementation.
- **Test wet target:** nuova matrice in `tests/test_goal_loop_orchestrator.py`, then unified runner.
- **Esito:** serial gate `3/3`; targeted MVP `105/105`; unified runner `6/6`; OmniRoute direct smoke green; CodeGraph `139/3724/12516`. Unsupported `parallel`/`bogus` modes now fail closed; no legacy parallel implementation added.

### Sotto-iterazione bounded corrente — context budget provider/node evidence

- **Obiettivo:** rendere esplicita e verificabile la relazione provider/model → context budget → node file-chunk/compaction events, senza cambiare provider/model selection o fallback.
- **Metrica/soglia:** 100% dei 3 casi fissi verdi: budget identity fields; chunk event identity/budget fields; compaction event identity/budget fields. Soglia 3/3.
- **Baseline:** `/tmp/context-provider-baseline.log`: context/file suite `9/9 OK`, ma existing events omit explicit `provider`, `model`, `context_window`, `input_limit`, `reserved_output`, `safety_margin`, `node_id` identity in compaction details.
- **Casi fissi/ordine:** `_context_budget("cheap")`; `read_file_chunk` on node; `_build_prompt` compaction on node/provider budget.
- **Variabile unica:** event metadata propagation from active context budget; no provider/model choice, fallback, scheduler or parallelism change.
- **Test wet target:** nuova matrice `3/3` in `tests/test_context_file_reading.py`, then unified runner.
- **Esito:** context/provider identity matrix `3/3`; context/file + executor-event `10/10`; targeted MVP `106/106`; unified runner `6/6`; OmniRoute direct smoke green; CodeGraph `139/3726/12529`.

### Sotto-iterazione bounded corrente — context metadata redaction/replay safety

- **Obiettivo:** verificare che nuovo provider/model/context metadata resti redacted-safe in JSONL and deterministic replay, without leaking credentials or changing event semantics.
- **Metrica/soglia:** `3/3` fixed safety cases green: metadata survives replay; secret-like values redacted; node filter excludes other node events. Threshold 3/3.
- **Baseline:** `/tmp/context-provider-baseline.log`: metadata identity tests pass, but no fixed redaction/replay matrix covers provider/model fields after propagation.
- **Casi fissi/ordine:** replay metadata projection; provider/model secret-like redaction; node-scoped event filter.
- **Variabile unica:** event redaction/replay assertions only; no runtime/provider/model/fallback/scheduler change.
- **Test wet target:** nuova matrice `3/3` in `tests/test_context_file_reading.py` and `tests/test_event_stream.py`, then unified runner.
- **Esito:** redaction/replay matrix `3/3`; context/file/event `15/15`; targeted MVP `107/107`; unified runner `6/6`; OmniRoute direct smoke green; CodeGraph `139/3727/12534`.

### Sotto-iterazione bounded corrente — remaining MutationJournal coverage audit

- **Obiettivo:** verify completed replay, in-flight recovery and failed terminal status across remaining range/path mutation actions without changing mutation semantics, provider/model policy or serial execution.
- **Metrica/soglia:** fixed cases `3/3` per action family: range (`delete_range`, `delete_backward`, `replace_range`), encoding (`convert_encoding`, `normalize_line_endings`), path (`copy`, `move`, `delete`), permissions (`chmod`, `chown`). Threshold 12/12 family checks.
- **Baseline:** `/tmp/mutation-baseline-current.log`: mutation execution/journal suite `51/51 OK`; existing tests cover actions but no compact 12-case audit matrix ties all remaining families to one bounded gate.
- **Casi fissi/ordine:** completed replay; in-flight recovery with one terminal completion; invalid/fail-closed terminal status, in family order range → encoding → path → permissions.
- **Variabile unica:** audit matrix/test coverage only; no mutation runtime behavior or provider/model/parallelism change.
- **Test wet target:** nuova matrice in `tests/test_mutation_execution.py`, then unified runner.
- **Esito:** remaining mutation family matrix `12/12`; mutation/journal `52/52`; targeted MVP `108/108`; unified runner `6/6`; OmniRoute direct smoke green; CodeGraph `139/3728/12535`.

### Sotto-iterazione bounded corrente — mutation journal recovery metadata safety

- **Obiettivo:** verify mutation replay/recovery JSONL preserves action/key/status metadata without leaking mutation content, and replay remains node-scoped.
- **Metrica/soglia:** fixed safety cases `3/3`: mutation replay metadata; mutation recovery metadata; node-filtered replay excludes another node. Threshold 3/3.
- **Baseline:** `/tmp/mutation-audit-targeted.log`: mutation/journal `52/52 OK`, but no fixed redaction/replay matrix covers mutation metadata and node scope.
- **Casi fissi/ordine:** completed replay event; in-flight recovery event; node-filtered replay.
- **Variabile unica:** mutation event/replay safety assertions only; no mutation semantics/provider/model/fallback/scheduler change.
- **Test wet target:** nuova matrice `3/3` in `tests/test_mutation_execution.py` and `tests/test_event_stream.py`, then unified runner.
- **Esito:** mutation replay/recovery safety `3/3`; mutation/journal/event `58/58`; targeted MVP `109/109`; unified runner `6/6`; OmniRoute direct smoke green; CodeGraph `139/3729/12552`.

### Sotto-iterazione bounded corrente — pause/resume checkpoint safety

- **Obiettivo:** validate existing persisted handoff/capsule resume boundary with a 3-case safety matrix, without adding cancellation/parallelism or changing provider/model policy.
- **Metrica/soglia:** `3/3` fixed cases green: node capsule reopen; file-read checkpoint reopen; suspended provider handoff resume. Threshold 3/3.
- **Baseline:** `/tmp/pause-resume-baseline.log`: individual capsule/file/provider tests exist, but no single bounded matrix asserts all recovery boundaries and no runtime pause/cancel contract is authorized.
- **Casi fissi/ordine:** `NodeExecutionCapsule` reopen; `file_reads` offset/hash checkpoint reopen; provider suspension handoff waiting→resume.
- **Variabile unica:** acceptance matrix/test composition only; no new pause/cancel API, provider/model/fallback, mutation or parallelism change.
- **Test wet target:** nuova matrice `3/3` in `tests/test_goal_loop_orchestrator.py`, `tests/test_file_read_recovery.py`, `tests/test_agent_integration.py`, then unified runner.
- **Esito:** pause/resume checkpoint matrix `3/3`; goal/file/agent recovery `46/46` (`1` skip); targeted MVP `120/120` (`1` skip); unified runner `6/6`; OmniRoute direct smoke green; CodeGraph `139/3732/12582`.

### Sotto-iterazione bounded corrente — context provider/model selection matrix

- **Obiettivo:** verify context budget/chunk/compaction evidence for two explicitly selected provider identities while preserving manual ownership and no fallback/provider changes.
- **Metrica/soglia:** `3/3` fixed cases green: cheap budget identity; chatgpt budget identity; selected-node chunk/compaction metadata. Threshold 3/3.
- **Baseline:** `/tmp/context-node-provider-baseline-current.log`: context suite `9/9 OK`; `_context_budget` exposes fields, but no fixed matrix covers two provider identities plus event metadata under selected node.
- **Casi fissi/ordine:** `_context_budget("cheap")`; `_context_budget("chatgpt")`; `read_file_chunk` and prompt compaction with selected provider/model budget.
- **Variabile unica:** acceptance matrix over existing context paths; no router selection, fallback, provider/model policy, mutation or parallelism change.
- **Test wet target:** nuova matrice `3/3` in `tests/test_context_file_reading.py`, then unified runner.
- **Esito:** context provider/model selection matrix `3/3`; context suite `10/10`; targeted MVP `121/121` (`1` skip); unified runner `6/6`; OmniRoute direct smoke green; CodeGraph `139/3733/12589`.

### Sotto-iterazione bounded corrente — integrità output del unified runner

- **Obiettivo:** far valutare al runner output JSON completo senza includere log completi nel report bounded.
- **Metrica/soglia:** 100% dei 6 gate del manifest eseguiti in ordine; soglia 6/6, con output report limitato a tail redacted/bounded.
- **Baseline:** `/tmp/unified-validation-baseline.log`: gate `simulation_matrix` termina `returncode=0` ma runner fallisce `stdout is not JSON` perché `_run()` conserva solo ultimi 4000 caratteri del JSON.
- **Casi fissi/ordine:** evaluator con stdout completo + tail; manifest 6 gate IDs unici/in ordine; runner list mode; docs checker.
- **Variabile unica:** separare stdout completo usato dall'evaluator dal tail conservato nel report; nessuna modifica runtime/provider/model/parallelismo.
- **Esito:** runner fixed-order esegue `6/6` gate verdi: simulation `29/29`, targeted MVP `103/103`, full discovery `588/588` con `5` skip, CLI `3/3`, OmniRoute direct smoke, docs `17/17` con `0` errori. Report bounded conserva solo tail stdout/stderr.

### Sotto-iterazione bounded corrente — sospensione fail-closed di errori provider

- **Obiettivo:** classificare errori transitori di rete/limite d'uso come sessione sospesa anche con selezione provider manuale e fallback negato, senza cambiare ownership provider/model o autorizzazione fallback.
- **Metrica/soglia:** casi fissi integrazione verdi 2/2 (100%).
- **Baseline:** `/tmp/full-matrix-current-baseline.log`: full discovery 588 test, 5 failure e 1 error; entrambi i casi network/token-reset restituiscono `fallback_not_authorized`/`exception` invece di `Session suspended`/`waiting`.
- **Casi fissi/ordine:** network failure → handoff `waiting` e messaggio sospensione; usage/token limit → handoff `waiting`, messaggio sospensione e resume completato.
- **Variabile unica:** classificazione errore sospendibile prima del blocco fallback manuale; nessun fallback/provider/model/parallelismo nuovo.
- **Test wet target:** `test_agent_resumes_suspended_network_session_from_persisted_handoff`, `test_agent_resumes_after_token_reset_from_persisted_handoff`.
- **Esito:** `2/2` verdi; network e usage-limit persistono handoff `waiting`, messaggi `Session suspended`, resume completa file e chiude handoff. Policy provider/model, fallback e serialità invariati.

### Sotto-iterazione bounded corrente — riconciliazione status CLI con policy manuale

- **Obiettivo:** aggiornare il solo caso CLI obsoleto che assume routing automatico, così full discovery rifletta `selection_mode=manual` e `allow_provider_fallback=false` già definiti dal MVP.
- **Metrica/soglia:** caso status CLI verde e full discovery senza failure/error; soglia `1/1` caso mirato e `588` test full con `0` failure/`0` error.
- **Baseline:** `/tmp/full-unittest-baseline-20260923.log`: `588` test, `1` failure, `5` skip; `test_interactive_shell_status_and_mode_commands` cerca `chatgpt ... selection=automatic` su workspace senza policy persistita.
- **Casi fissi/ordine:** status shell con default policy; `model policy` manual/fallback-off; full `python3 -m unittest discover -s tests -q`.
- **Variabile unica:** aspettativa test aggiornata da automatico storico a manuale MVP; nessuna modifica runtime/provider/model/fallback/parallelismo.
- **Test wet target:** `tests.test_trace_cli.TraceAndCliTests.test_interactive_shell_status_and_mode_commands`, poi full discovery.
- **Esito:** caso mirato verde; full discovery `588/588 OK` con `5` skip intenzionali.

### Iterazione bounded corrente — Node Knowledge Store/index acceptance matrix

- **Obiettivo:** chiudere acceptance matrix per Node Knowledge Store context/history, node-scoped retrieval/citation, Python code index, compaction e file-read recovery senza sostituire CodeGraph o allargare scope.
- **Metrica/soglia:** 100% dei 6 casi fissi verdi: context isolation, citation/source, Python symbols/lines, deterministic compaction, stale/fresh index behavior, file-read checkpoint/reopen; soglia 6/6.
- **Baseline:** comportamento parziale in `tests.test_node_knowledge`/`tests.test_file_read_recovery`; matrice esplicita stale/fresh e cross-node isolation assente in `/tmp/node-knowledge-coverage-baseline.log`.
- **Casi fissi/ordine:** node context isolation, citation metadata, code symbols/line ranges, compaction, stale/fresh reindex, file-read checkpoint/reopen; poi suite node/file/context.
- **Wet validation:** matrix `6/6`; Node Knowledge/file/context/event suite `19/19 OK`; goal-loop/event/tools suite passed; OmniRoute free smoke green; `py_compile`, `git diff --check` passed. CodeGraph `137 files / 3685 nodes / 12326 edges`.
- **Gate completato precedente:** tree/packet matrix 6/6; evidenza in `AGENT_HANDOFF.md` e `HANDOFF.md`.

### Iterazione bounded corrente — tree/packet acceptance matrix

- **Obiettivo:** chiudere acceptance matrix per tree invariants, deterministic bottom-up serial ordering, WorkPacket parent→child, ResultPacket child→parent e lateral rejection senza cambiare parallel policy.
- **Metrica/soglia:** 100% dei 6 casi fissi verdi: root/cycle invariants, ready ordering, packet contract, result evidence/parent scope, lateral block, serial run projection; soglia 6/6.
- **Baseline:** `/tmp/tree-packet-coverage-baseline.log`: partial goal-loop tests existed; explicit six-case matrix absent.
- **Casi fissi/ordine:** invalid roots/cycles, deterministic ready ordering, WorkPacket rejection, ResultPacket evidence/parent, lateral control rejection, serial run/replay; poi suite goal/event/node knowledge.
- **Wet validation:** matrix `6/6`; goal-loop suite `32/32 OK`; goal/event/node/context/recovery `115/115 OK`; executor-event + tools `56/56 OK`; OmniRoute free smoke green; `py_compile`, `git diff --check` passed. CodeGraph `137 files / 3684 nodes / 12316 edges`.
- **Gate completato precedente:** context budget/compaction matrix 6/6; evidenza in `AGENT_HANDOFF.md` e `HANDOFF.md`.

### Iterazione bounded corrente — context budget/compaction acceptance matrix

- **Obiettivo:** chiudere acceptance matrix per budget contesto, auto-compaction, chunk metadata e replay per nodi/provider/model senza cambiare routing o serialità.
- **Metrica/soglia:** 100% dei 6 casi fissi verdi: provider budget, node budget, chunk cap, compaction reduction, JSONL metadata/replay, recovery persistence; soglia 6/6.
- **Baseline:** `/tmp/context-budget-coverage-baseline.log`: base context tests esistenti, ma matrice esplicita provider/node/replay/recovery assente.
- **Casi fissi/ordine:** cheap budget, catalog/user budget, node prompt budget, chunk cap, compaction event reduction, JSONL replay/reopen metadata; poi suite context/file/event recovery.
- **Wet validation:** matrix `6/6`; `tests.test_context_file_reading tests.test_executor_event_stream tests.test_event_stream tests.test_file_read_recovery` `15/15`; executor/goal/node knowledge `... OK`; OmniRoute free smoke green; `py_compile`, `git diff --check` e handoff checks passed. CodeGraph `137 files / 3683 nodes / 12305 edges`.
- **Gate completato precedente:** MutationJournal coverage audit 16/16 chiuso; evidenza in `AGENT_HANDOFF.md` e `HANDOFF.md`.

### Iterazione bounded corrente — mutation journal coverage audit

- **Obiettivo:** auditare journal/replay/recovery coverage per tutti gli action types mutanti dichiarati, senza introdurre nuovi provider/model o parallelismo.
- **Metrica/soglia:** 100% dei 16 action types mutanti dichiarati hanno key stabile, replay completato, `in_flight` recovery e terminal failure test; soglia 16/16.
- **Baseline:** `/tmp/mutation-journal-coverage-baseline.log`: 16 dichiarati; branch/schema presenti, ma nessuna matrice dedicata; `apply_patch` e `insert_text_file` non restituivano recovery metadata; write/apply/insert failure cases mancanti.
- **Casi fissi/ordine:** `write_file`, `apply_patch`, `search_replace_file`, `patch_file`, `patch_files`, `insert_text_file`, `delete_range_file`, `delete_backward_file`, `replace_range_file`, `convert_encoding_file`, `normalize_line_endings_file`, `delete_path_file`, `copy_path_file`, `move_path_file`, `chmod_path_file`, `chown_path_file`; per ciascuno key/replay/recovery/failure, poi suite mutation/event/file recovery.
- **Wet validation:** mutation execution `48/48`; aggregate mutation/executor/event/file recovery `116/116`; executor-event + tools `56/56`; static matrix `16/16`; OmniRoute free smoke green; `py_compile`, `git diff --check` and handoff/text/JSON checks passed. CodeGraph after test edit: `137 files / 3681 nodes / 12291 edges`.
- **Gate completato precedente:** `chown_path_file` ha superato replay, recovery e failure terminale; coverage audit ora chiuso; evidenza in `AGENT_HANDOFF.md` e `HANDOFF.md`.

### Profilo formale canonico

Usare composizione minima e verificabile:

```text
Markdown                 regole e specifica
JSON + JSON Schema       packet e tool action
Tree/DAG                 piano e dipendenze
FSM                      lifecycle e ciclo nodo
Invariants + gates       completion fail-closed
NodeExecutionCapsule     contesto, checkpoint e recovery
JSONL                    audit e replay
Node Knowledge Store     memoria per nodo e code-aware retrieval
```

Prompt non è source of truth operativo. Nessun blackboard globale, messaggio laterale libero o parallelismo legacy implicito.

## Metrica e soglia

- **Metrica:** copertura dei requisiti approvati nella specifica, documentazione, matrice di acceptance e piano di implementazione.
- **Soglia:** 100% dei requisiti obbligatori ha contratto, owner, stato, caso di test e criterio di completamento; nessuna implementazione runtime prima dell'approvazione utente.

## Requisiti non negoziabili

- Albero nodi come unità primaria di pianificazione, esecuzione, contesto, responsabilità e audit.
- Costruzione albero distinta da esecuzione: piano top-down; lavoro operativo bottom-up.
- Nodo padre può inoltrare lavoro a nodo figlio soltanto tramite work packet tipizzato, con obiettivo, scopo, vincoli, input, output e acceptance criteria.
- Risultati risalgono al padre come evidence/result packet; comunicazione laterale vietata per default.
- Multiagente non deve essere dispersivo: un solo nodo attivo per default; parallelismo solo tra foglie indipendenti e solo se autorizzato.
- Ogni nodo ha scopo visibile e ricordato nel terminale insieme a identificatore, padre, stato e lavoro corrente.
- Terminale deve mostrare attività reale: eventi, tool, file, test, prompt/context budget, provider/modello, messaggi, errori, pause e transizioni.
- RAG deve conservare storia e contesti per nodo, decisioni, risultati, evidenze e recovery.
- RAG deve offrire indice semantico/strutturale di file, moduli, classi, procedure, funzioni, test e relazioni con path e intervalli di riga.
- Indice Stagewarden deve essere orientato a recupero per nodo e contesto; CodeGraph resta solo strumento ausiliario di sviluppo, non source of truth.
- Dimensione contesto, budget prompt, limiti provider/modello, compattazione automatica e scelta provider/modello restano espliciti e sotto responsabilità utente.
- Nessun invio, fallback, costo o uso credenziali implicito.

## Regole di fase

- [x] Fermare loop ricorrenti e implementazione feature.
- [x] Registrare nuova direzione node-first/bottom-up/RAG/terminal observability.
- [x] Riscrivere specifica canonica completa.
- [x] Riscrivere tutta documentazione utente, architettura e policy.
- [x] Consolidare piano in questo unico TODO.
- [x] Validare link, terminologia, UTF-8, assenza di backlog duplicati e coerenza handoff.
- [x] Ottenere autorizzazione utente per MVP testabile su OmniRoute free.
- [x] Derivare backlog MVP implementativo dal requisito node-first.
- [ ] Approvare le decisioni residue per la release v3 completa.

## Piano ordinato

### P0 — Baseline e decisioni architetturali

- [x] Verificare branch, worktree, CodeGraph e stato handoff.
- [x] Leggere implementazione attuale di albero, goal loop, handoff, RAG, memoria e terminale.
- [x] Leggere riferimenti Pi rilevanti: auto-compaction, catalogo provider/modelli, subagent.
- [ ] Classificare capacità esistenti: retain, redesign, deprecate, remove.
- [ ] Registrare esplicitamente rischi: parallelismo dispersivo, stato duplicato, RAG non node-scoped, stream non osservabile, purpose non persistito, limiti contesto impliciti.

**Completamento P0:** tabella capability-gap nella specifica e decisioni coerenti con requisiti utente.

### P1 — Specifica canonica node-first

- [ ] Creare `docs/specs/stagewarden-v3.md` come unica specifica prodotto approvabile.
- [ ] Definire concetti: tree, node, parent/up, child/bottom, leaf, work packet, result packet, evidence packet, node context, node purpose, knowledge index, event.
- [ ] Definire lifecycle: intake, tree design, readiness, bottom-up execution, upward aggregation, closure, recovery.
- [ ] Definire invarianti tree: identità stabile, parent unico, edge autorizzato, scopo obbligatorio, acceptance obbligatoria, stato persistito, ownership esplicita.
- [ ] Definire scheduler bottom-up e regole di readiness, dipendenza, retry, block, escalation, pause, resume e cancellation.
- [ ] Definire forwarding parent→child e return child→parent; vietare delega implicita e comunicazione laterale predefinita.
- [ ] Definire parallelismo limitato, concorrente e osservabile; default seriale per node path.
- [ ] Definire node context e history, inclusa compattazione per nodo.
- [x] Definire RAG/Node Knowledge Store: schema, ingestion, retrieval, citazioni, versioni, retention e redazione.
- [ ] Definire indice code-aware di file/classi/procedure/funzioni/test e relazioni; specificare perché è superiore all'uso diretto di CodeGraph per retrieval operativo.
- [ ] Definire terminal event protocol, pinned node banner, purpose reminder, full activity stream, JSONL/RPC e replay.
- [ ] Definire context accounting, model/provider ownership e auto-compaction nel lifecycle del nodo.
- [x] Definire permessi, dati inviabili, segreti, tool mutanti e audit.
- [x] Definire failure/recovery e idempotenza tool.
- [x] Definire acceptance matrix e metriche.
- [x] Definire migrazione dal runtime attuale senza considerare l'architettura legacy come vincolo.

**Completamento P1:** specifica v3 leggibile, non ambigua, con contratti e casi misurabili.

### P2 — Documentazione prodotto e operativa

- [x] Riscrivere `README.md` per nuova architettura e percorso utente.
- [x] Riscrivere `README_IT.md` come guida primaria italiana, coerente con README.
- [x] Riscrivere `docs/architecture.md` come architettura node-first.
- [x] Riscrivere `AGENT_MANIFESTO.md` con disciplina del nodo e osservabilità.
- [x] Riscrivere `AGENT_POLICY.md` e `AGENT_POLICY.json` con bottom-up, forwarding, RAG e terminale.
- [x] Riscrivere `ROADMAP.md` come puntatore/deprecazione: piano unico in `TODO.md`, nessun backlog duplicato.
- [x] Aggiornare `models/README.md` e `models/providers/README.md` chiarendo che provider/model sono scelta utente e dati di capacità non sono autorizzazione.
- [x] Aggiornare `docs/source_references.md`, `docs/status_research.md`, `docs/external_io_help_audit.md`, `docs/kilocode_provider_coverage.md` come materiale di riferimento con stato e non come specifica concorrente.
- [x] Riscrivere `docs/specs/stagewarden-v2.md` come avviso `superseded` che rimanda alla v3, evitando specifiche confliggenti.
- [x] Aggiornare esempi di configurazione per node policy, terminale, RAG, context e ownership senza segreti.
- [x] Revisionare `.pi/prompts/*.md` per allineare linguaggio e flusso; nessun prompt deve autorizzare parallelismo o forwarding implicito.

**Completamento P2:** documentazione pubblica e interna usa stessa terminologia e stessa architettura.

### P3 — MVP implementativo node-first per OmniRoute free

**Casi fissi e ordine:** protocollo packet; tree bottom-up seriale; terminal purpose/events; Node Knowledge Store/history; code-aware Python index; context budget/compaction policy; adapter OmniRoute free; regression legacy.

**Metrica:** acceptance cases MVP superati.
**Soglia:** 100% dei casi MVP automatici verdi; live OmniRoute è verde oppure esplicitamente blocked dall'ambiente.

- [x] Separare primo contratto WorkPacket/ResultPacket dal runtime legacy.
- [x] Implementare state/event projection MVP.
- [x] Implementare scheduler seriale bottom-up MVP.
- [x] Implementare WorkPacket/ResultPacket e forwarding controllato MVP.
- [x] Implementare terminal renderer live + JSONL replay MVP (`events`, `events replay`).
- [x] Emettere eventi JSONL per tool result, file chunk, file complete e context compaction.
- [x] Registrare `events` e `events replay` nel command catalog/help surface.
- [x] Aggiungere filtro stream/replay per nodo (`events node <id>`, `events replay <id>`).
- [x] Esporre `EventStream.follow(node_id)` per consumer live/polling del multiplexer.
- [x] Chiudere connessioni Node Knowledge Store per evitare leak durante sessioni/test.
- [x] Implementare Node Knowledge Store SQLite persistente e retrieval node-scoped MVP.
- [x] Implementare code-aware Python index incrementale MVP di file/classi/funzioni.
- [x] Collegare context accounting e compaction al singolo nodo.
- [x] Aggiungere stato ciclo locale per nodo (`cycle_id`, fase, revisione contesto, checkpoint e budget bounded).
- [x] Emettere checkpoint JSONL per ciclo nodo senza abilitare parallelismo.
- [x] Implementare lettura file context-aware: chunk automatici basati su contesto residuo.
- [x] Persistire file completi fuori dal prompt e permettere ricostruzione completa oltre il limite.
- [x] Auto-compattare contesto prima del chunk successivo quando budget insufficiente.
- [x] Persistire checkpoint file-read in Node Knowledge Store e riprendere da offset dopo reopen.
- [x] Migrare tool execution con idempotenza e checkpoint MVP per mutazioni file (`MutationJournal`), inclusi `write_file`, `apply_patch`, `insert_text_file`, `search_replace_file`, `patch_file` e `patch_files`.
- [x] Esporre journal mutazioni con CLI `mutations [completed|failed]`.
- [x] Migrare provider/model selection manuale e fallback autorizzato MVP: policy persistita `selection_mode`, `allow_provider_fallback`, `allow_paid_provider`; fallback bloccato per default.
- [x] Applicare `selection_mode=manual` al router/executor: nessuna euristica task, variante o fallback provider silenzioso; fallback solo con policy esplicita.
- [x] Esporre policy ownership provider/model via CLI `model policy` e nel report `model limits`.
- [x] Allineare capability baseline includendo `model policy`.
- [ ] Estendere `MutationJournal` alle mutazioni range/path restanti, con replay, `in_flight` recovery e test fail-closed.
- [ ] Portare solo extension/subagent capability approvate.
- [ ] Aggiungere migrazione dati e compatibility layer temporaneo.

**Completamento P3 MVP:** test automatici node/RAG/packet verdi; live OmniRoute free verde oppure blocker esterno registrato. La specifica v3 completa resta gate per estensioni oltre MVP.

### P4 — Test e validazione wet-run

- [x] Creare matrice scenari unica dentro `tests/data/unified_validation_matrix.json` con runner fisso `scripts/run_unified_validation.py`.
- [x] Implementare validator MVP tree: root unico, parent/dependency esistenti, cicli bloccati, ordine bottom-up seriale preservato.
- [x] Rendere ready-node selection deterministica per profondità parent e `node_id`; dipendenze completate restano gate obbligatorio.
- [x] Testare tree invariants e bottom-up ordering.
- [x] Validare edge packet MVP: ResultPacket parent-scoped, evidence list obbligatoria e result forwarding solo al parent autorizzato.
- [x] Validare WorkPacket delegation contract: parent edge, dependency e acceptance criteria obbligatori.
- [x] Validare forwarding child→parent typed result dopo completion, con evidence list e target parent dichiarato.
- [x] Documentare stack formale canonico e confini tra prompt, stato nodo, history, storage ed eventi.
- [x] Testare forwarding parent→child e result child→parent.
- [x] Bloccare comunicazione laterale nel control path: solo parent→child/child→parent edges autorizzati ricevono message state.
- [x] Testare blocco comunicazione laterale e delega senza contratto.
- [ ] Testare serial default e parallel opt-in con collisioni.
- [x] Testare purpose banner e current-node stream in TTY, non-TTY, JSONL e replay.
- [x] Testare Node Knowledge Store: storia per nodo, retrieval, citazioni, stale index, redazione.
- [x] Testare indice code-aware: file/class/function/procedure/test e riferimenti.
- [x] Estendere replay JSONL con proiezione cycle_id, phase, context_revision e last_checkpoint per terminale/recovery.
- [x] Proiettare in replay metadata compaction context e mutation recovery per resume/terminal consumers.
- [x] Emettere in `file_chunk` replay metadata di budget: input disponibile, prompt chars before/after e auto-compaction.
- [x] Emettere in `context_compaction` metadata di budget e prompt chars before/after.
- [ ] Testare context budget/compaction per nodo e provider/model scelti.
- [x] Testare file piccolo, file oltre il contesto, ricostruzione completa, offset e compaction durante lettura.
- [x] Testare recovery journal `in_flight` per mutazione file e impedire riesecuzione duplicata dopo interruzione.
- [x] Rendere recovery `in_flight` file mutation bounded e osservabile via `mutation_recovery` JSONL.
- [x] Emettere `node_retry` JSONL con retry_count/max_retries e bounded retry gate.
- [ ] Testare crash recovery, retry, pause/resume e tool idempotency completa.
- [x] Persistire `NodeExecutionCapsule` completa nel Node Knowledge Store e ripristinare ciclo/checkpoint dopo reopen dell'orchestrator.
- [x] Estendere MutationJournal a `insert_text_file` con in_flight/completed replay idempotente.
- [ ] Estendere crash recovery da reopen controllato a interruzione durante tool/mutazione non-file.
- [x] Applicare `allow_paid_provider` al routing euristico/catalogo: provider paid/unknown bloccati senza autorizzazione; policy esplicita propagata ad Agent/router e WorkPacket.
- [x] Eseguire suite mirata, suite completa, CLI smoke e simulation matrix in wet-run: unified runner `6/6` verde.
- [x] Aggiornare handoff dopo ogni gate.

## Capability disposition provvisoria

| Area | Decisione provvisoria | Motivo |
|---|---|---|
| Albero PRINCE2/goal loop | redesign profondo | diventa tree operativo unico, non solo blueprint/governance |
| Esecuzione parallela attuale | ridurre e rendere opt-in | dispersione e difficile supervisione |
| Message bus globale | sostituire con edge-scoped packets | evita comunicazione laterale non governata |
| Project handoff | retain come recovery/audit, non come stato operativo unico | lo stato operativo deve essere node/event store |
| RAG attuale `DesignRag` | redesign in Node Knowledge Store | deve contenere storia contesti e code map per nodo |
| CodeGraph | ausiliario | non contiene da solo contesto, purpose, evidenze e retrieval operativo |
| Terminale/stderr minimo | redesign in event stream | utente deve vedere attività reale e scopo nodo |
| Router euristico | manuale default, auto solo autorizzato | provider/model/costo appartengono all'utente |
| Auto-compaction | core per-node | dipende da prompt e limiti provider/modello |
| Pi auto-compact | riferimento concettuale | non copia diretta TypeScript nel runtime Python |
| Pi subagent | defer finché non definito | rischio costi, concorrenza e dispersione |

## Gate di approvazione utente

La fase specifica è chiusa solo quando l'utente approva esplicitamente:

- bottom-up come modalità operativa primaria;
- forwarding parent→child e ritorno evidence child→parent;
- default seriale e regole del parallelismo;
- Node Knowledge Store con storia per nodo e code-aware map;
- terminale osservabile con purpose reminder;
- policy di contesto/compaction e ownership provider/model;
- documentazione riscritta;
- piano unico presente in questo file.

## Vincoli di sicurezza

- Non registrare token, chiavi, sessioni o prompt sensibili nella documentazione o memoria condivisa.
- Non usare CodeGraph/RAG come autorizzazione a modificare file.
- Non dichiarare completato un nodo senza evidence reale.
- Non nascondere cambi modello/provider, compaction, retry, forwarding o escalation.
- Non creare nuovi worktree.

## Comandi di validazione documentale

```bash
codegraph status .
codegraph sync .
git diff --check
python3 - <<'PY'
from pathlib import Path
for path in Path('.').rglob('*.md'):
    data = path.read_bytes()
    data.decode('utf-8')
    assert not data.startswith(b'\xef\xbb\xbf'), path
print('markdown UTF-8/no-BOM: OK')
PY
```
