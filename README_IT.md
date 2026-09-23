# Stagewarden

Stagewarden è un runtime per coding agent governato da un albero operativo di nodi.

**Stato attuale:** architettura e documentazione v3 in reingegnerizzazione. L'implementazione runtime è congelata fino all'approvazione della specifica v3. Il runtime Python esistente resta evidenza legacy, non architettura target.

## Modello di prodotto

Stagewarden non tratta il lavoro come insieme indistinto di agenti. Il lavoro vive in un albero:

```text
scopo root
└── scopo parent
    ├── work packet leaf -> evidence
    └── work packet leaf -> evidence
        ^ aggregazione risultati
    risultato parent
^ decisione root
```

- La pianificazione è top-down.
- L'esecuzione è bottom-up.
- L'esecuzione seriale è il default.
- Il parallelismo è opt-in e limitato a foglie isolate e verificabili indipendentemente.
- Il parent delega tramite `WorkPacket` tipizzato.
- Il child restituisce `ResultPacket` con `EvidencePacket` verificabili.
- La comunicazione laterale libera è negata per default.
- Un nodo non può completare senza evidenza rispetto ai criteri di accettazione.

## Stack del protocollo formale

Stagewarden usa un insieme limitato di strutture formalizzate:

```text
Markdown                 regole e specifica
JSON + JSON Schema       WorkPacket/ResultPacket/EvidencePacket/tool action
tree + DAG                decomposizione e dipendenze
FSM                       lifecycle del nodo e del ciclo
invarianti + gate        completion fail-closed
NodeExecutionCapsule     contesto, checkpoint e recovery del nodo
JSONL                     audit append-only e replay
SQLite Node Knowledge    memoria per nodo e retrieval code-aware
```

Il prompt è input dell'inferenza, non source of truth operativo. Nessun blackboard implicito, messaggio laterale o parallelismo legacy.

## Cosa deve vedere l'utente

Il terminale deve rispondere sempre a queste domande:

1. Quale nodo sta lavorando?
2. Qual è lo scopo di quel nodo?
3. Quale work packet ha ricevuto?
4. Cosa sta facendo adesso?
5. Quali file, tool e test sono coinvolti?
6. Quanto contesto resta?
7. Quale evidenza è stata prodotta?
8. Perché il nodo è in attesa, bloccato, delegato o completato?

Il contratto v3 prevede banner persistente del nodo, promemoria dello scopo dopo resume/compaction, eventi live, eventi JSONL e replay.

## Node Knowledge Store

Il RAG diventa un Node Knowledge Store operativo. Conserva con scope di nodo e provenienza:

- purpose, work packet, risultati, decisioni, blocker e recovery;
- snapshot del contesto e summary di compaction;
- evidenze di tool, file, test e provider;
- file, moduli, classi, procedure, funzioni, metodi, test e relazioni del codice;
- path, intervalli di riga, hash del contenuto, freschezza e sensibilità.

CodeGraph può aiutare l'ispezione dei simboli, ma resta un indice ausiliario di sviluppo. Non è source of truth per contesto, storia, evidenza, ownership, permessi o retrieval del nodo.

## Contesto e ownership dei modelli

Context window, input budget, output riservato, overhead, safety margin, metodo di misura, fonte e freschezza sono dati di prima classe.

La compattazione automatica è comportamento core del nodo. Riduce il contesto attivo prima di superare il limite del provider/modello selezionato, persiste e valida il summary e non cambia mai provider, modello, account o policy di costo in modo implicito.

La lettura dei file è context-aware: Stagewarden legge automaticamente a chunk in base al contesto residuo. Se il chunk successivo non entra, compatta il contesto e continua da offset persistito. Un file può essere letto completamente anche oltre la finestra del modello: il contenuto completo resta fuori dal prompt, in cache/evidence persistente, e viene ricostruito per chunk senza perdita.

Provider, modello, account, credenziali, quote, costi e autorizzazione dei fallback appartengono all'utente. Stagewarden può mostrarli e applicare i vincoli, ma non può scegliere silenziosamente un servizio a pagamento o sostituire il modello selezionato.

## Documentazione

- [`TODO.md`](TODO.md) — unico piano di progetto e unico backlog.
- [`docs/specs/stagewarden-v3.md`](docs/specs/stagewarden-v3.md) — specifica canonica in bozza.
- [`docs/architecture.md`](docs/architecture.md) — architettura node-first e trust boundary.
- [`AGENT_MANIFESTO.md`](AGENT_MANIFESTO.md) — principi operativi.
- [`AGENT_POLICY.md`](AGENT_POLICY.md) — policy formale.
- [`AGENTS.md`](AGENTS.md) — protocollo di continuità degli agenti.
- [`AGENT_HANDOFF.md`](AGENT_HANDOFF.md) — handoff corrente.
- [`docs/README.md`](docs/README.md) — mappa documentazione.

La precedente specifica v2 è conservata solo come documento superato: [`docs/specs/stagewarden-v2.md`](docs/specs/stagewarden-v2.md).

## Confine dell'implementazione attuale

In questa fase non si implementano feature runtime v3. Non dedurre il contratto v3 dai moduli esistenti: goal loop legacy, router, project handoff, message bus o `DesignRag`.

Piano di migrazione:

1. contratti eventi e stato nodo;
2. validazione dell'albero;
3. scheduler bottom-up seriale;
4. work/result/evidence packet;
5. stream eventi osservabile nel terminale;
6. Node Knowledge Store e indice code-aware;
7. accounting e compattazione per nodo;
8. ownership provider/modello controllata;
9. migrazione legacy e rimozione dei percorsi paralleli/free-message non sicuri.

## Installazione del runtime legacy per ispezione

```bash
python3 -m pip install -e .
```

La CLI installata è il runtime legacy attuale finché non viene chiuso il gate di approvazione v3. Il lavoro futuro deve seguire [`TODO.md`](TODO.md).

## Validazione della fase documentale

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
