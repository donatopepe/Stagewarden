# Stagewarden v3 — Specifica canonica node-first

**Stato:** bozza per approvazione utente  
**Versione:** 3.0-draft  
**Data:** 2026-09-22  
**Sostituisce:** `docs/specs/stagewarden-v2.md`  
**Implementazione:** congelata fino ad approvazione esplicita

## 1. Decisioni di prodotto

Stagewarden viene reingegnerizzato attorno all'albero dei nodi. Il nodo è unità primaria di:

- lavoro;
- responsabilità;
- contesto;
- memoria;
- retrieval;
- esecuzione;
- osservabilità;
- recovery;
- evidenza di completamento.

Il lavoro non viene gestito come insieme indistinto di agenti concorrenti. L'albero viene progettato top-down, ma l'esecuzione operativa procede bottom-up: prima le foglie pronte, poi i nodi superiori che aggregano risultati e decidono il lavoro successivo.

Un nodo superiore può inoltrare lavoro verso un nodo inferiore, ma solo tramite contratto esplicito. Il figlio non riceve un prompt libero privo di scopo e il padre non considera completato il lavoro senza un result/evidence packet verificabile.

## 2. Problema

Il modello multiagente concorrente è dispersivo:

- l'utente fatica a capire quale agente sta lavorando;
- i risultati arrivano fuori ordine;
- il contesto viene duplicato o perso;
- comunicazioni laterali e retry rendono difficile ricostruire decisioni;
- il terminale mostra poco lavoro reale e non ricorda lo scopo del nodo;
- il RAG attuale è prevalentemente design-oriented e non è un archivio node-scoped completo;
- CodeGraph descrive simboli e relazioni, ma non è una memoria operativa con storia, purpose, evidenze, stato o contesto per nodo.

## 3. Obiettivi

1. Rendere l'albero il sistema operativo del lavoro.
2. Rendere bottom-up l'esecuzione predefinita.
3. Ridurre la dispersione tramite serialità di default e parallelismo limitato.
4. Rendere ogni inoltro e ritorno tipizzato, tracciato e verificabile.
5. Conservare storia e contesto separati per nodo.
6. Creare un indice operativo code-aware che permetta retrieval mirato di file, classi, procedure, funzioni, test e relazioni.
7. Mostrare nel terminale nodo attivo, scopo, stato, attività reale e risultato.
8. Collegare budget prompt, limiti provider/modello e auto-compaction al singolo nodo.
9. Conservare governance, permessi, wet-run, audit e recovery senza trasformarli in concorrenza non osservabile.
10. Lasciare provider, modello, account, credenziali, costi, quote e fallback sotto responsabilità dell'utente.

## 4. Non-obiettivi

- Non creare un team di agenti autonomi senza supervisione visibile.
- Non usare parallelismo come default per diminuire il tempo se riduce tracciabilità.
- Non consentire messaggi laterali arbitrari tra nodi.
- Non trattare CodeGraph come memoria completa o autorizzazione.
- Non compattare contesti cancellando evidenze necessarie alla ripresa.
- Non scegliere provider/modello a pagamento senza autorizzazione.
- Non portare automaticamente tutte le estensioni Pi.
- Non mantenere più documenti concorrenti che definiscono il piano operativo.

## 5. Terminologia

### 5.1 Albero
Grafo operativo aciclico radicato, con un solo root e un parent operativo per nodo. Le relazioni operative sono parent/child; riferimenti a nodi esterni sono link read-only o dependency edge esplicito.

### 5.2 Nodo
Unità persistente con identità stabile, scopo, responsabilità, prompt policy, contesto, knowledge scope, stato, input/output contract, acceptance criteria, ownership provider/model e stream eventi.

### 5.3 Nodo up / parent
Nodo che possiede un obiettivo superiore, prepara work packet per figli, attende risultati, integra evidenze e decide se completare, delegare altro lavoro o escalare.

### 5.4 Nodo bottom / child
Nodo che esegue un work packet delimitato, produce evidence e result packet, aggiorna il proprio contesto e non amplia autonomamente scope.

### 5.5 Foglia
Nodo senza child operativo. Esegue tool/model work concreto e produce evidenza primaria.

### 5.6 Work packet
Contratto parent→child. Contiene almeno:

