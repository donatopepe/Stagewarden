# Stagewarden Agent Manifesto

## Principio centrale

Stagewarden governa lavoro attraverso un albero di nodi. L'albero rende visibili scopo, responsabilità, contesto, evidenza e stato.

## Regole non negoziabili

- Pianifica top-down; esegui bottom-up.
- Esegui una leaf alla volta per default.
- Un parent inoltra lavoro solo con `WorkPacket` esplicito.
- Un child ritorna solo `ResultPacket`/`EvidencePacket` verificabili.
- Blocca comunicazione laterale, scope implicito e completion senza evidence.
- Ricorda sempre all'utente quale nodo lavora e perché.
- Persisti eventi, contesto e decisioni per nodo.
- Usa Node Knowledge Store per storia, retrieval e code-aware map.
- Tratta CodeGraph come ausilio, non come memoria operativa completa.
- Compatta automaticamente il context del nodo prima del limite provider/modello.
- Mostra provider, modello, account, budget, compaction, tool e test.
- Lascia selezione provider/modello, credenziali, costi e fallback all'utente.
- Applica permessi, scope, idempotenza e wet-run evidence.
- Riduci cerimonia per task piccoli, mai controllo essenziale.
- Non dichiarare completato un nodo senza risultato verificato.

## Obiettivo UX

L'utente deve poter rispondere in qualsiasi momento:

1. quale nodo sta lavorando;
2. qual è il suo scopo;
3. quale lavoro ha ricevuto;
4. cosa sta facendo ora;
5. quali file/tool/test sta usando;
6. quanto contesto resta;
7. quale evidenza ha prodotto;
8. perché attende, è bloccato o ha delegato.

## Riferimenti

- Specifica: `docs/specs/stagewarden-v3.md`
- Architettura: `docs/architecture.md`
- Piano unico: `TODO.md`
