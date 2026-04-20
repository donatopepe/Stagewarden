# Source References

Stagewarden keeps third-party agent sources as local research material under
`external_sources/`. That directory is intentionally ignored by Git so the
project does not vendor or republish upstream code.

## Local Clones

| Project | Local path | Upstream | Purpose | License/source note |
| --- | --- | --- | --- | --- |
| Caveman | `external_sources/caveman` | `https://github.com/JuliusBrussee/caveman` | Study token-compression skills, commands, hooks, and plugin packaging. | Public GitHub repository. Check upstream license before copying implementation. |
| OpenAI Codex CLI | `external_sources/codex` | `https://github.com/openai/codex` | Study CLI agent loop, status card, login flow, approvals, sandbox, model metadata, token usage, and rate-limit handling. | Apache-2.0 according to npm metadata for `@openai/codex`. |
| Claude Code | `external_sources/claude-code` | `https://github.com/anthropics/claude-code` | Study official Claude Code CLI behavior if public source is available. | NPM metadata points to this homepage; if unavailable, use only official npm package/bundle metadata, not leaked mirrors. |

## Update Commands

```sh
git -C external_sources/caveman pull --ff-only
git -C external_sources/codex pull --ff-only
git -C external_sources/claude-code pull --ff-only
```

If a repository is not available, keep the directory absent and document the
reason in `HANDOFF.md`.

## Copying Rule

Do not copy code verbatim into Stagewarden unless the upstream license permits
it and attribution is added. Prefer reimplementing behavior from observed
interfaces and documented concepts.
