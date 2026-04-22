# Stagewarden

Autore: Donato Pepe
Licenza: MIT

Stagewarden e un agente CLI per coding controllato: loop stile Codex, routing multi-provider, governance PRINCE2, handoff persistente, strumenti shell/file/git e tracciamento verificabile.

## Installazione

```bash
python3 -m pip install -e .
```

Prerequisiti:

- Python 3.11+
- Git installato e disponibile in `PATH`

Git e obbligatorio. Se la workspace non ha `.git`, Stagewarden inizializza il repository e crea snapshot locali delle azioni dell'agente.

## Avvio

```bash
stagewarden
```

Oppure:

```bash
stagewarden "fix failing tests"
```

Nella shell interattiva i comandi iniziano con `/`. Tutto cio che non inizia con `/` viene trattato come richiesta/task per l'agente.

## UX Stile Codex/Claude

Stagewarden usa Codex CLI e Claude Code come baseline di esperienza utente:

- `/help` mostra le categorie principali.
- `/slash [prefisso]` mostra una palette comandi con descrizioni.
- `/slash mo` mostra i comandi relativi ai modelli.
- `stagewarden "slash mo" --json` espone la stessa palette in formato strutturato.
- Il completamento slash suggerisce provider, ruoli PRINCE2, backend shell, account configurati, provider-model e valori `reasoning_effort`.
- La palette mostra anche contesto operativo: provider abilitati, account attivi, provider bloccati e hint sui parametri.

Esempi:

```text
stagewarden> /slash
stagewarden> /slash mo
stagewarden> /model choose
stagewarden> /model choose chatgpt
stagewarden> /model preset chatgpt
stagewarden> /role configure project_manager
stagewarden> /status
stagewarden> /resume context
```

## Modelli E Provider

Comandi principali:

- `/models` mostra provider abilitati, attivi, preferiti e provider-model correnti.
- `/model choose [provider]` apre un menu guidato per provider, provider-model e parametri.
- `/model preset <provider>` senza preset apre il picker guidato.
- `/model list <provider>` mostra catalogo provider-model e parametri supportati.
- `/model variant <provider> <provider_model>` fissa un modello del provider.
- `/model param set <provider> reasoning_effort <low|medium|high>` salva il livello di ragionamento quando supportato.
- `/model limits` mostra blocchi, reset time e limiti conosciuti.

I menu guidati mostrano il contesto corrente prima della scelta: provider abilitati, provider preferito, account attivi, provider bloccati, provider-model corrente, reasoning effort corrente e account configurati.

## PRINCE2 E Handoff

Stagewarden tratta l'handoff come contesto vivo del progetto, non come semplice resume opzionale.

- `.stagewarden_handoff.json` contiene lo stato operativo.
- `HANDOFF.md` contiene roadmap e decisioni umane.
- `/handoff` mostra il contesto persistente.
- `/resume --show` mostra il target di resume.
- `/resume context` mostra ultimo tentativo modello, route, evidenza tool e snapshot git.
- `/roles domains` mostra responsabilita e perimetro dei ruoli.
- `/role configure [role]` mostra responsabilita PRINCE2 e scope del ruolo prima di assegnare provider/modello/account.
- `/roles tree approve` salva l'albero PRINCE2 corrente come baseline approvata in `.stagewarden_models.json` e `.stagewarden_handoff.json`.
- `/roles baseline` mostra la baseline approvata che guidera i futuri handoff di contesto per ruolo.
- `/role add-child` apre un menu guidato, oppure `/role add-child <parent_node> <role_type> [node_id]` aggiunge nodi PRINCE2 delegati/subordinati alla baseline approvata.
- `/role assign` apre un menu guidato, oppure `/role assign <node_id> <provider> <provider_model> [reasoning_effort=<valore>] [account=<nome>] [pool=<primary|reviewer|fallback>]` assegna rotte primary, reviewer o fallback a un nodo specifico dell'albero.

Il contesto passato ai modelli e limitato al dominio del ruolo PRINCE2 assegnato.

## Validazione

Regole operative:

- ogni modifica deve avere test o verifica reale
- dry-run da solo non e checkpoint valido
- serve wet-run: test eseguiti, comandi reali, file osservati o output reale di tool
- se un wet-run diretto non e possibile, Stagewarden deve trovare una verifica alternativa concreta

## Comandi Utili

```text
stagewarden> /doctor
stagewarden> /preflight
stagewarden> /health
stagewarden> /report
stagewarden> /transcript
stagewarden> /git status
stagewarden> /sources status
```

Per output JSON:

```bash
stagewarden status --json
stagewarden "slash mo" --json
stagewarden "model limits" --json
stagewarden "roles matrix" --json
stagewarden "resume context" --json
```

## Crediti

Stagewarden studia e riproduce, dove compatibile, pattern UX e architetturali ispirati a Codex CLI, Claude Code e Caveman. Le fonti locali servono come riferimento tecnico; non vengono vendorizzati contenuti protetti nel progetto.
