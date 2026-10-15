# Prompt ingegnerizzato — completamento Stagewarden al 100%

> File: `PROMPT_MASTER_100.md`
> Scopo: un **unico prompt pronto da incollare** a un modello agente (`gpt-6-luna`) per portare il progetto Stagewarden v3 al 100% della definizione di fatto, integrando gestione del contesto avanzata, tecniche PRINCE2 e supporto multi-modello globale.
> Uso: copia il blocco dalla sezione **PROMPT** in fondo. La parte sopra è contesto e tracciamento, da leggere ma non da incollare se non serve.

---

## 1. Stato attuale (studio del repository, 2026-10-15)

**Branch:** `main`, avanzato su `origin/main` di ~652 commit, indietro di 4. Commit HEAD: `stagewarden: initialize workspace`. Cambiamenti di lavoro **non committati** sui soli file di handoff.

**Architettura di riferimento** (`ROADMAP.md`, `docs/specs/stagewarden-v3.md`):
- Stagewarden pianifica **top-down**, esegue **bottom-up**. Esecuzione di default **seriale**.
- Passaggio padre→figlio con `WorkPacket`; completamento figlio→padre con `ResultPacket` e `EvidencePacket` verificato.
- Storico nodo, contesto e retrieval del codice vivono nella **Node Knowledge Store**.
- Il terminale mostra sempre nodo attivo, purpose, lavoro, evidenza e stato del contesto.

**Componenti principali (`stagewarden/`):**
| Area | File | Note |
|---|---|---|
| Orchestrazione goal-loop | `goal_loop_orchestrator.py` (~1613 righe) | loop seriali, compaction, budget, event emission |
| Conoscenza per nodo | `node_knowledge.py` | SQLite + `RLock`; contesto UUID-scoped, capsule, ricerca, file-read session |
| Contesto memoria | `memory_context.py` | loader token-aware solo se riceve contatore |
| Catalogo modelli | `model_catalog.py` | limiti contesto/budget per modello |
| Event stream | `event_stream.py` | hash-chain opzionale, replay, integrità fail-closed |
| PRINCE2 | `prince2.py` (~643 righe), `prince2_benchmark.py` | temi/processi |
| Adapter modello | `scripts/run_model_omniroute.py` | free-only, no paid fallback |
| Project flow | `stagewarden/project/*` | brief, design flow, ruoli, albero |

**Fatto e verificato (full regression verde):** `800 passed, 5 skipped, 361 subtests (≈330s)`.
- Contesto per nodo **isolato UUID-scoped** con revisioni, snapshot di conoscenza, recovery post-restart.
- **Codemode ristretto** read/append con check **CAS `expected_revision`**; conflitto su scrittura concorrente con stessa revisione.
- Append valida e rifiuta: operazioni/payload non-stringa, surrogate UTF-8 non validi, budget zero, payload sovradimensionati; `bool` **non** trattato come intero.
- Persistenza verificata: il contenuto esatto persistito in SQLite viene riletto e confrontato; memoria/revisione riconciliate o rollback.
- Eventi di audit emessi **solo dopo** persistenza riuscita. Su fallimento EventStream primario: record di fallback best-effort via `ProjectHandoff` e **nessuna** falsa affermazione di audit riuscito.
- Budget prompt **section-aware**; estimator **UTF-8 byte upper-bound** (`utf8_byte_upper_bound_v1`), etichettato esplicitamente **non** come conteggio token del provider.
- Compattazione **deterministica**, bounded per byte, con marker boundary, Unicode e cap minuscoli testati.
- Replay riconcilia tool in-flight su operation-ID duplicati; clear su stati terminali e su `node_skipped`/`node_blocked`.
- EventStream: hash-chain, append locked, prefix verificato, torn-tail, compat legacy; **fail-closed** al primo record non valido.
- File-read: `begin_file_read` valida limiti interi stretti (rifiuta `bool`); checkpoint/complete rifiutano session/hash/content malformati e Unicode non valido **prima** della mutazione; API serializzate sotto `RLock`.

**Vincolo test/costo (già operativo):** qualsiasi test con chiamate remote deve usare route/modelli **esplicitamente gratuiti** e **fallire chiuso** se appare fallback a modello non-free. I test unitari/mock restano **offline**; nessuna API a pagamento.

