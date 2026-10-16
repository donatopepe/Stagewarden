# Loop prompt canonico — `stagewarden-mvp-continue`

Task durevole `.pi-loop.json`, id ricreato 2026-10-16 dopo blackout che ha svuotato `tasks`
(il precedente `c05d5335` è recuperato dalla storia git di `.pi-loop.json`).
Questo file è la copia versionata e verificabile del prompt: se il loop sparisce di nuovo,
il testo si recupera da qui o da `git log -p -- .pi-loop.json` senza chat history.

## Prompt (testo esatto passato a `cron_create`)

Continue Stagewarden MVP work automatically in one bounded iteration. Recover state first: read AGENTS.md, AGENT_HANDOFF.md, HANDOFF.md, TODO.md and the canonical Hermes memory when available; verify the main worktree, CodeGraph currency and that the durable loop task exists in .pi-loop.json (re-arm it from .pi/prompts/stagewarden-mvp-continue-loop.md if missing). Then work only from TODO.md and AGENT_HANDOFF.md Next steps: node-scoped context, provider/model-aware token budgeting, automatic bounded compaction, restricted read/append codemode; the decision model must be called generically, never as a hard-coded provider/model name. Preserve routing/provider/fallback/policy and v3 serial execution. Use the main worktree only; no secrets; no new worktree. Before editing define one objective, one metric plus threshold, the fixed test cases and the baseline; make the smallest TDD change; run targeted wet tests; update TODO.md, AGENT_HANDOFF.md, HANDOFF.md and .stagewarden_handoff.json with evidence. Remote-model tests must select explicitly free routes and fail closed otherwise. Stop and record the blocker on repeated external OmniRoute malformed output, missing environment, failing tests or a user decision gate. Do not enable legacy parallel execution or silently change provider/model.

## Vincoli permanenti

- Nessun test a pagamento: route/modelli `:free` espliciti, fail-closed.
- Nessun worktree nuovo, nessun segreto nei file di handoff o in memoria condivisa.
- Un solo item bounded per iterazione; se nessun item runtime è selezionabile, registrare
  "no new runtime item selected" e fermarsi invece di generare hardening marginale.
- Gate decisionale utente: fermarsi e registrare, non decidere da soli.