- `work_id`, `tree_id`, `parent_node_id`, `child_node_id`;
- scopo e risultato atteso;
- task atomico;
- input e riferimenti knowledge;
- file/path consentiti;
- strumenti e permessi;
- provider/modello/account autorizzati;
- context budget e policy compaction;
- acceptance criteria;
- vincoli e tolleranze;
- deadline/retry policy;
- output contract;
- correlation id.

### 5.7 Result packet
Contratto child→parent. Contiene summary, stato, output, evidence references, file modificati, test/comandi, uso contesto, errori, rischi, decisioni, lavoro residuo e proposta del prossimo passo.

### 5.8 Evidence packet
Parte verificabile del result packet: output tool, path, hash, righe, test result, exit code, timestamp, provider/model e correlazione al work id. Un testo narrativo non è evidence sufficiente.

### 5.9 Node context
Contesto attivo e storia del nodo: purpose, vincoli, work packet corrente, eventi, tool result, decisioni, risultati figli, errori, summary di compaction e riferimenti knowledge.

### 5.10 Node Knowledge Store
RAG persistente orientato ai nodi, composto da storia contestuale, evidenze, decisioni e indice code-aware. Deve fornire citazioni e provenienza.

### 5.11 Node Execution Capsule
Capsula persistente per ogni nodo: identità, parent, purpose, work/result references, FSM cycle, context revision, checkpoint, budget, status, next action e recovery metadata. La capsula non sostituisce lo storage completo: active context, node working state, node history e storage restano livelli distinti.

### 5.12 Protocollo formale minimo
La baseline usa Markdown per regole, JSON/JSON Schema per contratti, tree/DAG per piano, FSM per lifecycle, invarianti e gate per completion, Node Knowledge Store per memoria e JSONL per audit/replay. DSL proprietarie, blackboard globale e formalismi aggiuntivi richiedono approvazione separata.

## 6. Invarianti dell'albero

Ogni tree deve rispettare:

1. un solo root;
2. identità univoca e stabile per nodo;
3. parent unico per nodo operativo;
4. niente cicli;
5. purpose non vuoto e distinto da label;
6. acceptance criteria non vuoti;
7. owner umano/agent/provider esplicito;
8. stato e ultimo evento persistiti;
9. child eseguibile solo con work packet valido;
10. result obbligatorio prima di child completion;
11. parent completion solo dopo criteri propri e aggregazione evidenze;
12. comunicazione laterale negata per default;
13. file scope e permessi verificabili;
14. provider/model/account selezionati o policy di blocco esplicita;
15. ogni modifica del tree produce versione e audit event.

## 7. Stati nodo

```text
planned
ready
waiting_children
running
waiting_input
waiting_user
blocked
compacting
verifying
completed
failed
cancelled
stale
```

Transizioni vietate:

- `planned → running` senza readiness e work packet;
- `running → completed` senza evidence e acceptance;
- `blocked → running` senza nuovo evento di sblocco;
- `compacting → running` prima della persistenza del summary;
- qualsiasi stato → `completed` se un child obbligatorio è pending/failed.

## 8. Pianificazione top-down, esecuzione bottom-up

### 8.1 Costruzione

Il root riceve obiettivo e vincoli. La progettazione scompone il lavoro in nodi con:

- purpose;
- deliverable;
- acceptance;
- dipendenze;
- scope file/knowledge;
- modello/provider policy;
- rischio e tolleranza;
- strategia di verifica.

La costruzione è top-down perché il significato del lavoro deriva dall'obiettivo superiore.

### 8.2 Readiness

Un nodo leaf è `ready` se:

- work packet validato;
- dipendenze completate;
- input presenti o esplicitamente mancanti;
- permessi disponibili;
- budget contesto calcolato;
- provider/model configurati secondo ownership policy;
- nessuna tool call mutante dello stesso scope in volo.

Un nodo parent diventa `ready` dopo che:

- tutti i child obbligatori hanno result packet;
- evidenze child sono indicizzate;
- conflitti sono risolti o escalati;
- acceptance aggregate sono valutabili.

### 8.3 Scheduler

Scheduler v1 deve essere seriale per default:

1. sceglie una leaf ready secondo ordine deterministico;
2. la marca active/running;
3. emette evento e banner terminale;
4. esegue work packet;
5. verifica e indicizza evidence;
6. produce result packet;
7. aggiorna parent;
8. rivaluta readiness.

