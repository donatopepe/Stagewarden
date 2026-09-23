# Stagewarden documentation

## Canonical documents

- [`specs/stagewarden-v3.md`](specs/stagewarden-v3.md) — canonical node-first product specification, pending user approval.
- [`architecture.md`](architecture.md) — target architecture and trust boundaries.
- [`../TODO.md`](../TODO.md) — only plan and backlog.
- [`../AGENT_MANIFESTO.md`](../AGENT_MANIFESTO.md) — operating principles.
- [`../AGENT_POLICY.md`](../AGENT_POLICY.md) — policy contract.
- [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md) — current work state.

## Reference and evidence documents

- [`source_references.md`](source_references.md) — external research sources, not implementation authority.
- [`status_research.md`](status_research.md) — behavioral research and design input.
- [`external_io_help_audit.md`](external_io_help_audit.md) — legacy external-IO wet-run evidence.
- [`kilocode_provider_coverage.md`](kilocode_provider_coverage.md) — generated provider coverage reference.
- [`../docs_ljson.md`](../docs_ljson.md) — LJSON utility reference.

Reference documents cannot override the v3 specification or TODO. Generated data remains authoritative only for the command that generated it and must carry source/freshness information.

## Documentation rules

- Do not create another backlog or roadmap with executable tasks.
- Do not describe legacy behavior as v3 behavior.
- Use `tree_id`, `node_id`, `parent_node_id`, `purpose`, `work_id`, `event_id`, `context_budget`, `provider`, `model`, and `evidence` consistently.
- Mark proposals, legacy behavior, generated reports, and verified runtime facts separately.
- Never include secrets, tokens, private session content, or credentials.
- Validate Markdown as UTF-8 without BOM and run `git diff --check`.
