# Stagewarden Evolution Roadmap

Last updated: 2026-05-31
Status: proposed roadmap after repository audit and external governance/observability research

## Executive summary

Stagewarden already has strong PRINCE2-oriented controls: brief ambiguity gates, stale-baseline blocking, product-evidence enforcement, RAG-backed context, role runtime views, budget commands, and benchmark surfaces. The next high-value evolution is to make those controls more observable, policy-driven, and auditable so every autonomous step can be traced from business justification to tool evidence and exception handling.

Recommended priority order:

1. Agent Run Ledger and OpenTelemetry-compatible span export.
2. Policy-as-Code governance gates for PRINCE2, NIST AI RMF, and OWASP GenAI risks.
3. Autonomy Budget and tolerance enforcement across tokens, cost, tool calls, filesystem/network surface, and stage time.
4. Command/schema parity hardening for machine-readable automation.
5. Evidence Vault and provenance graph for coding and non-coding artifacts.
6. Agentic security controls for prompt injection, excessive agency, vector weakness, and unbounded consumption.
7. Adaptive stage replanning with explicit change-control packets and dynamic node mutation.

## Research basis

### Internal repository signals

Observed repository state:

- Branch: `main`.
- Latest commit: `84b3e16 stagewarden: gate report plan artifact completions`.
- Latest full-suite reference from handoff: `449 tests OK in 1136.235s` with explicit Hermes env sourcing.
- Command catalog audit: 206 catalog entries and 127 JSON schema registrations.
- Rough schema gap audit found 63 command usages without exact schema coverage. Important examples include `cost`, `stream on/off/status`, many `account ...` commands, `project start --ai`, `role ...` mutation/runtime commands, `resume`, and permission mode commands.
- Handoff state confirms recent completion of evidence gates for coding, design/documentation/specification, and explicit research/report/plan file artifacts.

Key internal gaps:

- Traceability is currently split across handoff entries, runtime records, CLI text, JSON payloads, and test output; there is no single immutable run ledger.
- Governance rules are embedded in Python and prompt text; they are not yet externally reviewable as policy bundles.
- Budget exists but does not yet appear to enforce a complete autonomy envelope over tool calls, model escalation, wall time, risky actions, and stage tolerances.
- Schema parity is incomplete, limiting reliable machine-to-machine use.
- RAG is useful and deterministic, but it needs stronger provenance/security controls around vector and embedding weaknesses.

### External signals mapped to Stagewarden

OpenTelemetry GenAI semantic conventions:

- OpenTelemetry documents GenAI signals for events, exceptions, metrics, model spans, tool execution spans, retrieval spans, and agent spans.
- Mapping implication: Stagewarden can export every project, stage, role tick, model call, tool call, retrieval, evidence gate, and exception as a trace with stable attributes while keeping the local JSON handoff as the source of truth.

Anthropic/Claude Code agent workflow patterns:

- Current agent tooling emphasizes plan-before-editing, resumable sessions, parallel sessions/worktrees, delegated research/subagents, hooks, scoped tools, and custom subagents.
- Mapping implication: Stagewarden’s role tree should evolve toward policy-bounded subagents with explicit worktree/session isolation, scoped tool permissions, and project-level hooks for governance events.

NIST AI Risk Management Framework:

- NIST AI RMF emphasizes trustworthy AI risk management across Govern, Map, Measure, and Manage, with the Generative AI profile focusing on GenAI-specific risks and mitigations.
- Mapping implication: Stagewarden should treat PRINCE2 business case, stage boundaries, quality gates, issue/exception registers, and audit trails as concrete AI RMF controls.

OWASP Top 10 for LLM/GenAI Applications 2025:

- The 2025 list includes Prompt Injection, Sensitive Information Disclosure, Supply Chain, Data and Model Poisoning, Improper Output Handling, Excessive Agency, System Prompt Leakage, Vector and Embedding Weaknesses, Misinformation, and Unbounded Consumption.
- Mapping implication: Stagewarden should add built-in security gates for tool input/output handling, RAG poisoning, prompt leakage, excessive permissions, and cost/token exhaustion.

## Roadmap

### P0. Agent Run Ledger and OpenTelemetry-compatible traces

Problem:
Stagewarden has rich execution evidence but no single normalized, append-only ledger that can be queried or exported as an execution trace.

Feature:
Add `.stagewarden_runs.jsonl` as an append-only local ledger and a `runs` CLI surface.

Initial event types:

- `project.started`, `project.blocked`, `project.finished`
- `stage.started`, `stage.boundary_reviewed`, `stage.exception_raised`
- `role.tick.started`, `role.tick.finished`, `role.message.sent`
- `model.call.started`, `model.call.finished`, `model.call.failed`
- `tool.call.started`, `tool.call.finished`, `tool.call.failed`
- `rag.retrieve`, `rag.index`, `rag.compact`
- `evidence.accepted`, `evidence.rejected`
- `policy.gate.passed`, `policy.gate.blocked`

