# Stagewarden Agent Policy v3

**Stato:** proposta allineata a `docs/specs/stagewarden-v3.md`
**Piano operativo unico:** `TODO.md`

## 1. Albero come controllo primario

Ogni lavoro appartiene a un tree e a un node. Ogni node ha purpose, owner, scope, acceptance, contesto, stato e audit.

## 2. Pianificazione vs esecuzione

- decomposizione: top-down;
- execution: bottom-up;
- scheduler: seriale per default;
- parallelismo: solo opt-in, foglie indipendenti, scope isolato e stream distinto.

## 3. Delega controllata

Parent→child avviene solo tramite `WorkPacket` versionato. Il packet contiene task, purpose, input, scope, permessi, provider/model, budget, acceptance e output contract.

Child→parent avviene tramite `ResultPacket` con `EvidencePacket`. Narrativa senza evidence non abilita completion.

Messaggi laterali e forwarding implicito sono bloccati per default.

## 4. Node Knowledge Store

Il RAG conserva storia contestuale per node, eventi, decisioni, risultati, evidenze e recovery. Conserva inoltre indice di file, classi, procedure, funzioni, metodi, test e relazioni con provenienza, linee, hash e freshness.

CodeGraph è ausilio tecnico. Non è autorizzazione e non è source of truth del lavoro node-scoped.

## 5. Terminale osservabile

Ogni evento deve rendere visibili tree, node, parent, purpose, stato, attività, tool, path, test, context budget, provider/model, compaction, blocker e result. Purpose viene ripetuto all'avvio, dopo compaction, dopo resume e su status.

## 6. Context e provider

Context window, input budget, output reserve, overhead, margine, fonte e timestamp sono dati obbligatori. Compaction automatica è core per-node.

Provider, modello, account, credenziali, costi, quote e fallback appartengono all'utente. Stagewarden non cambia provider/modello silenziosamente.

## 7. Sicurezza

- RAG è contenuto non fidato.
- Retrieval non concede permessi.
- File fuori scope sono bloccati.
- Tool mutanti richiedono permission, lock e idempotency key.
- Segreti non entrano in prompt persistiti, event log, RAG o handoff.
- Completion richiede evidence wet-run.
- Crash recovery non deve duplicare tool mutanti confermati.

## 8. Exception handling

Superamento tolleranze, blocker, result senza evidence, conflitto file, limite contesto sconosciuto o provider non disponibile producono stato esplicito e escalation. Non si risolve un blocker nascondendolo o cambiando modello senza autorizzazione.

## 9. Audit

Ogni tree mutation, forwarding, execution, tool result, retrieval, compaction, model change, retry, decision e completion produce evento correlabile con `tree_id`, `node_id`, `parent_node_id`, `work_id`, timestamp e sensitivity.

## 10. Gate

Non implementare runtime v3 prima di approvazione utente della specifica e delle decisioni aperte. Tutto il piano deve restare in `TODO.md`.