Parallelismo è opt-in per un gruppo di foglie indipendenti con:

- file scope disgiunto o lock espliciti;
- contesti separati;
- budget separati;
- terminale che distingue stream;
- merge/evidence gate del parent;
- limite di concorrenza configurato dall'utente.

### 8.4 Perché bottom-up

- Riduce contesto inutile nei nodi superiori.
- Produce evidenze prima delle decisioni aggregate.
- Rende visibile una sola attività operativa alla volta.
- Impedisce al parent di dichiarare lavoro completato sulla base di proposte non verificate.
- Permette al parent di inoltrare solo lavoro residuo concreto.

## 9. Forwarding parent→child

Il parent non invia testo libero come delega implicita. Crea un `WorkPacket` versionato.

Il forwarding deve:

1. citare il purpose del parent e il purpose del child;
2. delimitare scope e acceptance;
3. includere solo context/knowledge necessari;
4. dichiarare file e strumenti autorizzati;
5. dichiarare provider/model/account e budget;
6. specificare output contract;
7. registrare correlation id e causation event;
8. mostrare nel terminale `UP → DOWN`;
9. attendere ack `accepted|rejected|needs_clarification`;
10. non cambiare scope senza nuovo packet/versione.

Un child può rispondere:

- `accepted`: prende lavoro;
- `needs_clarification`: non esegue e restituisce domanda;
- `rejected`: indica violazione o impossibilità;
- `result`: restituisce risultato;
- `blocked`: restituisce blocker e recovery;
- `escalation`: chiede decisione parent/user.

## 10. Return child→parent e aggregazione

Il child restituisce solo al parent salvo audit/event sink. Il parent deve:

- validare schema e correlation id;
- verificare evidence referenziate;
- inserire result nel proprio Node Context;
- aggiornare Node Knowledge Store;
- confrontare output con acceptance;
- registrare decisione `accept|retry|forward|block|escalate`;
- inoltrare altro lavoro solo se necessario e tipizzato.

Un parent non deve riversare l'intero transcript child nel proprio prompt: usa summary, evidence references e retrieval mirato.

## 11. Node Knowledge Store e RAG

### 11.1 Funzione

Il RAG diventa archivio operativo per nodo e indice di recupero. Non è solo documentazione di design.

### 11.2 Namespace obbligatori

- `tree`: definizione albero e versioni;
- `node`: purpose, scope, stato, work packet, result;
- `context`: snapshot e compaction summary per nodo;
- `event`: eventi append-only;
- `decision`: decisioni e motivazioni;
- `evidence`: tool/test/file evidence;
- `code`: file, moduli, classi, procedure, funzioni, metodi, test;
- `relation`: calls, imports, inheritance, reads, writes, defines, tests, references;
- `provider`: identity, model, limits e usage non segreto;
- `recovery`: checkpoint e resume information.

### 11.3 Entry schema minimo

```json
{
  "entry_id": "nk-uuid",
  "namespace": "node|context|event|decision|evidence|code|relation",
  "tree_id": "tree-uuid",
  "node_id": "build.compiler",
  "parent_node_id": "build",
  "kind": "purpose|context_snapshot|tool_result|function|class|decision",
  "title": "Compile validation",
  "content": "...",
  "source": {
    "type": "runtime|file|test|provider|user",
    "path": "stagewarden/compiler.py",
    "line_start": 100,
    "line_end": 140,
    "event_id": "evt-uuid"
  },
  "tags": ["compiler", "validation"],
  "relations": [{"type": "calls", "target": "nk-other"}],
  "created_at": "...",
  "updated_at": "...",
  "sensitivity": "local|shareable|secret-redacted",
  "content_hash": "sha256:...",
  "embedding_version": "..."
}
```

### 11.4 Node history

Per ogni nodo si conservano:

- purpose e versioni;
- work packet ricevuti/inviati;
- prompt/context snapshots secondo retention policy;
- compaction summaries;
- tool calls e output redatti;
- file/class/function recuperati;
- decisioni;
- result/evidence packet;
- retry, blocker, escalation e resume;
- provider/model/usage non segreto;
- link alla storia parent e child.