---

## 2. Lacune note (restano aperte, da non risolvere con affermazioni non dimostrate)

- **Tokenizer/contatore token reale del provider**: non verificato; i pacchetti tokenizer controllati non erano disponibili. Non dichiarare conteggi token esatti senza evidenza runtime.
- **Enforcement dell'output cap**: Pi CLI non espone flag max-output/max-tokens documentati (`pi --help` verificato); `max_tokens` di OmniRoute è una **richiesta**, non enforcement provider verificato. Mantenere fail-closed quando l'enforcement richiesto manca (`STAGEWARDEN_GOAL_LOOP_REQUIRE_OUTPUT_CAP=true`, `STAGEWARDEN_GOAL_LOOP_REQUIRE_INPUT_BUDGET=true`).
- **Locking nativo Windows**: non testato su Windows; la branch Windows esistente è mockata.
- **Migrazione/riparazione automatica dell'EventStream**: non implementata (nessuna migrazione implicita legacy→hashed).

---

## 3. Vincoli non negoziabili (invarianti)

1. **Nessuna migrazione v2.** Nessun subagente, nessun plugin.
2. **Non modificare** comportamento di provider/modello/fallback/routing/policy.
3. **Preservare la serialità v3**: esecuzione di default seriale; niente esecuzioni concorrenti tra nodi.
4. **Nessuna chiamata a pagamento** nei test; free-only + fail-closed su fallback.
5. **Fail-closed**: se un enforcement richiesto (cap, budget, integrità) non è dimostrabile, rifiutare l'esecuzione invece di fingere successo.
6. **Nessuna affermazione non dimostrata**: no "token esatti del provider", no "output cap imposto" senza evidenza runtime.
7. Il **decision model** va riferito **genericamente**, mai per nome di modello o vendor, nella descrizione delle decisioni interne.
8. Mantenere allineati `AGENT_HANDOFF.md`, `HANDOFF.md`, `.stagewarden_handoff.json` dopo ogni cambiamento significativo.
9. Niente commit/push senza autorizzazione esplicita.

---

## 4. Definizione di fatto (Definition of Done)

Il progetto è "al 100%" solo quando **tutti** i criteri sono dimostrati con evidenza eseguibile (test verdi + wet-run dove possibile):

- **D1** Contesto per nodo completo, isolato e recuperabile a ogni ripartenza (UUID-scoped, revisioni, snapshot, recovery) — *in larga parte già fatto, da chiudere con casi limite rimasti*.
- **D2** Gestione del contesto "evoluta" (vedi §5) implementata **dentro** i vincoli di serialità e fail-closed.
- **D3** PRINCE2 applicato ai flussi di progetto (vedi §6): temi, processi, prodotti e Management Stage Gate tracciabili.
- **D4** Supporto multi-modello globale (vedi §7): catalogo estensibile per **tutti i modelli disponibili**, senza rompere policy di routing/fallback e restando free-only per i test.
- **D5** Budget/compattazione corretti per modello, con accountant pluggabile e nessuna affermazione di token esatti senza evidenza.
- **D6** Integrità EventStream e semantica replay chiuse e testate.
- **D7** Full regression verde: `python -m pytest --ignore=external_sources -q` → **≥ 800 passed, 0 failed**; `compileall`, validazione JSON handoff e `git diff --check` puliti.

---

## 5. Gestione del contesto evoluta (obiettivo "più possibile avanzata")

Deve essere implementata come **estensione** dell'attuale contesto UUID-scoped, senza toccare routing/policy/serialità. Direzione (ogni voce è verifica `si/no` con test):

