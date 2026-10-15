# Agent Handoff

## Current objective
Completa contesto isolato per nodo, token budget provider/modello, compattazione automatica e codemode ristretto; decision model va chiamato genericamente, non come nome di modello. Preservare routing/provider/fallback/policy e serialità v3.

## Current state
- Added explicit legacy-only EventStream compatibility regression: two unchained records report valid=true, chain_corrupted=false, count=2. Focused 30 passed/7 subtests; full suite 780 passed, 5 skipped, 339 subtests (317.91s).
- Legacy compatibility cleanup: simplified unchained-event classification; legacy-only stream stays valid, transition into new hashed chain remains flagged; removed unreachable duplicate branch. EventStream 29 passed/7 subtests; full suite 779 passed, 5 skipped, 339 subtests (317.58s).
- Append policy simplification: append now gates solely on `integrity["valid"]`, matching verifier contract and avoiding duplicate classification; behavior preserved. EventStream 29 passed/7 subtests; full suite 779 passed, 5 skipped, 339 subtests (317.97s); static checks pass.
- Hash metadata format hardened: verifier requires lowercase 64-char hex parent/digest strings, not merely strings. Focused test updated for malformed parent; EventStream 29 passed/7 subtests; full suite 779 passed, 5 skipped, 339 subtests (318.69s).
- Chain schema tightening: after chain start, fully missing reserved fields no longer fall back to legacy mode; missing parent/hash are explicitly rejected as malformed strings before hashing/comparison. Focused EventStream 29 passed/7 subtests; full suite 779 passed, 5 skipped, 339 subtests (317.49s).
- Hardening sequence schema: verifier now accepts only non-bool integers for `event_sequence`; bool `true` previously compared equal to 1 and could pass sequence continuity. Added test with correctly recomputed digest proving bool sequence rejected. EventStream 29 passed/7 subtests; full suite 779 passed, 5 skipped, 339 subtests (319.03s).
- Cleanup append path: removed derived `append_errors` list and use integrity report directly in exception; no behavior change. EventStream 28 passed/7 subtests; full suite 778 passed, 5 skipped, 339 subtests (319.51s); static checks pass.
- Closed metadata spoofing path: `append(..., **details)` now strips caller-supplied `event_sequence`, `previous_event_hash`, `event_hash` before writing authoritative chain fields. Regression for forged metadata then valid second append. EventStream 28 passed/7 subtests; full suite 778 passed, 5 skipped, 339 subtests (319.51s).
- Hash-chain hardening completo: sequence, previous-hash e content-digest mismatch interrompono verify al primo errore. Aggiunto digest tampering + malicious tail test. EventStream 27 passed/7 subtests; full suite 777 passed, 5 skipped, 339 subtests (319.13s).
- Integrity chain fail-closed completato: previous-hash mismatch e record hash con digest errato ora terminano scansione al primo failure, oltre a sequence gap. Aggiunto test mismatch+tail maligno; EventStream 26 passed/7 subtests; full suite 776 passed, 5 skipped, 339 subtests (319.91s).
- Chain verifier fail-closed completato: sequence discontinuity ora interrompe scansione al primo record fuori sequenza (prima registrava errore ma esaminava suffix). Regression muta seq=99 e tail seq=100, attesta `events_verified=1` e solo primo errore. EventStream 25 passed/7 subtests; full suite 775 passed, 5 skipped, 339 subtests (319.52s).
- Corretto fail-closed: errore append ora include persistent `chain_broken` anche per invalid JSON in coda a stream firmato (prima il flag non veniva riflesso in `chain_corrupted` se non seguiva record valido). Test stream invalido ora verifica append rifiutato e replay limitato al prefisso. EventStream 24 passed/7 subtests; full suite 774 passed, 5 skipped, 339 subtests (319.18s).
- Cleanup del verifier: removed predicate append ridondante, usa flag di integrity/error unico; legacy counter resta coerente. EventStream 24 passed/7 subtests; compileall/JSON/diff checks passano. Full suite post-cleanup 774 passed/5 skipped/339 subtests (319.62s).
- Hardening legacy corruption: malformed JSON or non-object line after a legacy unchained event now marks stream chain-corrupted; append fails closed. Regression covers legacy→invalid line. EventStream 24 passed/7 subtests; full suite 774 passed, 5 skipped, 339 subtests (319.89s).
- Small maintainability fix: renamed `unparseable_after_chain` flag to `chain_broken` to match persistent semantics (remains set after detection, never reset). EventStream 23 passed/7 subtests; compileall/JSON/diff checks pass. Runtime behavior unchanged.
- Hardening follow-up: reordered corrupted-stream checks so after invalid JSON or legacy records in a hashed chain, verifier halts immediately at next hashed record even when its sequence is malformed; no suffix is examined. Manual adversarial probe sequence=99 reports valid prefix 1. EventStream 23 passed/7 subtests; full suite 773 passed, 5 skipped, 339 subtests (319.14s).
- Correzione recovery audit stream: spostato check di invalid JSON prima del sequence mismatch; così primo record hashato successivo al buco è il boundary di errore anche se sequence manca/salta, e verifier si ferma senza processare suffisso. EventStream 23 passed/7 subtests; compileall/JSON/diff-check passano; full suite 773 passed/5 skipped/339 subtests (319.09s).
- Follow-up integrity cleanup: verifier ora si ferma subito dopo il primo record hashato che segue JSON invalido; conteggio prefisso e logica append rifiutano tutto il suffisso. EventStream focused 23 passed/7 subtests; full suite 773 passed, 5 skipped, 339 subtests (319.16s); compileall/JSON/diff checks passano.
- Continuazione 2026-10-14: `verify_integrity()` ora imposta `valid=false` anche se chain_corrupted è true senza nuovi errori testuali, rendendo esplicito fail-closed per invalid JSON nel mezzo degli eventi hashati. EventStream 23 passed/7 subtests; full suite 773 passed, 5 skipped, 339 subtests (318.01s); compileall/diff-check passano.
- Continuazione: trovata lacuna integrità: invalid JSON inserito tra record hashati era ignorato da verify e append, spezzando chain senza fail-closed. Ora segna chain corrotta quando record hashato successivo segue una riga non decodificabile; tail invalid non incide finché non arriva record successivo. Regressione aggiunta; EventStream 23 passed/7 subtests. Full suite: 773 passed, 5 skipped, 339 subtests (318.64s).
- Continuazione 2026-10-14: test Windows `msvcrt.locking` aggiunto via fake msvcrt e lockfile temporaneo; controlla lock/unlock 1-byte con seek offset zero e sentinel inizializzato. EventStream 22 passed/7 subtests; full suite 772 passed, 5 skipped, 339 subtests (318.93s). È test logico su POSIX, non esecuzione Windows nativa.
- Investigazione regressione 2026-10-14: tentativo manuale multiprocessing `spawn` da stdin non è un test valido: child Python non può importare `__main__` da `<stdin>` (`FileNotFoundError`), comando scaduto in attesa queue. Nessun processo figlio ha completato append; nessun impatto repository noto. Il test pytest usa helper top-level in file ed è il percorso valido e ora termina esplicitamente eventuali processi appesi; EventStream 21 passed/7 subtests.
- Continuazione: allineato sidecar process lock al path canonico risolto, evitando lock distinti quando target è aperto via symlink. Aggiunto regression test alias path; EventStream 21 passed/7 subtests; full suite 771 passed, 5 skipped, 339 subtests (316.81s). Rimossa annotazione `ContextManager` fuorviante dal generator decorato `@contextmanager`; focused, py_compile, compileall, JSON e diff checks passano.
- Continuazione 2026-10-14: aggiunto sidecar advisory lock cross-process in `EventStream.append()` (fcntl POSIX, msvcrt Windows), oltre al lock condiviso intra-process; test `spawn` con 2 processi × 10 append simultanei preserva chain. EventStream 20 passed/7 subtests; full suite 770 passed, 5 skipped, 339 subtests (317.32s). Nel seguito tipizzato `_process_lock() -> ContextManager[None]`; import typing consolidati. mypy non installato, ma py_compile/focused/compileall/JSON/diff checks passano.
- Continuazione 2026-10-14: EventStream usa lock condiviso per path canonicale tra istanze nello stesso processo; prima lock per istanza consentiva race sequence/hash chain su file condiviso. Aggiunto concurrency wet test (2 writer × 25 append); focused ripetuto: 19 passed/7 subtests. Full suite precedente a questa ripresa: 769 passed, 5 skipped, 339 subtests (317.10s). Nessuna ulteriore modifica implementativa in questo turno; static checks passano.
- Continuazione: rinforzata hash-chain eventi contro inserzione non firmata in mezzo alla chain e riordino; ora append rifiuta corruzione chain rilevata senza bloccare righe JSONL non decodificabili legacy. Casi insert/reverse aggiunti. EventStream tests 18 passed, 7 subtests; full suite: 768 passed, 5 skipped, 339 subtests (428.61s). `compileall`, handoff JSON parse e `git diff --check` passano.
- Continuazione 2026-10-14: aggiunta integrità hash-chain append-only in `EventStream`, `verify_integrity()` segnala JSON invalido/record alterati e append rifiuta catena verificabile corrotta; legacy e linee JSON invalide restano leggibili per compatibilità. Tamper test e chain tests inclusi. Full wet suite: 767 passed, 5 skipped, 337 subtests (505.57s); `compileall`, JSON parse e `git diff --check` passano. Ripristinati anche i bit locali Git `assume-unchanged` sui file Stagewarden: nessuna differenza codice rispetto a HEAD; evitare che future modifiche siano occultate.
- Ripresa sessione 2026-10-14: `main`; full suite pre-edit: 766 passed, 5 skipped, 332 subtests. Corretto boundary bug in compaction UTF-8: trimming/head-tail split potevano oltrepassare byte cap per caratteri multibyte o cap minuscolo. Aggiunto trimming entro hard ceiling, inclusione marker nel limite e regressioni per cap 1/8/10/100/300 bytes, più scan per tutti i cap 1–79 su UTF-8 misto. Focused goal-loop: 76 passed, 36 subtests (ripetuto dopo estensione cap 1–79). Full wet suite post-fix: 766 passed, 5 skipped, 337 subtests (346.58s; codice invariato dall’estensione test-only). `compileall`, JSON parse e `git diff --check` passano.
- Implementati contesto/revision UUID-scoped per nodo, budget input da catalogo/config con riserva output/margine, compattazione, persistenza knowledge e append/read contestuale.
- Budget finale controlla prompt standard + skills; over-budget fail-closed, context node limitato al residuo. Metadata dichiara `token_counter=utf8_byte_upper_bound_v1` e `accounting_unit=utf8_bytes_upper_bound_not_provider_tokens`; test verifica marker su NodeState e WorkPacket. Goal-loop 74 passed/28 subtests; full suite 761 passed/5 skipped/320 subtests (317.82s).
- Test remoto ora free-only anche nei benchmark OpenRouter espliciti: `STAGEWARDEN_TEST_FREE_MODEL` default `auto/coding:free`; live test saltano se override non termina `:free`, smoke shell fallisce chiuso. OmniRoute free detection accetta suffisso `:free` e due alias fallback esatti (`auto/best-free`, `coding-free-fallback`); respinge `/free/` segmento permissivo e substring incidentali. Adapter: 11 passed/1 skipped/20 subtests; full suite: 765 passed/5 skipped/329 subtests (438.64s).
- Memory loader usa token count solo con contatore esplicito; tokenizer runtime non presente (`transformers`, `tiktoken`, `tokenizers`, `sentencepiece` assenti). Wet mock `run_loop` verifica nodi/eventi/capsule e restart terminale; fix resume precedente ignorava capsule completed/failed, ora ripristina stato terminale e campi bounded (context/revision/messages/output/error). OmniRoute riceve max_tokens clampato a minimo tra cap catalogo, reserve e override, ma è richiesta non garanzia provider; env max tokens OmniRoute e limiti goal-loop input/output/reserve/margin validati come interi positivi; config malformata fallisce chiusa invece di annullare silently tutti i limiti. Opt-in `STAGEWARDEN_GOAL_LOOP_REQUIRE_OUTPUT_CAP=true` fail-closes prima subprocess sia con Pi che OmniRoute: nessuno dei due backend dimostra enforcement. Default off preserva behavior esistente.
- Terminologia decision model: usare nome generico, non nominare JEV come modello.
- Context snapshot knowledge include UUID nel provenance; recovery seleziona snapshot UUID-scoped di revision >= capsule (snapshot wins on tie), evita capsule stale. Test restart e precedence aggiunti.
- Stima token fallback modificata da 3 char/token a UTF-8 byte bound, gestendo correttamente testo Unicode; compattazione ora rispetta cap byte. Non equivale a tokenizer provider reale.
- Strict budget env distingue unset (default) da vuoto/whitespace (errore). OmniRoute max_tokens bound 1..131072 (default 4096), over-range fail-fast JSON/exit 2; adapter tests 10 passed/1 skipped/12 subtests. Full suite 764 passed/5 skipped/321 subtests (317.74s). `STAGEWARDEN_GOAL_LOOP_REQUIRE_OUTPUT_CAP` valida boolean fail-closed. Opt-in input-budget tested: 75 passed/28 subtests; full suite 762 passed/5 skipped/320 subtests (318.85s). `STAGEWARDEN_GOAL_LOOP_REQUIRE_INPUT_BUDGET=true` rifiuta limit unknown, input override esplicito consente progress. Policy input budget valida ora boolean literal; `maybe`/`2`/`enabled` rifiutati. Goal-loop 76 passed/31 subtests; full suite 766 passed/5 skipped/332 subtests (342.96s).

