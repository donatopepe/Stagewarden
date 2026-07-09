---
description: Decide autonomously or ask the user based on risk and reversibility
argument-hint: "<decision-point>"
---
# Autonomy vs User Question

Usa questa policy:

1. Basso impatto, reversibile, locale -> decidi autonomamente.
2. Impatto medio ma con una scelta chiaramente migliore -> decidi autonomamente e spiega.
3. Impatto su architettura, sicurezza, compatibilità, dati, test fondamentali, o bassa reversibilità -> chiedi all’utente.
4. Ambiguità critica che blocca il corretto funzionamento -> ferma il loop e segnala eccezione.

Regola generale:
preferisci autonomia informata quando il rischio è basso; preferisci domanda all’utente quando il rischio è alto.