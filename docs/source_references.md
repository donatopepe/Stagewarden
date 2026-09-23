# Source references

This document lists external material used as behavioral research. It is not a product specification, not an authorization source, and not a license to copy implementation.

## References

| Project | Local path | Upstream | Design use |
|---|---|---|---|
| Caveman | `external_sources/caveman` | `https://github.com/JuliusBrussee/caveman` | compression, commands, skills, packaging |
| OpenAI Codex CLI | `external_sources/codex` | `https://github.com/openai/codex` | status, approvals, sandbox, usage, protocol |
| Claude Code | `external_sources/claude-code` | `https://github.com/anthropics/claude-code` | CLI behavior and auth surfaces |
| KiloCode | `external_sources/kilocode` | `https://github.com/Kilo-Org/kilocode` | provider/model registry and runtime layering |
| Pi Agent extensions | `/root/.pi/agent/extensions` | installed local reference | auto-compaction, dynamic catalog, subagent behavior |

## Rules

- Verify upstream license before copying code.
- Prefer behavioral notes and independent implementation.
- Never store credentials or private sessions in this repository.
- Provider/model catalogs are observations with source and timestamp, not permission to select a provider.
- Pi TypeScript extensions are not directly executable as Python runtime components; port through an explicit Stagewarden contract.

## Canonical design

The node-first design, including bottom-up scheduling, packet forwarding, Node Knowledge Store, code-aware index, terminal observability, context accounting and compaction, is defined only in [`specs/stagewarden-v3.md`](specs/stagewarden-v3.md).
