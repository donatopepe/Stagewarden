---
description: End-to-end execution prompt for the full goal loop using the other templates
argument-hint: "<task>"
---
# Goal Loop Execution Prompt

Usa questo prompt quando vuoi avviare il loop principale.

Istruzioni:
- leggi prima il task
- usa goal-root per definire scopo e confini
- usa goal-loop-orchestrator per costruire il grafo
- usa subnode-generator per creare i prompt dei figli
- usa autonomy-decision per decidere se chiedere all’utente o agire autonomamente
- usa tolerance-exception per tutte le deviazioni
- usa validation-wet-run per ogni cambiamento non banale
- usa node-communication per i messaggi tra nodi
- usa pi-learning-benchmark per aggiornare le basi di apprendimento

Obiettivo finale:
portare il sistema alla massima potenza utile, con controllo del loop, rifattorizzazione completa, test reali, e gestione rigorosa delle eccezioni.

Output richiesto:
1. scope
2. node graph
3. child prompts
4. execution plan
5. validation plan
6. exception policy
7. final report