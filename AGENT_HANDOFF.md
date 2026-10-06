# Agent Handoff

## Current objective
Continue local, safe implementation of optional decision classifier adapters while leaving classic LLM execution unchanged. User asked «continua in autonomia».

## Current state
- Skill selected: `/skill:mvp-first-agent-workflow`; direct analysis, no subagent. Durable HermesVault context read.
- Branch `main`, HEAD `8b32359787fd07fbc3453ae2cda2165286b2fb37`. Modified: `TODO.md`, `HANDOFF.md`, `.stagewarden_handoff.json`, `AGENT_HANDOFF.md`; untracked `.pi-loop.json.lock`.
- Pi shallow clone in gitignored `external_sources/pi-mono`, HEAD `23cf2b948dc626c234f81d6fee7d9978b4c43631`; root MIT license. Pi docs explicitly show `models.getModelOfType("classifier", "typesafe", "jev-latest")`.
- TODO records 7/7 planning rubric outcome, recommendation not to port codemode/skill loader, advisory classifier guardrails, and gated POC steps.
- Added `stagewarden/decision_classifier.py` provider-neutral protocol/result types and explicitly selected API/llama.cpp HTTP adapters. Not wired into orchestrator; no production decisions change.
- Added `tests/test_decision_classifier.py`: `12 passed` under `/tmp/stagewarden-venv` pytest 9.1.1. Local HTTP stub smoke exercised both HTTP adapters (not actual JEV/llama.cpp). Compile and diff checks pass.
- Current machine lacks JEV and llama.cpp. API payload is unverified against TypeSafe; llama.cpp schema/model compatibility awaits user's other PC.
- User explicitly authorizes optional JEV add-on as decision model alongside classic LLM; does not replace or alter classic model/provider/fallback/routing. This permits design/benchmark preparation, not proof of efficiency.
- User states JEV's decision-process efficiency is already demonstrated; treat that as supplied product evidence, not a claim to re-prove. Stagewarden validation should verify faithful integration and no local regressions, while tracking operational latency/cost/escalation.
- Proposed serial cascade JEV→deterministic policy, escalating uncertain/complex items to existing LLM. Keep LLM/provider/fallback/routing unchanged.
- User wants two optional paths: JEV API or model through llama.cpp on another PC. Shared adapter contract implemented; selection is `off|api|llama_cpp`, explicit, with no silent switch. Live remote/local verification deferred.

## Recent changes
- `stagewarden/decision_classifier.py`: isolated backend interface/adapters.
- `tests/test_decision_classifier.py`: 12 passing unit cases.
- `TODO.md`, `AGENT_HANDOFF.md`, `HANDOFF.md`, `.stagewarden_handoff.json`: record state, evidence and limits.

## Important files
- `TODO.md`: active plan and backlog.
- `docs/specs/stagewarden-v3.md`: approved product contract.
- `stagewarden/goal_loop_orchestrator.py`: deterministic gate and current skill prompt loading.
- `stagewarden/extensions.py`: extension discovery; excluded from this task.
- `external_sources/pi-mono/packages/coding-agent/`: gitignored research reference.

## Technical decisions
- Keep classic LLM policy/model intact; JEV optional, serial add-on. Classifier proposal goes through deterministic policy; invalid/error/timeout/low confidence escalates to existing LLM/classic path.
- Do not import Pi codemode/skill loader; no arbitrary script/tool/MCP effects. Preserve serial execution and existing provider/model/routing; quantify any external classifier usage separately.

## Open issues
- This environment has no JEV/llama.cpp installation. API details and llama.cpp model/payload compatibility need verification on the user PC; runtime tests deferred until access is permitted.

## Next steps
1. Keep API payload marked provisional until official TypeSafe contract is checked.
2. On permitted PC, verify llama.cpp endpoint/model/schema and live API contract.
3. Only then consider orchestrator integration; retain opt-in, fail-closed fallback and classic LLM route.

## Commands
```bash
python -m json.tool .stagewarden_handoff.json
python -m compileall -q stagewarden
# pytest unavailable per prior handoff; recheck environment before next test run
```