## Recent changes
- `stagewarden/event_stream.py`, `tests/test_event_stream.py`: sequenza + hash chain opzionali su eventi, verifica integrità e blocco append su corruzione chain; regressione anti-tamper.
- `stagewarden/goal_loop_orchestrator.py`, `stagewarden/node_knowledge.py`: token budget skills, UTF-8 byte estimator/compaction, snapshot UUID provenance e recovery post-restart.
- `tests/test_goal_loop_orchestrator.py`: test estimator Unicode e byte-cap compaction.
- `tests/test_goal_loop_orchestrator.py`: regressione resume snapshot context node-scoped.
- `tests/test_goal_loop_orchestrator.py`: regressione skill eccedente budget fail-closed.
- `scripts/run_model_omniroute.py`, `tests/test_omniroute_adapter.py`: filtraggio free-only con fallback e fail-closed testati offline.
- `stagewarden/memory_context.py`: loader bounded con token counter esplicito.
- `tests/test_goal_loop_orchestrator.py`, `tests/test_memory_context.py`: isolamento, overflow e codemode.
- `stagewarden/goal_loop_orchestrator.py::_compact_node_text`: limite UTF-8 byte della compaction.
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
- Tokenizer provider e overhead tool/schema/system non verificati; UTF-8 byte upper bound non è token count.
- Memory token compaction non collegata al caller; compattazione resta non semantica/loss-aware non verificata.
- Output-cap backend non verificato: OmniRoute `max_tokens` è solo request; Pi CLI senza cap documentato. Opt-in fail-closed presente.
- Event replay semantics non implementate/verificate.

## Next steps
1. Full regression post-fix: 771 passed, 5 skipped, 339 subtests; eseguire static checks finali.
2. Verificare tokenizer provider e output-cap solo con evidenza runtime disponibile; nessuna chiamata remota non necessaria, test remoti free-only.
3. Integrare tokenizer/usage solo con evidence provider; mantenere UTF-8 estimator fallback.

## Commands
```bash
python -m compileall -q stagewarden tests
python -m pytest --ignore=external_sources -q
python -m json.tool .stagewarden_handoff.json
```