OpenTelemetry-oriented attributes:

- `gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.model`
- `gen_ai.operation.name`: `agent`, `chat`, `execute_tool`, `retrieve`
- `stagewarden.project_id`, `stagewarden.stage_id`, `stagewarden.step_id`
- `stagewarden.role.node_id`, `stagewarden.role.type`
- `stagewarden.prince2.process`, `stagewarden.prince2.tolerance_status`
- `stagewarden.policy.gate`, `stagewarden.policy.outcome`
- `stagewarden.evidence.kind`, `stagewarden.evidence.ref`

Commands:

- `runs list [limit=N] [--json]`
- `runs show <run_id> [--json]`
- `runs export-otel <path>`
- `runs verify [--json]`

Acceptance criteria:

- A simple agent run records model/tool/evidence/policy events in order.
- Ledger writes are append-only and tolerate partial/corrupt trailing lines.
- `runs export-otel` produces deterministic JSON suitable for an OpenTelemetry collector bridge later.
- Tests validate ledger schema, CLI JSON schema, and correlation IDs.

### P1. Policy-as-Code governance gates

Problem:
Governance controls are correct but scattered across Python matchers and prompt sections. Operators cannot inspect or customize them without editing code.

Feature:
Add a policy bundle layer under `stagewarden/policies/` with YAML first, and optional Rego later.

Initial bundles:

- `prince2_core.yaml`: business justification, stage tolerance, exception escalation, product evidence.
- `nist_ai_rmf.yaml`: Govern/Map/Measure/Manage control mapping.
- `owasp_genai_2025.yaml`: prompt injection, excessive agency, vector weakness, unbounded consumption, output handling.

Commands:

- `policy list [--json]`
- `policy explain <gate> [--json]`
- `policy check <context-file> [--json]`
- `policy trace <run_id> [--json]`

Acceptance criteria:

- Existing evidence gates can emit a policy decision object with `policy_id`, `control_id`, `outcome`, `reason`, and `required_action`.
- Policy files are validated by tests and documentation examples.
- Default behavior stays backward compatible.

### P1. Autonomy Budget and tolerance envelope

Problem:
Stagewarden has budget reporting, but autonomy should also be bounded by tool-call counts, risky-action classes, stage time, retry count, and model escalation.

Feature:
Add a unified autonomy envelope at project, stage, role, and step level.

Controls:

- Max model calls per step/stage.
- Max tool calls per step/stage.
- Max cost/token budget per project/stage/role.
- Max retries after failed gates.
- Max filesystem/network mutation surface.
- Required approval for crossing tolerance bands.

Commands:

- `budget policy [--json]`
- `budget envelope set token=<N> cost=<N> tool_calls=<N> wall_time=<duration>`
- `budget envelope status [--json]`
- `budget envelope clear`

Acceptance criteria:

- `roles tick`, `role tick`, `project start`, and model/tool execution paths block or escalate when tolerance is exceeded.
- Text and JSON payloads identify the exceeded tolerance and required recovery action.
- Wet-run tests simulate cost/tool-call exhaustion without live provider calls.

### P1. Command/schema parity hardening

Problem:
Catalog and schema counts differ materially: 206 command catalog entries vs 127 schema registrations. Rough audit found 63 usages without exact schema coverage.

Feature:
Add a registry parity test and fill high-value schema gaps.

First batch:

- `cost`
- `stream on`, `stream off`, `stream status`
- `resume`
- `project start --ai`
- `role tick`, `role message`, `role assign`, `role remove`, `role tolerance`
- `permission mode`, `permission allow`, `permission ask`
- account mutation commands

Acceptance criteria:

- `tests/test_json_schema_registry.py` includes a parity helper with an explicit allowlist for intentionally text-only commands.
- Every JSON-capable command has a schema name.
- Existing CLI text output remains unchanged.

### P2. Evidence Vault and provenance graph

Problem:
Evidence exists in transcripts and handoffs, but artifact provenance is not yet queryable across files, commands, model calls, and acceptance criteria.

Feature:
Add `.stagewarden_evidence.jsonl` and artifact provenance commands.

Commands:

- `evidence list [artifact=<path>] [--json]`
- `evidence show <evidence_id> [--json]`
- `evidence verify <artifact> [--json]`
- `evidence graph [--json]`

Acceptance criteria:

- Completion gates store evidence IDs rather than only narrative summaries.
- Each evidence record has hash, command/tool source, timestamp, step ID, and acceptance criterion IDs.
- Non-coding artifact gates can verify that a report/plan file exists and was created/updated in the same step.

### P2. Agentic security gates

