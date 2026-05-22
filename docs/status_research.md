# Status Research: Codex CLI, Claude Code, and KiloCode

This document records implementation lessons from the local official references
in `external_sources/` and from installed official CLI packages. It is a
behavioral study, not copied source.

## Sources Studied

Codex:

- `external_sources/codex/codex-rs/tui/src/status/card.rs`
- `external_sources/codex/codex-rs/tui/src/status/rate_limits.rs`
- `external_sources/codex/codex-rs/tui/src/status/helpers.rs`
- `external_sources/codex/codex-rs/tui/src/status/format.rs`
- `external_sources/codex/codex-rs/cli/src/login.rs`
- `external_sources/codex/codex-rs/app-server/src/codex_message_processor.rs`
- `external_sources/codex/codex-rs/app-server-protocol/schema/typescript/*`

Claude Code:

- `external_sources/claude-code/README.md`
- `external_sources/claude-code/CHANGELOG.md`
- official installed package bundle at
  `/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/cli.js`
- runtime command `claude auth status --json`

KiloCode:

- `external_sources/kilocode/AGENTS.md`
- `external_sources/kilocode/packages/opencode/src/provider/models.ts`
- `external_sources/kilocode/packages/opencode/src/session/system.ts`
- `external_sources/kilocode/packages/opencode/src/acp/agent.ts`
- `external_sources/kilocode/packages/kilo-gateway/src/api/models.ts`
- `external_sources/kilocode/packages/kilo-vscode/src/KiloProvider.ts`
- `external_sources/kilocode/packages/kilo-vscode/src/kilo-provider/model-state.ts`
- `external_sources/kilocode/packages/kilo-vscode/src/kilo-provider/handlers/auth.ts`
- `docs/kilocode_provider_coverage.md`
- `data/kilocode_provider_coverage.json`

## Codex Status Model

Codex has two status surfaces:

- `codex login status`: a small auth check. It returns success when API key or
  ChatGPT credentials exist, failure when not logged in.
- TUI `/status`: a full operational status card.

The `/status` card is composed from structured runtime state, not from ad hoc
strings. The display includes:

- CLI identity and version.
- Link to ChatGPT Codex usage settings for authoritative limit data.
- Model name plus model details, including reasoning effort and reasoning
  summary mode for Responses API models.
- Model provider when it is not the default OpenAI provider.
- Working directory, path-shortened for terminal width.
- Permission profile, mapped to user labels such as `Default`, `Full Access`,
  or `Custom (<sandbox>, <approval>)`.
- Agents summary for `Agents.md`/agent instruction files.
- Account display: ChatGPT email/plan when available, or API-key mode.
- Thread name, session ID, fork source, and collaboration mode when available.
- Token usage: compact total, non-cached input, output.
- Context window: percent remaining, tokens used, model context size.
- Rate limits: 5h/weekly windows, credits, stale/missing/unavailable states.

Important behavior:

- Token usage is hidden for ChatGPT subscribers in the TUI card.
- Rate-limit data is stale after 15 minutes.
- Missing limits show a different message depending on whether refresh is in
  progress.
- Progress bars display percent remaining, not percent used.
- Reset timestamps are localized and shortened: same-day values render as time;
  future days include date.
- Base URLs are sanitized before display by removing username, password, query,
  and fragment.
- Field labels are width-aligned and output is truncated/wrapped to terminal
  width.

## Codex Data Shapes To Mirror

Auth:

```text
GetAuthStatusParams:
- includeToken: bool | null
- refreshToken: bool | null

GetAuthStatusResponse:
- authMethod: "apikey" | "chatgpt" | "chatgptAuthTokens" | null
- authToken: string | null
- requiresOpenaiAuth: bool | null
```

Rate limits:

