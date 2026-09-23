# Stagewarden — Architettura node-first

**Stato:** direzione v3 in approvazione; runtime attuale legacy fino al gate di migrazione.
**Piano unico:** [`../TODO.md`](../TODO.md)
**Specifica canonica:** [`specs/stagewarden-v3.md`](specs/stagewarden-v3.md)

## Modello

Stagewarden tratta albero e nodi come sistema operativo del lavoro:

```text
root purpose
└── parent purpose
    ├── leaf work packet → evidence
    └── leaf work packet → evidence
        ↑ result aggregation
    parent result
↑ root decision
```

Pianificazione è top-down. Esecuzione è bottom-up. Parent prepara lavoro e aggrega risultati; leaf esegue lavoro concreto. Default seriale. Parallelismo solo opt-in tra foglie isolate.

## Piani architetturali

### Tree Store

Conserva tree version, node contracts, parent/child edges, purpose, ownership, acceptance, scope, dependencies e status.

### Scheduler

Seleziona una leaf `ready`, crea active event, inoltra work packet, attende result/evidence, aggiorna knowledge store e rivaluta parent. Nessun parent può completare senza child evidence obbligatoria.

### Packet protocol

- `WorkPacket`: parent → child;
- `ResultPacket`: child → parent;
- `EvidencePacket`: riferimenti verificabili a tool, file, test e provider usage.

Comunicazioni laterali sono negate per default.

### Protocollo formale minimo

Runtime usa composizione limitata di strutture formalizzate:

- Markdown per regole e specifica;
- JSON/JSON Schema per packet e tool action;
- tree/DAG per piano e dipendenze;
- FSM per lifecycle e ciclo locale del nodo;
- invarianti, pre/postcondizioni e gate per completion;
- NodeExecutionCapsule per stato persistente e recovery;
- JSONL append-only per audit e replay.

Non sono source of truth DSL proprietarie, blackboard globale, parallelismo implicito o formalismi aggiuntivi non approvati.

### Node Execution Capsule e contesto

Ogni nodo mantiene capsula persistente con identità, purpose, parent, packet reference, ciclo, fase FSM, revisione contesto, checkpoint, budget, stato e next action. Il contesto è separato in active context, node working state, node history e storage; retrieval è una vista temporanea, non memoria concorrente.

### Node Knowledge Store

RAG persistente con namespace per tree/node/context/event/decision/evidence/code/relation/provider/recovery. Include storia del contesto per nodo e indice code-aware di file, classi, procedure, funzioni, metodi, test e relazioni con path/linee/hash/freshness.

CodeGraph può fornire analisi ausiliaria. Non è source of truth: non contiene automaticamente purpose, work packet, evidenze, ownership, compaction o policy.

### Event Store e terminale

Ogni cambio importante produce evento persistente. TTY mostra banner pinned con tree, node, parent, purpose, stato, lavoro e context budget; stream mostra tool, file, test, forwarding, result, compaction, blocker e decisioni. JSONL consente replay e integrazione machine-readable.

### Context manager

Ogni nodo ha context budget. Prompt, retrieved knowledge, child summaries, tool schema, output reserve, overhead e margine vengono contabilizzati. Compaction automatica agisce sul nodo attivo prima del superamento del limite del provider/modello selezionato.

Provider, modello, account, credenziali, costi e fallback sono selezionati/autorizzati dall'utente. Nessun cambio implicito.

## Trust boundaries

- RAG è dati non fidati, non istruzioni eseguibili.
- Retrieval non concede permessi.
- Evidence abilita completion solo dopo verifica.
- Tool mutanti richiedono scope, permission e idempotency key.
- Eventi persistiti devono redigere segreti.
- Limit/provider metadata devono avere fonte, timestamp e freshness.

## Stato migrazione

1. Specifica v3 e documentazione.
2. Event/node state shadow layer.
3. Scheduler bottom-up seriale.
4. Packet protocol.
5. Terminal event stream.
6. Node Knowledge Store/code index.
7. Context compaction per nodo.
8. Switch default e rimozione graduale message bus legacy.

Vedere `TODO.md` per ordine e gate.