La storia completa può essere soggetta a retention utente, ma la perdita deve essere esplicita e non può compromettere il recovery dichiarato.

### 11.5 Retrieval

Ogni query deve supportare filtri:

- `tree_id`, `node_id`, ancestor/descendant;
- namespace/kind;
- file/class/function/test;
- phase/status/time;
- evidence validity;
- sensitivity;
- lexical/vector/hybrid;
- max tokens/characters;
- source citation required.

Il risultato deve indicare score, provenienza, timestamp, freshness e motivo di inclusione. Il modello riceve riferimenti citabili, non contesto non attribuibile.

### 11.6 Indice code-aware

L'indice deve estrarre almeno:

- repository/workspace;
- directory e file;
- linguaggio e parser/versione;
- moduli/package;
- classi e basi;
- funzioni, procedure, metodi e signature;
- test e fixture;
- import/export;
- call/reference relations;
- definisce/usa/legge/scrive;
- intervalli di riga e hash del contenuto;
- nodo che ha indicizzato o usato l'elemento;
- ultima modifica e freshness.

CodeGraph può alimentare estrazione o diagnostica, ma Stagewarden deve aggiungere purpose, storia, evidence, ownership, node scope, freshness e retrieval budget. Per questo CodeGraph non è source of truth del Node Knowledge Store.

## 12. Context accounting e compaction per nodo

Ogni nodo ha un budget separato o un budget ereditato esplicitamente. Il packet deve misurare:

- purpose e work packet;
- prompt utente;
- system/policy;
- knowledge retrieval;
- node history;
- child result summaries;
- tool schema;
- output riservato;
- overhead provider;
- safety margin;
- limite provider/modello/account;
- metodo e attendibilità della misura.

La compattazione è automatica quando il prossimo turno non entra nel budget disponibile. Prima compattare il Node Context del nodo attivo; non compattare indiscriminatamente l'intero albero.

La lettura file deve essere indipendente dalla dimensione della finestra modello. Il tool divide automaticamente ogni file in chunk secondo il budget input residuo e conserva `path`, `offset`, `length`, `total_length`, hash e stato `has_more`. Se il chunk successivo non entra, il sistema persiste il contesto corrente, esegue auto-compaction e riprende dal successivo offset. `read_file_complete` deve poter ricostruire un file completo oltre il context window: il file integrale non viene inserito in un singolo prompt, ma resta in cache/evidence persistente e viene recuperato per chunk. Nessun byte/carattere può essere perso o duplicato.

Il summary deve preservare purpose, acceptance, vincoli, decisioni, file, test, evidence, blocker, child status e next action. Deve essere persistito e validato prima di rimuovere materiale dal packet attivo.

La compattazione non può cambiare provider/modello senza autorizzazione. Se limite o tokenizer sono sconosciuti, si applica policy esplicita dell'utente e mai un default invisibile.

## 13. Terminale e osservabilità

### 13.1 Obiettivo UX

L'utente deve capire in ogni momento:

- quale nodo sta lavorando;
- dove si trova nell'albero;
- qual è lo scopo del nodo;
- quale lavoro è stato inoltrato;
- cosa sta facendo ora;
- quali tool/file/test sono coinvolti;
- quale modello/provider/account è usato;
- quanto contesto resta;
- perché il nodo è in attesa/bloccato/completato;
- quale evidenza sostiene il risultato.

### 13.2 Banner persistente

Ogni stream deve avere un banner aggiornato:

```text
TREE tree-42 | NODE build.compiler | PARENT build | DEPTH 2
PURPOSE: compilare e verificare modulo compiler senza modificare API pubblica
STATUS: RUNNING | WORK: run pytest tests/test_compiler.py
MODEL: user-selected/provider/model | CONTEXT: 42k/110k input | COMPACTION: armed
```

Il purpose deve comparire all'avvio nodo, dopo ogni compaction, dopo resume e quando l'utente chiede status.

### 13.3 Eventi minimi

- tree created/versioned;
- node selected/ready/running/waiting/blocked/completed;
- work forwarded/accepted/rejected;
- tool started/progress/finished/failed;
- file read/written/patched;
- test started/finished;
- context measured/near-limit/compacted;
- model/provider selected/changed;
- evidence indexed/invalid;
- decision/escalation/retry;
- node result returned/aggregated;
- pause/resume/cancel.

