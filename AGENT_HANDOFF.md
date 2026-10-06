# Agent Handoff

## Current objective
Integrate optional Jev decision support using working Pi extension documented in Obsidian; preserve classic LLM path, deterministic policy and v3 seriality.

## Current state
- User requested «implementa, guarda memoria obsidian ... estensione pi agent funzionante» and «continua in autonomia».
- Obsidian details read: Pi extension implements TypeSafe System One API (`https://api.typesafe.ai/v1/systemone`, `TYPESAFE_API_KEY`, `{model,state,questions}` typed choice/probabilities) and local JevStyle-v3 llama.cpp `/v1/completions` verdict slots (`logprobs:10`, `logit(yes)-logit(no)`, softmax T=0.8279). Source: `Memory/Backups/pi-local-decision-model/jev-decide-extension.ts`, `Memory/Modelli-IA-locali/jev-decision-model.md`, and pinned Pi repo tests.
- `stagewarden/decision_classifier.py` implements API/local protocols. `goal_loop_orchestrator._autonomy_gate` invokes only when `STAGEWARDEN_DECISION_BACKEND=api|llama_cpp`; default off. Classifier may raise caution/block, never lower deterministic caution or authorize. Errors fail to deterministic policy. Evidence logged and added to node capsule.
- Targeted tests: `72 passed, 16 subtests`. Full suite: `738 passed, 5 skipped, 301 subtests`. Local HTTP stub smoke passed; does not prove real TypeSafe or GGUF compatibility. `compileall`, JSON parse, `git diff --check` pass.
- No changes to classic LLM, provider/fallback/routing, scheduler or serial execution. This host lacks live JEV/GGUF; real test awaits configured Mac.

## Recent changes
- `stagewarden/decision_classifier.py`: TypeSafe System One and JevStyle-v3 adapters.
- `stagewarden/goal_loop_orchestrator.py`: opt-in advisory autonomy-gate integration.
- `tests/test_decision_classifier.py`, `tests/test_goal_loop_orchestrator.py`: protocol/security/safety coverage.
- `TODO.md`, `HANDOFF.md`, `.stagewarden_handoff.json`: synchronized.

## Important files
- `TODO.md`: scope, evidence, limits and next steps.
- `stagewarden/decision_classifier.py`: backend contract and adapters.
- `stagewarden/goal_loop_orchestrator.py`: deterministic autonomy gate.
- `external_sources/pi-mono/packages/ai/test/typesafe-system-one.test.ts`: upstream TypeSafe wire contract.

## Technical decisions
- Decision model remains optional advisor, not replacement for LLM. Default backend off.
- Deterministic policy is authoritative; JEV can only elevate caution; errors fall back to deterministic policy.
- `api` and `llama_cpp` selected explicitly; no silent switching. Remote HTTP denied; remote llama.cpp requires HTTPS + API key.
- Pi extension patterns adopted; no arbitrary codemode, tool/MCP exposure or model-routing change.

## Open issues
- No live API or JevStyle GGUF available here; actual Mac wet-run pending.
- Goal loop calls classifier at each autonomy gate when opted in; assess whether selective invocation is desired before routine enablement.

## Next steps
1. On configured Mac, run one real API and/or llama.cpp test; verify logs, schema and latency.
2. Review invocation frequency/cost; retain opt-in and serial call.
3. Keep runtime fallback/classic LLM unchanged; update evidence after wet run.

## Commands
```bash
python -m json.tool .stagewarden_handoff.json
python -m compileall -q stagewarden tests
/tmp/stagewarden-venv/bin/python -m pytest -q
```