- **Jerararchia del contesto**: system/fixed instructions → assegnate skills → memoria per nodo → output recente → sintesi. La gerarchia è già *section-aware*; renderla esplicita come pipeline di **priorità** con dimostrazione che il troncamento colpisce le sezioni più basse per prime.
- **Compattazione loss-aware**: non solo per byte; identificare **cosa** comprimere preservando marcatori, riferimenti UUID e revisioni. Estendere l'attuale compattazione deterministica con una policy **più selettiva** mantenendo l'invariante "bounded per byte".
- **Rituale di memoria (memory ritual)**: chiusura di ogni nodo con **Lesson Learned** + **Issue/Decision log** che alimenta la Knowledge Store dei nodi figli. Allineare con PRINCE2 (§6).
- **Reattivazione della memoria (memory re-activation)**: quando un nodo figlio deve decidere, riattivare il contesto rilevante dei **genitori/antenati** invece di caricare tutto. Confinato per nodo (già garantito dallo scope) — estendere con **retrieval mirato** invece di scan completo.
- **Ricerca semantica**: l'attuale `search` è a token. Aggiungere punteggio più ricco solo se resta offline/deterministico; altrimenti dichiarare esplicitamente il limite e **non** reclamare "semantic search" se è solo keyword.
- **Accountant pluggabile**: interface per il conteggio del contesto per modello, con fallback byte-upper-bound **etichettato**; divieto di claim di token esatti senza tokenizer verificato.
- **Observability**: ogni compaction/append emette evento con revisione, byte, sezione toccata — già in parte presente, da rendere completo e testato.

---

## 6. PRINCE2 (tecniche da applicare ai flussi)

`stagewarden/prince2.py` esiste. Estendere i flussi di progetto (`stagewarden/project/*`) così che i **7 temi** siano tracciati come stati/strutture nel terminale e nei prodotti:

1. **Business Case** — perché il nodo esiste, value/urgency. Già legato a `project/brief.py`.
2. **Organization** — ruoli, responsabilità (RACI), escalation. `project/role_*.py`.
3. **Quality** — definizione di "qualità" per il deliverable del nodo + acceptance criteria dimostrabili.
4. **Plans** — piano per prodotti (deliverable), piani di livello team/stage/project.
5. **Risk** — identificazione, valutazione, risposta. Colmare con issue/risk log.
6. **Change** — controllo del change (Change Authority/EC), configuration management.
7. **Progress** — monitoraggio vs baseline, exception report, **Management Stage Gate**.

