# Stagewarden TODO operativo

## Objective
Allineare repository a regole standard Hermes Memory, preservando modifiche già presenti e verificando ogni risultato con evidenza reale.

## Metric and threshold
- Metric: controlli applicabili completati / controlli applicabili identificati.
- Threshold: 100%.

## Scope and assumptions
- Checkout operativo: `/home/public/Stagewarden`, branch `main`.
- Non creare worktree nuovi; non rimuovere worktree esistenti.
- Non alterare o ripristinare modifiche preesistenti non attribuibili a questa attività.
- Non salvare segreti in repository o memoria.
- Interpretare “simulazioni” come capability/demo/agent-runner eseguibili già presenti nel repository; catalogare casi reali, non inventare copertura cosmetica.

## Ordered work
1. [x] Inventory: branch, status, handoff, tests, scripts, CodeGraph availability.
   - Done when: current state and risks recorded.
   - Validation: `git status --short --branch`, file inventory.
2. [x] Define applicable standard controls from Hermes memory and project policy.
   - Depends on: inventory.
   - Done when: controls mapped to concrete files/checks.
   - Validation: checklist below; `AGENT_POLICY.md`, `AGENT_POLICY.json`, and `AGENT_MANIFESTO.md` reviewed.
3. [x] Initialize/update CodeGraph.
   - Depends on: repository inventory.
   - Done when: index exists and is current.
   - Validation: `codegraph status /home/public/Stagewarden`.
4. [x] Keep operational handoff artifacts aligned.
   - Depends on: control mapping and current state.
   - Files: `AGENT_HANDOFF.md`, `HANDOFF.md`, `.stagewarden_handoff.json`.
   - Done when: objective, state, risks, next steps, and validation evidence agree.
   - Validation: JSON parse, handoff cross-check, and `git diff --check`.
   - Result: current handoffs describe prior completed goal-loop work, not this standards-alignment activity; update required before closure.
5. [x] Add or document complete simulation/scenario matrix and reusable runners.
   - Depends on: inventory of existing capabilities and tests.
   - Done when: matrix is source of cases and runners support total plus granular scenario/category execution with observable results.
   - Validation: `./scripts/run_simulation_matrix.py --list`, total, `--scenario executor_write_file`, and `--category role-runtime` all pass; total `29/29`, category `10/10`.
6. [x] Encode applicable global standards in project documentation without secrets.
   - Depends on: control mapping.
   - Done when: project rules cover MVP-first, CodeGraph, TODO, main checkout, scenario matrix/runners, automation, UTF-8, handoff, and wet-run evidence.
   - Validation: `AGENT_MANIFESTO.md`, `AGENT_POLICY.md`, `AGENT_POLICY.json`, and this TODO cover governance/wet-run/traceability; new matrix and runner document scenario coverage.
7. [ ] Run final wet-run test/audit and update all handoff artifacts.
   - Depends on: steps 2–6.
   - Done when: all applicable controls pass or have explicit blocker/exception evidence.
   - Validation: targeted tests, runner commands, CodeGraph status, git status.

## Applicable-control checklist
- [ ] CodeGraph initialized/current before code work.
- [ ] Only main checkout used; existing worktree changes inventoried and preserved.
- [ ] TODO is the single operational plan and updated after each meaningful step/blocker.
- [x] Project documents global standard rules.
- [x] Scenario matrix covers applicable simulations/capabilities.
- [x] Reusable runner supports total and granular scenario/category execution.
- [ ] Handoff files remain aligned.
- [ ] UTF-8/text audit performed; no secrets stored.
- [ ] Wet-run evidence recorded; dry-run never sole closure evidence.

## Evidence log
- Baseline: `TODO.md` absent; CodeGraph initially uninitialized; branch `main`; worktree had 11 mode-only modifications plus `.pi-loop.json.lock`.
- CodeGraph: initialized and indexed 117 files, 3297 nodes, 10693 edges; status current.
- Baseline wet run: `battery --json` in isolated temp workspace returned `ready=true`, `passed=29`, `total=29`, `failed=0`, exit 0. Existing battery has 29 named scenarios but no matrix or granular runner.
- Existing worktree inventory: only main checkout; no additional worktrees. Eleven pre-existing mode-only changes preserved.
- Handoff divergence found: `AGENT_HANDOFF.md`/`HANDOFF.md` target OmniRoute reproducibility while this activity targets standard alignment; `.stagewarden_handoff.json` contains older completed goal-loop state. Must reconcile before closure.

## Blockers / exceptions
- Existing mode-only changes and active `.pi-loop.json.lock` are preserved; do not remove without explicit authorization.
- No implementation started yet beyond CodeGraph initialization and this TODO.