```text
RateLimitSnapshot:
- limitId
- limitName
- primary: RateLimitWindow | null
- secondary: RateLimitWindow | null
- credits: CreditsSnapshot | null
- planType
- rateLimitReachedType

RateLimitWindow:
- usedPercent
- windowDurationMins
- resetsAt

CreditsSnapshot:
- hasCredits
- unlimited
- balance

RateLimitReachedType:
- rate_limit_reached
- workspace_owner_credits_depleted
- workspace_member_credits_depleted
- workspace_owner_usage_limit_reached
- workspace_member_usage_limit_reached
```

Token usage:

```text
ThreadTokenUsage:
- total: TokenUsageBreakdown
- last: TokenUsageBreakdown
- modelContextWindow

TokenUsageBreakdown:
- totalTokens
- inputTokens
- cachedInputTokens
- outputTokens
- reasoningOutputTokens
```

## Claude Code Status Model

The public Claude Code repo does not expose the full CLI implementation. It does
document behavior through README/changelog and plugin examples. The official npm
package exposes a minified bundle that is useful for interface discovery.

Runtime auth status:

```sh
claude auth status --json
```

Observed output when not logged in:

```json
{
  "loggedIn": false,
  "authMethod": "none",
  "apiProvider": "firstParty"
}
```

Claude's status system is split across:

- `claude auth status`: machine-readable auth status.
- Status line JSON input: extensible data consumed by user scripts.
- SDK/headless stream events such as `rate_limit_event` and `auth_status`.
- Changelog-documented `/context`, `/stats`, transcript, and statusline
  behavior.

Claude Code statusline data evolved to include:

- workspace/current directory/project directory/additional dirs.
- worktree metadata.
- session name, model, output style, version.
- current context window usage.
- current usage from last API call.
- precomputed `used_percentage` and `remaining_percentage`.
- Claude.ai `rate_limits` for 5-hour and 7-day windows, with used percentage
  and reset time.

## Claude Rate-Limit Model

The official bundle exposes a structured `rate_limit_event` with:

```text
rate_limit_info:
- status: allowed | allowed_warning | rejected
- resetsAt
- rateLimitType: five_hour | seven_day | seven_day_opus | seven_day_sonnet | overage
- utilization
- overageStatus: allowed | allowed_warning | rejected
- overageResetsAt
- overageDisabledReason:
  - overage_not_provisioned
  - org_level_disabled
  - org_level_disabled_until
  - out_of_credits
  - seat_tier_level_disabled
  - member_level_disabled
  - seat_tier_zero_credit_limit
  - group_zero_credit_limit
  - member_zero_credit_limit
  - org_service_level_disabled
  - org_service_zero_credit_limit
  - no_limits_configured
  - unknown
- isUsingOverage
- surpassedThreshold
```

Claude Code also distinguishes these assistant error categories:

- `authentication_failed`
- `billing_error`
- `rate_limit`
- `invalid_request`
- `server_error`
- `unknown`
- `max_output_tokens`

Important behavior from changelog/bundle:

- Server rate limits are distinguished from plan usage limits.
- 429 retry messages include which limit was hit and when it resets.
- Rate-limit warnings should not trigger too early; weekly warnings require
  meaningful utilization.
- Long `Retry-After`/reset waits must surface immediately instead of leaving
  agents appearing stuck.
- Extra usage and overage have separate status/reset fields.

## KiloCode Architecture

KiloCode is structurally closer to a product platform than a single CLI:

- `packages/opencode/` is the shared CLI/runtime core.
- `packages/kilo-gateway/` wraps OpenRouter-compatible access with Kilo-specific auth and model fetching.
- `packages/kilo-vscode/` owns the VS Code extension, provider refresh orchestration, model picker sync, and auth UI behavior.
- `packages/kilo-docs/` and the repo-level `AGENTS.md` act as first-class contributor guidance and source-link maintenance.

The repository makes `AGENTS.md` operational, not decorative:

- it tells contributors to use `.kilo/command/*.md`, `.kilo/agent/*.md`, `kilo.json`, and `AGENTS.md`
- it defines the supported dev commands and source-link regeneration workflow
- it encodes `kilocode_change` markers for shared-file divergence control during upstream syncs