Problem:
OWASP GenAI 2025 risks map directly to autonomous coding agents.

Feature:
Add default security gates and warnings.

Controls:

- Prompt injection: mark external/web/RAG/tool output as untrusted and require quoting/sanitization in model packets.
- Sensitive information disclosure: redact secrets in ledger, traces, handoffs, and model prompts.
- Supply chain: gate install, dependency, and download operations behind provenance evidence.
- Data/model poisoning: tag RAG entries by trusted/untrusted source and lower confidence for untrusted entries.
- Improper output handling: validate JSON/action outputs against schemas before execution.
- Excessive agency: enforce tool scopes and permission modes per role/stage.
- System prompt leakage: prevent export of privileged prompts by default.
- Vector weakness: expose retrieval diagnostics, source trust, and dedup/conflict checks.
- Misinformation: require evidence-backed claims for status/report artifacts.
- Unbounded consumption: integrate with Autonomy Budget.

Acceptance criteria:

- RAG entries carry source trust and provenance.
- Tool execution gate rejects untrusted instructions from retrieved/web content unless explicitly converted into user-approved requirements.
- Tests cover prompt-injection-shaped retrieved content and sensitive value redaction.

### P2. Adaptive replanning and dynamic node mutation

Problem:
The desired functional model is dynamic: user changes can invalidate work, nodes can create/delete subnodes, stages can be replanned, and ambiguity must stop execution rather than trigger assumptions.

Feature:
Implement change-control packets and replanning gates.

Flow:

1. Detect new/changed requirement.
2. Diff against approved brief and current stage plan.
3. Mark affected baselines/stages/products stale.
4. Ask clarification for any ambiguous change.
5. Rebuild affected role-tree/stage/microtask scope only.
6. Require approval if tolerances/business case are impacted.

Commands:

- `change propose <summary> [--json]`
- `change impact [--json]`
- `change approve [--json]`
- `change reject [--json]`
- `roles rebalance [--json]`

Acceptance criteria:

- No runtime/tick path advances from an ambiguous or unapproved change packet.
- Node creation/deletion/reparenting is auditable and reflected in runtime views.
- Existing stale-baseline gates are reused rather than duplicated.

### P3. PRINCE2/NIST/OWASP control dashboard

Problem:
Operators need a concise board view that connects delivery status with risk controls.

Feature:
Add a dashboard that groups controls by PRINCE2 process, NIST function, and OWASP risk.

Commands:

- `governance dashboard [--json]`
- `governance controls [framework=prince2|nist|owasp] [--json]`
- `governance exceptions [--json]`

Acceptance criteria:

- Dashboard shows pass/block/warn status for each framework dimension.
- Exceptions include evidence links and recovery actions.
- JSON schema is registered.

## Suggested first implementation slice

Start with P0 Agent Run Ledger because it supports all later work and can be implemented narrowly without changing existing behavior.

TDD plan:

1. RED: add a ledger unit test proving a tool/evidence/policy event can be appended and loaded with correlation IDs.
2. GREEN: implement `stagewarden/run_ledger.py` with append/load/verify helpers.
3. RED: add CLI JSON tests for `runs list` and `runs show`.
4. GREEN: route read-only `runs` commands and register schemas.
5. RED: add executor integration test proving a completion-gate rejection records `policy.gate.blocked` and `evidence.rejected`.
6. GREEN: insert ledger writes in the narrow evidence-gate path only.
7. Validate focused suites: `tests.test_executor`, `tests.test_json_schema_registry`, and targeted trace CLI tests.
8. Run full discovery if executor/runtime behavior changes broadly.

## Risks and mitigations

- Risk: Ledger creates noisy or unstable outputs.
  - Mitigation: append stable event types first; keep volatile token/cost fields optional.
- Risk: Policy-as-code duplicates Python logic.
  - Mitigation: start by emitting policy IDs from existing gates, then migrate evaluation gradually.
- Risk: Autonomy budget blocks legitimate work.
  - Mitigation: warning mode first, then explicit blocking thresholds.
- Risk: Command/schema parity creates churn.
  - Mitigation: add an intentional text-only allowlist and fill schemas by command family.
- Risk: Security gates over-block research/RAG context.
  - Mitigation: mark trust/provenance and require explicit promotion from untrusted data to approved requirement.

## Source references

- OpenTelemetry Semantic Conventions for Generative AI Systems, including model/tool/retrieval/agent spans: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- OpenTelemetry GenAI spans: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/
- Anthropic Claude Code common workflows: https://docs.anthropic.com/en/docs/claude-code/common-workflows
- Anthropic Claude Code subagents: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
- NIST Generative AI Profile referenced by NIST AI RMF page: NIST-AI-600-1
- OWASP Top 10 for LLM/GenAI Applications 2025: https://genai.owasp.org/llm-top-10/