**Processi da mappare**: Starting/Initiating a Project, Directing, Controlling a Stage, Managing a Stage Boundary, Managing Product Delivery, Closing. Ogni nodo/WorkPacket è una unità di **Managing Product Delivery**; la **Stage Boundary** è il punto di Lesson Learned e ripianificazione; il **Stage Gate** è il punto di verifica evidence prima del passaggio successivo (allineato all'esistente fail-closed).

**Prodotto-chiave da rendere tracciabili**: Project Brief, Project Initiation Documentation (PID), Risk Log, Issue Log, Lessons Log, Stage Plan, Product Description, End Stage Report. Colmare lo stato nel terminale.

---

## 7. Supporto multi-modello globale ("tutti i modelli disponibili")

Obiettivo: il catalogo possa **assorbire tutti i modelli disponibili globalmente** senza rompere routing/fallback/policy né la serialità.

- **Estensione del catalogo**: schema per provider → modello → limiti contesto/budget/finestre. Estendere `stagewarden/model_catalog.py` + script di build (`scripts/build_ai_models_catalog.py`, `generate_provider_model_tree.py`).
- **Adapter generici**: riusare il pattern dell'attuale adapter free-only (`scripts/run_model_omniroute.py`) per nuovi provider, mantenendo **free-only** per i test e **fail-closed** su fallback a pagamento.
- **Capability discovery**: per ogni modello documentare (o dichiarare "sconosciuto") input context window, output cap, streaming, tool-use, modalità. **Non inventare**: se non verificabile, marcare come unknown e comportarsi in fail-closed.
- **Nessun cambio di policy**: l'inclusione di un modello nel catalogo **non** deve alterare routing/fallback esistenti; l'inclusione è un dato, non un comportamento.
- **Compat budget**: ogni modello deve poter fornire un **accountant** (§5) o dichiarare fallback byte-upper-bound.

---

## 8. Approccio di lavoro (MVP-first)

1. Un **deliverable alla volta**; niente sotto-attività per aggirare limiti.
2. Obiettivo = **una** frase + **una** coppia metrica+soglia. Usa la **rubrica fissa §9** quando il risultato è qualitativo.
3. **Percorso diretto** prima: agente principale, un solo percorso, strumenti già disponibili, **nessun subagente, nessun componente nuovo**.
4. Se baseline ≥ soglia → **fermati**. Niente architettura/iterazioni decorative.
5. Se baseline < soglia → **stessi casi, stesso ordine, stessa soglia**; ogni iterazione cambia **una sola variabile** misurata (prima `prompt`, poi `input`, poi config, poi gate subagente come ultima risorsa).
6. **Preferisci wet-run** quando l'ambiente lo permette; dry-run solo come supplemento, mai sostituto.
7. Dopo ogni passo: regression mirata + allinea i tre handoff.

---

## 9. Rubrica di accettazione (0/1 per criterio)

| # | Criterio | 1 | 0 |
|---|---|---|---|
| R1 | Contesto per nodo isolato UUID-scoped persistito e verificato esatto | | |
| R2 | Compattazione bounded per byte con marker preservati | | |
| R3 | Budget account pluggabile, fallback byte-upper-bound **etichettato**, nessun claim di token esatti | | |
| R4 | PRINCE2: almeno 7 temi tracciati + Stage Gate evidence-based | | |
| R5 | Catalogo multi-modello estensibile senza cambiare routing/fallback/policy | | |
| R6 | Integrità EventStream fail-closed + replay riconcilia tool in-flight | | |
| R7 | Full regression verde ≥800 passed, 0 failed; compileall/JSON/diff puliti | | |
| R8 | I tre handoff allineati e aggiornati | | |

**Soglia di accettazione: 8/8.** Un solo criterio a 0 ⇒ non completato.

---

## 10. Comandi

```bash
# ambientazione
python -m venv /tmp/stagewarden-venv
/tmp/stagewarden-venv/bin/pip install -e .          # o equivalente pyproject

# test focalizzati
/tmp/stagewarden-venv/bin/python -m pytest tests/test_node_knowledge.py tests/test_goal_loop_orchestrator.py -q

# regression completa (fonte di verità)
/tmp/stagewarden-venv/bin/python -m pytest --ignore=external_sources -q

# pre-commit statici
/tmp/stagewarden-venv/bin/python -m compileall -q stagewarden tests
/tmp/stagewarden-venv/bin/python -m json.tool .stagewarden_handoff.json >/dev/null
git diff --check
```

---

---

# PROMPT

Copia tutto il blocco qui sotto come messaggio al modello.

```
Sei l'agente principale del repository Stagewarden (branch main). Obiettivo: portare il progetto al 100% della Definition of Done mantenendo INTATTI i vincoli di invarianti.

CONTESTO ATTUALE (verificato):
- Stagewarden v3 pianifica top-down ed esegue bottom-up; esecuzione di default SERIALE. Passaggio WorkPacket (padre→figlio), ResultPacket + EvidencePacket (figlio→padre). Contesto/storico/retrieval vivono nella Node Knowledge Store (SQLite + RLock, contesto isolato UUID-scoped con revisioni).
- Fatto e verde: full regression 800 passed, 5 skipped, 361 subtests. Contesto per nodo isolato con revisioni e recovery post-restart; codemode read/append con CAS expected_revision; append valida stringhe/UTF-8/budget e rifiuta bool; persistenza verificata leggendo il contenuto esatto; eventi di audit solo dopo persistenza; budget section-aware con estimator UTF-8 byte-upper-bound (utf8_byte_upper_bound_v1) etichettato NON come token provider; compattazione deterministica bounded per byte; EventStream hash-chain fail-closed con replay che riconcilia tool in-flight; file-read session con validazione stretta e RLock.

VINCOLI (non negoziabili):
1) Nessuna migrazione v2, nessun subagente, nessun plugin.
2) NON modificare provider/modello/fallback/routing/policy.
3) PRESERVA la serialità v3 (nessuna concorrenza tra nodi).
4) Nessuna chiamata a pagamento nei test: free-only + fail-closed su fallback.
5) Fail-closed: se un enforcement (cap, budget, integrità) non è dimostrabile, RIFIUTA l'esecuzione invece di fingere successo.
6) Nessuna affermazione non dimostrata: mai "token esatti del provider" né "output cap imposto" senza evidenza runtime.
7) Riferisci il decision model GENERICAMENTE, mai per nome di modello/vendor.
8) Dopo ogni cambiamento significativo mantieni allineati AGENT_HANDOFF.md, HANDOFF.md, .stagewarden_handoff.json.
9) Niente commit/push senza autorizzazione esplicita.

DELIVERABLE (uno alla volta, MVP-first; baseline = primo risultato; se >= soglia fermati, altrimenti cambia UNA sola variabile per iterazione in ordine prompt -> input -> config -> gate subagente):
A) GESTIONE CONTESTO EVOLUTA (estendere l'attuale UUID-scoped, dentro i vincoli): pipeline di priorità delle sezioni con troncamento che colpisce le sezioni basse per prima; compattazione loss-aware (che cosa comprimere preservando marker, UUID e revisione, restando bounded per byte); rituale di memoria di chiusura nodo (Lesson Learned + Issue/Decision log che alimenta i figli); reattivazione mirata della memoria di antenati invece di caricare tutto; ricerca più ricca solo se offline/deterministica, altrimenti dichiararne il limite; accountant pluggabile per modello con fallback byte-upper-bound etichettato; observability completa di append/compaction.
B) PRINCE2 nei flussi di progetto (stagewarden/project/* e prince2.py): traccia i 7 temi (Business Case, Organization, Quality, Plans, Risk, Change, Progress) come stati/prodotti nel terminale; mappa i processi (Starting/Initiating, Directing, Controlling a Stage, Managing a Stage Boundary, Managing Product Delivery, Closing) su nodi/WorkPacket/Stage Gate; rendi tracciabili Brief, PID, Risk/Issue/Lessons Log, Stage Plan, Product Description, End Stage Report; Stage Gate = verifica evidence prima del passaggio, coerente con il fail-closed esistente.
C) MULTI-MODELO GLOBALE: estendi il catalogo (model_catalog.py + scripts di build) per assorbire tutti i modelli disponibili globalmente come DATI (provider, limiti contesto/budget/finestre, capability), senza alterare routing/fallback/policy; riusa il pattern adapter free-only; per ogni capability non verificabile marca "unknown" e comportati in fail-closed; ogni modello deve avere un accountant o dichiarare fallback byte-upper-bound.

CHIUSURA DEL CICLO: dopo ogni passo esegui la regression mirata e poi il pieno controllo: pytest --ignore=external_sources -q (>=800 passed, 0 failed), compileall, json.tool sul handoff, git diff --check; aggiorna i tre handoff.

ACCETTAZIONE (rubrica fissa, soglia 8/8; 0 su un criterio = non completato):
R1 contesto isolato UUID-scoped persistito e verificato esatto; R2 compattazione bounded con marker preservati; R3 accountant pluggabile con fallback byte-upper-bound etichettato e nessun claim di token esatti; R4 PRINCE2 con 7 temi tracciati + Stage Gate evidence-based; R5 catalogo multi-modello estensibile senza cambiare routing/fallback/policy; R6 EventStream fail-closed + replay riconcilia in-flight; R7 full regression >=800 passed 0 failed e statici puliti; R8 tre handoff allineati.

Riporta per ogni deliverable: metrica usata, soglia, baseline vs iterazione, e l'evidenza eseguibile (comando + output sintetico). Non dichiarare completato un criterio senza la sua evidenza.
```

---

## 11. Note finali

- **`gpt-6-luna`** è il modello target richiesto dall'utente. Questo file non ne afferma l'esistenza o la disponibilità: se al runtime il modello non è configurabile, il comportamento corretto di Stagewarden è **fail-closed** (o fallback esplicito per policy), mai sostituzione silenziosa. L'integrazione concreta di un provider/modello va fatta §7 (catalogo come dati) senza toccare routing/policy.
- I riferimenti al **decision model** nel prompt sono **generici**, per coerenza con la convenzione del repository.
- Se serve la versione inglese del prompt o una variante "solo PRINCE2" / "solo multi-modello", chiedila esplicitamente: deliverable separati, non sottattività.
