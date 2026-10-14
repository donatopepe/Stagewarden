# Agent Handoff

## Current objective
Completa contesto isolato per nodo, token budget da profilo provider/modello, compattazione automatica e context codemode ristretto. Preservare routing/provider/fallback/policy e serialità v3.

## Current state
- `GoalLoopOrchestrator` mantiene per nodo contesto e revision, calcola input budget da catalogo + riserva output/margine, compacta testo eccedente e include contesto node UUID-scoped nei prompt/WorkPacket. Context append salvato nel node knowledge con revision e hash in event stream.
- Markdown memory supporta ora limite token solo se caller fornisce token counter esatto; senza contatore fallisce chiuso. Nessun tokenizer reale agganciato ancora.
- Upstream studiati a livello iniziale: Pi compaction pure functions/session layer e codemode tool dinamico; Codex auto_compact window/threshold e contesto task; Claude Code checkout pubblico ispezionato. Nessun codice copiato. Refs/licenze in TODO.
- Test mirati `94 passed, 26 subtests` (ri-eseguiti dopo persistenza append); suite Stagewarden prima della persistenza `743 passed, 5 skipped, 301 subtests` (escluso `external_sources`, raccolta impropria Codex). Compileall/JSON/diff check da ripetere dopo ultimo change.
- Tree state aggiornato in HEAD `bbae713`; pytest temporaneo `/tmp/stagewarden-test-venv`.

## Recent changes
- `stagewarden/goal_loop_orchestrator.py`: token budget, compaction, persistence/context API scoped per nodo.
- `stagewarden/memory_context.py`: token-aware bounded loading con contatore esplicito.
- `tests/test_goal_loop_orchestrator.py`, `tests/test_memory_context.py`: isolamento/overflow/codemode.
- `TODO.md`, `HANDOFF.md`, `.stagewarden_handoff.json`: aggiornare a fine ogni blocco.

## Important files
- `stagewarden/goal_loop_orchestrator.py`: node prompts, budget, compaction, codemode.
- `stagewarden/memory_context.py`: configured Markdown memory and token-bound loader.
- `stagewarden/model_catalog.py`: per-provider/model context limits.
- `stagewarden/node_knowledge.py`: persistent node-keyed store.
- `TODO.md`: source refs, roadmap, acceptance/risk.

## Technical decisions
- Safe token accounting must use caller-supplied tokenizer; no char/token ratio represented as exact. Goal-loop uses conservative 3 chars/token estimator until actual provider tokenizer arrives; hard prompt instruction overflow raises before model invocation.
- Compact context owned by NodeState UUID; code-mode offers read/append only and no eval/shell/tool calls. Context remains untrusted prompt data.
- Budget source currently catalog model limits plus env input/output overrides, reserves and margin. Unknown provider limits stay unknown; fallback cap is conservative character estimation.

## Open issues
- 3-char/token goal-loop estimate is conservative heuristic, not tokenizer guarantee; wire provider tokenizer or true preflight API; validate tool/schema/system prompt overhead across backend adapters.
- `memory_context` token compaction wired only as reusable API, not model caller; summary compaction currently truncation/head-tail, not semantic/loss-aware summary.
- Ensure custom node prompts, assigned skill content and output cap are budgeted uniformly (current final execution compaction is broad string truncation; risk essential instruction loss).
- Context codemode currently in-process method, not separately exposed to model; persist/reconstruct context robustly across re-instantiation and test wet runtime/model contract.
- Source clones ignored by Git; refresh refs and inspect Claude Code license before any reuse.

## Next steps
1. Replace broad prompt truncation with required-section-aware assembly and add custom-node/skills overflow tests.
2. Integrate actual backend tokenizer/capacity if available; else require explicit model config and keep fail-closed.
3. Persist node context to knowledge store at append/revision and restore after restart.
4. Expose only read/append via explicit serial codemode action contract, then wet-run mock/backend and full regression.

## Commands
```bash
python -m compileall -q stagewarden tests
/tmp/stagewarden-test-venv/bin/python -m pytest --ignore=external_sources -q
python -m json.tool .stagewarden_handoff.json
```