Ogni evento include timestamp, tree/node/parent, purpose snapshot o purpose reference, correlation id, human message, structured payload e sensitivity.

### 13.4 Modalità

- TTY live: banner + stream leggibile;
- non-TTY: righe deterministiche senza colori;
- `--json`: report finale strutturato;
- `--events`: JSONL append-only;
- `node status <id>`: stato e purpose;
- `tree status`: vista albero e nodo attivo;
- `tree follow <id>`: stream filtrato per nodo/subtree;
- replay: ricostruzione da event log.

Nessun output importante deve esistere solo in stderr non persistito.

## 14. Ownership provider/model

- Selezione manuale utente default.
- Provider/model/account visibili in ogni node banner e work packet.
- Context window, input limit, output reserve, quota e costo devono avere fonte/timestamp.
- Fallback diverso dal modello scelto richiede policy user-approved.
- Fallback che cambia provider/account o amplia dati inviabili richiede conferma.
- Stagewarden può raccomandare, non sostituire la decisione utente.
- Costi stimati ed effettivi separati.

## 15. Sicurezza e permessi

- Il child riceve solo scope dichiarato.
- Tool mutanti hanno lock/idempotency key e evidence.
- Path fuori scope bloccato.
- Prompt injection da RAG trattato come dato non fidato.
- Segreti redatti da event log, RAG, context snapshot e result.
- Un result narrativo non autorizza merge o completion.
- RAG retrieval non concede permessi.
- Parallelismo richiede isolamento verificato.

## 16. Persistenza e recovery

Store minimi:

- `tree_store`: tree/version/node contracts;
- `event_store`: eventi append-only;
- `node_context_store`: snapshot/compaction per nodo;
- `knowledge_store`: entry RAG e indice code-aware;
- `evidence_store`: riferimenti/output redatti;
- `recovery_store`: checkpoint e idempotency keys.

Scrittura atomica, schema version, hash e recovery da corruzione sono obbligatori. Il resume deve ripristinare nodo attivo, purpose, work packet, tool state, child results e budget senza rieseguire tool mutanti già confermati.

## 17. Failure modes

| Caso | Comportamento |
|---|---|
| Leaf non pronta | non eseguire; mostrare dipendenza mancante |
| Child scope insufficiente | `needs_clarification`; nessuna azione mutante |
| Child amplia scope | blocco e escalation al parent |
| Result senza evidence | reject; nodo non completabile |
| Parent anticipa child | parent resta waiting; nessun completion narrativo |
| Parallel collision | lock conflict; pause/retry controllato |
| RAG stale | mostrare stale; retrieval non silenziosamente autorevole |
| Code index incompleto | dichiarare coverage e chiedere fallback/scan |
| Compaction fallita | conservare context originale; bloccare se budget insufficiente |
| Provider limit sconosciuto | policy utente; nessun default nascosto |
| Provider/model cambia | handshake, re-budget e audit |
| Evento perso | fail closed/recovery da checkpoint |
| Nodo bloccato | purpose + blocker + owner + next decision nel terminale |

## 18. Capability disposition

| Capacità | v3 |
|---|---|
| Tree/goal loop | core redesign |
| Bottom-up scheduler | core |
| Parent→child forwarding | core |
| Child→parent evidence | core |
| Global free-form message bus | remove/deprecate |
| Default parallelism | remove; serial default |
| Opt-in isolated parallel leaves | retain after contract |
| Current project handoff | retain as recovery/audit adapter |
| Current DesignRag | migrate to Node Knowledge Store |
| CodeGraph | auxiliary index source/diagnostic |
| Terminal live status | core |
| Auto-compaction | core per-node |
| Provider/model router heuristic | manual default; auto opt-in |
| Pi auto-compact | reference behavior |
| Pi OmniRoute catalog | optional adapter |
| Pi subagent | defer until explicit scope |
| Pi custom UI/tools | defer/adapter per capability |

## 19. Acceptance matrix