The generated coverage report in `docs/kilocode_provider_coverage.md` maps every local KiloCode snapshot provider into the Stagewarden registry and records the full model lists in `data/kilocode_provider_coverage.json`. That artifact is the quickest way to confirm that Stagewarden now treats the entire local KiloCode provider set as runtime-supported.

That matters for Stagewarden because it shows a fork can stay mergeable by isolating product-specific behavior while keeping shared files annotated and mechanically checked.

## KiloCode Model and Auth Flow

The most useful implementation pattern is the model/provider stack:

- `packages/kilo-gateway/src/api/models.ts` fetches Kilo/OpenRouter-compatible model metadata, validates it, and drops models that are image-only or do not support tools.
- The transformed model object includes capabilities, context size, pricing, modalities, and flags that the UI can consume directly.
- `packages/opencode/src/provider/models.ts` injects the `kilo` provider dynamically, but only when `enabled_providers` and `disabled_providers` allow it.
- The default model resolution path prefers an explicit config model first, then the best available provider model, then Kilo-specific fallbacks when the `kilo` provider is available, and finally fails loudly if no model is usable.
- `packages/kilo-vscode/src/KiloProvider.ts` coalesces provider refreshes, keeps session status maps in sync, and refreshes providers/agents after auth or organization changes.
- `packages/kilo-vscode/src/kilo-provider/model-state.ts` persists per-mode model choices in a shared state file so the CLI and extension can stay aligned.
- `packages/kilo-vscode/src/kilo-provider/handlers/auth.ts` keeps login/logout, org switching, profile refresh, and provider refresh separate so auth changes do not leak into unrelated UI state.
- `packages/opencode/src/session/system.ts` injects environment context and prompt selection rules that explicitly reference the Kilo project layout.

## Stagewarden Implications

- KiloCode reinforces the value of a shared runtime with product-specific layers on top, which matches Stagewarden's own separation between core agent logic and surrounding UX/governance features.
- Its provider filtering rules are a concrete example of model governance: only surface models that support the required tool flow and modalities.
- Its per-mode model persistence and post-auth refresh behavior are good references for keeping CLI and UI model state coherent.
- Its fork hygiene rules are a useful example of how to keep an upstream-derived codebase maintainable, even though Stagewarden should continue to prefer its own abstractions and not copy KiloCode implementation details.

## Stagewarden Implementation Implications

Stagewarden should treat `status` as a project-control dashboard, not only as an
auth command. It should combine:

- Auth/provider/account state.
- Active model and selected profile.
- Provider-limit snapshot and stale/missing status.
- Session/handoff state.
- Git boundary and local push state.
- Sandbox/permission posture.
- Tool activity, token usage, and wet-run checkpoints.
- Open issues/risks/exceptions.

Provider limits should be normalized into one internal schema:

```text
ProviderLimitSnapshot:
- provider
- account
- model
- captured_at
- status
- reason
- blocked_until
- primary_window
- secondary_window
- credits
- rate_limit_type
- utilization
- overage_status
- overage_resets_at
- overage_disabled_reason
- raw_message
```

Status output should have two modes:

- Human card: compact aligned sections like Codex.
- JSON: complete machine-readable structure for tests and scripts.

Status data must never print raw tokens. If a token is included for internal
refresh flows, it must be opt-in, redacted in logs, and absent from default CLI
output.

## Concrete Backlog

1. Add `stagewarden status --full` with Codex-like grouped sections:
   `Identity`, `Model`, `Account`, `Limits`, `Workspace`, `Permissions`,
   `Git`, `Handoff`, `Usage`, `Quality Gates`.
2. Add `stagewarden statusline --json` for external prompt/status scripts.
3. Add provider-limit stale detection with a 15-minute default threshold.
4. Add Claude-style rate-limit fields to provider lockout persistence.
5. Add token/context-window accounting to memory/handoff events.
6. Add `auth status <provider> --json` that shells to provider CLIs when safe:
   `codex login status`, `claude auth status --json`.
7. Add tests for missing/stale/unavailable limits and redaction.
