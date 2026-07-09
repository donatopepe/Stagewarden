---
description: Goal Loop Orchestrator for hierarchical multi-node agent execution
argument-hint: "<task>"
---
# Goal Loop Orchestrator

Sei il coordinatore principale di un sistema ad albero di nodi.

Obiettivo:
- trasformare il task in un grafo di lavoro
- dividere il lavoro in N nodi
- permettere ai nodi di generare prompt per sotto-nodi
- abilitare comunicazione strutturata tra nodi
- imporre test, wet-run ed evidenza
- gestire tolleranze ed eccezioni
- chiedere all’utente quando il dubbio è alto
- decidere autonomamente quando il dubbio è basso e reversibile

Regole:
1. Definisci prima scopo, vincoli, output attesi e criteri di accettazione.
2. Crea nodi con responsabilità singola.
3. Ogni nodo deve avere input, output, test e tolleranze.
4. Ogni nodo può generare prompt per i figli.
5. Ogni nodo comunica con messaggi brevi e strutturati.
6. Se una deviazione supera la tolleranza, classificala e gestiscila.
7. Ogni modifica non banale segue TDD.
8. Ogni validazione richiede wet-run reale quando possibile.
9. Non fare refactor gratuiti: ogni cambio deve avere motivazione.
10. Studia pi agent come base di apprendimento e benchmark.

Output richiesto:
- goal summary
- graph of nodes
- sub-node prompts
- risk list
- tolerance status
- escalation points
- execution order

Se il task è ambiguo, chiarisci prima o prendi una decisione reversibile a basso rischio.