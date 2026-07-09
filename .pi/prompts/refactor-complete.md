---
description: Full refactoring plan with safety, modularity, and non-regression tests
argument-hint: "<codebase-or-module>"
---
# Full Refactoring

Obiettivo:
rifattorizzare completamente il modulo o la base indicata senza perdere comportamento utile.

Metodo:
1. identifica i blocchi più complessi
2. separa responsabilità
3. riduci coupling
4. estrai funzioni o moduli solo se utile
5. preserva semantica e compatibilità dove possibile
6. crea o aggiorna test di non regressione
7. esegui wet-run reale

Vincoli:
- niente refactor gratuiti
- ogni modifica deve essere motivata
- ogni cambiamento deve avere test
- se la modifica impatta protocollo, API o governance, segnala eccezione

Deliverable:
- before/after
- lista cambiamenti
- impatto architetturale
- test aggiunti/aggiornati
- evidenza di esecuzione