| ID | Caso | Criterio |
|---|---|---|
| TREE-01 | tree valido | invarianti passano |
| TREE-02 | ciclo/parent duplicato | tree rifiutato |
| EXEC-01 | leaf ready | una leaf eseguita prima del parent |
| EXEC-02 | parent con child pending | parent non eseguito/completato |
| EXEC-03 | forwarding | packet completo e correlation id |
| EXEC-04 | return | result/evidence validato e aggregato |
| EXEC-05 | lateral message | bloccato senza edge/policy |
| EXEC-06 | parallel disabled | nessun overlap non autorizzato |
| EXEC-07 | parallel opt-in | solo foglie isolate, stream distinti |
| RAG-01 | history per node | context/eventi restano nel namespace node |
| RAG-02 | retrieval descendant | parent recupera summary/evidence child |
| RAG-03 | retrieval isolation | nodo non vede scope non autorizzato |
| RAG-04 | code map | file/class/function/test con linee e relazioni |
| RAG-05 | stale index | freshness dichiarata |
| RAG-06 | citation | ogni entry recuperata ha source |
| CTX-01 | budget sotto soglia | invio consentito |
| CTX-02 | near limit | compaction automatica per nodo |
| CTX-03 | over limit dopo compact | invio bloccato |
| CTX-04 | compaction failure | history originale intatta |
| CTX-05 | file sotto budget | lettura completa in un chunk |
| CTX-06 | file oltre budget | chunk ordinati, offset contigui, hash finale corretto |
| CTX-07 | compaction durante file read | resume dal prossimo offset senza duplicati |
| CTX-08 | read_file_complete oltre context | contenuto completo ricostruito fuori prompt |
| TERM-01 | TTY | banner mostra node, parent, purpose, work |
| TERM-02 | non-TTY | eventi deterministici |
| TERM-03 | replay | stato ricostruibile da eventi |
| TERM-04 | purpose reminder | appare start/compaction/resume/status |
| REC-01 | crash leaf | resume senza duplicare tool mutante |
| REC-02 | blocked child | terminale mostra blocker/owner/decision |
| OWN-01 | manual model | nessun cambio invisibile |
| OWN-02 | fallback non autorizzato | blocco |
| SEC-01 | secret in output | redazione |
| EVID-01 | completion senza evidence | reject |

## 20. Piano di migrazione

1. Congelare runtime e definire v3 approvata.
2. Introdurre schema/event store senza cambiare esecuzione.
3. Implementare tree validator e node state projection.
4. Implementare scheduler seriale bottom-up in shadow mode.
5. Implementare WorkPacket/ResultPacket/EvidencePacket.
6. Implementare terminal event stream e purpose banner.
7. Implementare Node Knowledge Store e code-aware index.
8. Collegare RAG retrieval e node context compaction.
9. Attivare bottom-up per task opt-in e poi default.
10. Disabilitare message bus/free parallel legacy dopo parity gate.
11. Migrare provider/model/context ownership.
12. Valutare subagent/plugin solo con specifica separata.

## 21. Domande per approvazione

1. Confermi bottom-up come default assoluto o permetti top-down execution per nodi speciali? permetti top-down
2. Confermi serialità per default e parallelismo solo opt-in? si
3. Quale retention vuoi per cronologia completa node context? la più performante
4. Il RAG deve essere SQLite, file store, o backend configurabile? Proposta: SQLite locale con export JSONL. ok
5. Il code-aware index deve coprire Python soltanto nella prima release o anche JavaScript/TypeScript/shell/Java? tutto
6. Vuoi vedere anche prompt completo nel terminale o solo sezioni/eventi redatti? prompt completo
7. Vuoi un nodo attivo alla volta sempre, oppure più foglie simultanee in una vista multiplexer? uno attivo alla volta sempre
8. Il parent può creare nuovi child durante l'esecuzione o il tree deve essere congelato dopo readiness? si puo' creare nuovi child
9. Il parent può inoltrare lavoro allo stesso child più volte con nuove versioni o serve nuovo child attempt id? preferisco nuovo child
10. Confermi che `docs/specs/stagewarden-v2.md` venga mantenuta solo come documento superseded? si

## 22. Criterio di approvazione

La v3 è approvabile quando l'utente conferma le decisioni della sezione 21 e accetta:

- tree node-first;
- top-down planning + bottom-up execution;
- controlled forwarding and evidence return;
- serial default;
- node-scoped context/RAG history;
- code-aware operational index;
- terminal purpose/activity observability;
- per-node context accounting/compaction;
- explicit provider/model ownership;
- TODO unico come piano operativo.
