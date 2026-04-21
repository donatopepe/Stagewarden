# Stagewarden Handoff

Author: Donato Pepe

License: MIT

Last updated: 2026-04-20

## Purpose

This file is the human-readable project handoff for Stagewarden. It complements the runtime `.stagewarden_handoff.json` file and must stay updated with implementation decisions, pending work, recovery lanes, validation evidence, and Codex/Claude-inspired behaviours to reproduce.

The working rule is PRINCE2-style controlled execution:

- plan work as explicit stages
- execute only stages that are `ready` or `in_progress`
- persist handoff context continuously
- record git boundaries
- require wet-run validation
- create recovery lanes for exception paths
- keep model handoff context available without requiring manual resume
- adapt governance to task size and risk: small work stays lightweight, complex work gets stronger controls
- reduce ceremony, never principles

## Current Baseline

- Repository: `https://github.com/donatopepe/Stagewarden`
- Main package: `stagewarden`
- Runtime CLI: `stagewarden`
- Runtime handoff: `.stagewarden_handoff.json`
- Human handoff: `HANDOFF.md`
- Runtime model config: `.stagewarden_models.json`
- Runtime permission config: `.stagewarden_settings.json`
- Runtime trace: `.stagewarden_trace.ljson`
- Runtime PRINCE2 PID: `.stagewarden_prince2_pid.json`
- Agent manifesto: `AGENT_MANIFESTO.md`
- Agent policy: `AGENT_POLICY.md`
- Machine-readable policy: `AGENT_POLICY.json`

Latest known baseline at the time of this handoff:

- Local implementation snapshot: `5b79a4c stagewarden: initialize workspace`
- Last confirmed pushed baseline before this pass: `d4d864c stagewarden: initialize workspace`

## Current Implementation Pass

Status: pushed, continuing with incremental blocks

Implemented in this pass:

- Persisted structured provider limit snapshots in `.stagewarden_models.json`.
- Added model-level and account-level limit snapshots with sanitized fields only.
- Captured limit metadata automatically when executor sees provider block messages.
- Exposed persisted limit metadata through `status --full --json`.
- Exposed compact reset/usage fields through `statusline --json`.
- Kept provider status read-only commands free from model calls and token output.

Stored limit snapshot fields:

- `status`
- `reason`
- `blocked_until`
- `primary_window`
- `secondary_window`
- `credits`
- `rate_limit_type`
- `utilization`
- `overage_status`
- `overage_resets_at`
- `overage_disabled_reason`
- `stale`
- `captured_at`
- `raw_message`

Validation evidence:

- `python3 -m unittest tests/test_persistence.py tests/test_executor.py tests/test_trace_cli.py` passed, 108 tests.
- `python3 -m unittest discover -s tests` passed, 203 tests.
- `python3 -m stagewarden.main status --full --json` passed as wet-run.
- `python3 -m stagewarden.main statusline --json` passed as wet-run.

Follow-up implemented after this pass:

- Added `model limits` and `models limits` interactive/CLI commands.
- Added `stagewarden "model limits" --json` machine-readable output.
- Added concise human rendering for provider/account limit state.
- Updated interactive help and README examples.
- Added stale detection for provider limit snapshots based on `captured_at`.
- Added `model limit-record <model> <message>` to persist pasted provider limit messages safely.
- Added `account limit-record <model> <account> <message>` for account-specific provider limits.
- Added `model limit-clear <model>` and `account limit-clear <model> <account>` to remove stored limit snapshots, messages, and temporary blocks.
- Switched `account login chatgpt <profile>` to a Codex-style browser flow backed by `codex login`.
- Switched `account logout chatgpt <profile>` to Codex-backed logout plus local profile marker cleanup.
- Corrected CLI/status terminology: provider and provider-model are now rendered separately.
- Added explicit `provider_model` and `provider_model_selection` fields to model/status JSON reports.
- Route rendering now shows `provider=...` and `provider_model=...` instead of conflating provider with model.
- Added provider-model catalog metadata with supported `reasoning_effort` values.
- Added persisted provider-model params per provider, currently including `reasoning_effort`.
- Added CLI commands `model params`, `model param set`, and `model param clear`.

Additional validation evidence:

- `python3 -m unittest tests/test_trace_cli.py` passed, 78 tests.
- `python3 -m stagewarden.main "model limits" --json` passed as wet-run.
- `python3 -m stagewarden.main "model limits"` passed as wet-run.
- `python3 -m unittest discover -s tests` passed, 204 tests.
- Stale detection validation passed through `test_model_limits_cli_json_outputs_persisted_snapshots`.
- `python3 -m stagewarden.main "model limit-record chatgpt Usage limit reached until 2026-05-01T18:30." --json` passed as wet-run.
- `python3 -m stagewarden.main "model limit-clear chatgpt" --json` passed as wet-run and restored local provider availability.
- `python3 -m unittest discover -s tests` passed, 206 tests.
- `python3 -m unittest tests/test_auth.py tests/test_trace_cli.py` passed, 84 tests after browser-login migration.
- `python3 -m unittest discover -s tests` passed, 209 tests after browser-login migration.
- Interactive wet-run with stubbed `codex` backend confirmed `account login chatgpt personale` updates the active profile and stores a sanitized Codex marker.
- `python3 -m stagewarden.main models --json` passed as wet-run and now exposes `preferred_provider`, `provider_model`, and `provider_model_selection`.
- `python3 -m stagewarden.main statusline --json` passed as wet-run and now exposes active provider/provider-model separately.
- `python3 -m stagewarden.main "model list chatgpt"` passed as wet-run and renders the provider-model catalog plus supported reasoning levels.
- `python3 -m stagewarden.main "model variant chatgpt gpt-5.3-codex"` + `model param set chatgpt reasoning_effort high` + `model params chatgpt` passed as wet-run.
- Interactive guided model selection has been added through `model choose [provider]`, with menu-driven provider, provider-model, and reasoning-effort selection.
- Guided menus now also cover `model preset <provider>` and `account choose [provider]` inside the interactive shell.
- `python3 -m unittest tests/test_trace_cli.py` passed, 86 tests.
- `python3 -m unittest discover -s tests` passed, 214 tests.
- Interactive wet-run passed with `model choose chatgpt`, selecting `gpt-5.4` plus `reasoning_effort=medium`, and `models` then showed the persisted provider-model state.
- `python3 -m unittest tests/test_trace_cli.py` passed again, 88 tests, after adding guided preset/account menus.
- `python3 -m unittest discover -s tests` passed again, 216 tests, after adding guided preset/account menus.
- Interactive wet-run passed with `model preset chatgpt`, selecting `balanced`, and `model params chatgpt` then showed `provider_model=gpt-5.1-codex-mini` plus `reasoning_effort=medium`.
- Interactive wet-run passed with `account choose openai`, selecting `personale`, and `accounts` then showed the active profile change.
- `model preset <provider>` without an explicit preset value now opens the provider-model picker instead of the preset picker.
- Interactive wet-run passed with `model preset chatgpt`, selecting `gpt-5.4`, and `model params chatgpt` then showed `provider_model=gpt-5.4` plus `reasoning_effort=medium`.
- Interactive shell commands now require the `/` prefix in the real shell; input without `/` is treated as a task for the agent loop.
- Test harness compatibility was preserved for scripted `StringIO` command inputs so the shell command suite remains verifiable without changing task semantics.
- `python3 -m unittest tests/test_trace_cli.py` passed again, 88 tests, after slash-command routing.
- `python3 -m unittest discover -s tests` passed again, 216 tests, after slash-command routing.
- Interactive wet-run passed with bare `status`, which was treated as a task and rejected by governance as expected.
- Interactive wet-run passed with `/status`, which was treated as a shell command and rendered the status dashboard.
- `study/` remains developer-only learning material and is not exposed in agent prompts, status, doctor output, or runtime behavior.
- PRINCE2 role routing is implemented: `/roles`, `/roles propose`, `/roles setup`, `/role configure [role]`, `/role clear <role>`, and `/project start`.
- Role assignments persist provider, provider-model, reasoning parameters, account, mode, and source in `.stagewarden_models.json`.
- Project handoff now synchronizes PRINCE2 role assignments so model calls receive implicit role ownership context without a manual resume.
- Provider rate-limit recovery now records blocked-until metadata, switches automatically to an available provider/account, and asks the user whether to wait/stop when no alternative exists.
- `python3 -m unittest tests/test_trace_cli.py` passed, 91 tests, after role routing and `study/` runtime removal.
- `python3 -m unittest tests/test_persistence.py` passed, 7 tests, after role/handoff persistence.
- `python3 -m unittest tests/test_executor.py` passed, 25 tests, after rate-limit recovery decision support.
- `python3 -m unittest discover -s tests` passed, 220 tests, after role routing and rate-limit recovery.
- `status` now includes a PRINCE2 role baseline section and explicitly suggests `/project start` or `/roles setup` when role ownership is missing.
- Wet-run `python3 -m stagewarden.main status` confirmed the missing-role operational hint in the real workspace.
- `python3 -m unittest tests/test_trace_cli.py` passed, 91 tests, after the status role-baseline section.
- `python3 -m unittest discover -s tests` passed, 220 tests, after the status role-baseline section.
- PRINCE2 role automation now routes execution by role domain: Project Manager for planning/control, Team Manager for implementation, Project Assurance for validation, Change Authority for exceptions/changes/tolerance breaches, Project Executive for business stop-go, Senior User for acceptance/benefits, Senior Supplier for technical feasibility, and Project Support for records/traceability.
- Role-assigned models now receive scoped context only: unrelated risks/issues/exception plans/logs are omitted unless the active PRINCE2 role owns that domain.
- Executor tests verify Team Manager routing uses the configured provider/model/params and does not expose business risk or exception-plan content outside the Team Manager domain.
- `roles domains` now renders each PRINCE2 role responsibility and context boundary so model assignments can be reviewed before project startup.
- `roles domains --json` now exposes the same role-domain matrix with stable fields: command, rule, roles, role, label, responsibility, and context_scope.
- Wet-run `python3 -m stagewarden.main "roles domains"` passed and shows all role domains.
- Wet-run `python3 -m stagewarden.main "roles domains" --json` passed and emits the machine-readable role-domain matrix.
- `python3 -m unittest tests/test_executor.py tests/test_trace_cli.py` passed, 119 tests, after role-domain CLI support.
- `python3 -m unittest tests/test_trace_cli.py` passed, 93 tests, after role-domain JSON support.
- `python3 -m unittest discover -s tests` passed, 223 tests, after role-domain CLI support.
- `sources status` is implemented as a read-only external reference verifier for `docs/source_references.md`.
- `sources status` reports local path presence, Git repository state, HEAD, upstream URL match with `.git` suffix normalization, and shallow-clone state.
- Wet-runs `python3 -m stagewarden.main "sources status"` and `python3 -m stagewarden.main "sources status" --json` passed in the real workspace and reported Caveman, Codex, and Claude references as OK.
- `python3 -m unittest tests/test_trace_cli.py` passed, 92 tests, after the sources status command.
- `python3 -m unittest discover -s tests` passed, 221 tests, after the sources status command.

Next recommended implementation blocks:

Priority 1 - interactive operator experience:

- Implement Codex-style slash command palette: when the user types `/` in the interactive shell, show an autocomplete menu with command names, short explanations, and keyboard cursor selection/confirmation.
- Add structured command metadata so help, completions, slash palette, and JSON command catalogs share one source of truth.
- Add `commands --json` or `help --json` for machine-readable command discovery and future UI integrations.

Priority 2 - PRINCE2 role automation hardening:

- Add `roles check` to validate that every PRINCE2 role has provider/model/account assignments before controlled delivery.
- Add `roles matrix --json` to combine role domains, active assignments, provider limits, and account availability in one startup decision surface.
- Add a Project Board startup gate: if role baseline is missing, `project start` should propose assignments and require explicit confirmation before entering normal delivery.
- Add tests proving role context isolation for Project Executive, Project Assurance, Change Authority, and Team Manager, not only Team Manager.

Priority 3 - source reference governance:

- Add `sources update` command that runs `git pull --ff-only` in each reference repo and records updated heads.
- Add `sources status --strict` to fail when reference repos are missing, dirty, non-shallow when expected, or remote URLs mismatch.

Priority 4 - provider status and limits:

- Add provider-specific parsers for richer Claude Code and Codex status output when upstream CLIs expose machine-readable usage.
- Extend provider-limit persistence with reset windows, utilization, overage fields, stale-limit detection, and redacted raw-message previews.
- Add token/context-window accounting to handoff and memory events where provider output exposes safe usage metadata.

Priority 5 - resilience and auditability:

- Add a `preflight` command that combines doctor, sources status, roles check, model limits, git status, and permission posture.
- Add JSON schema stability tests for status, statusline, roles domains, roles matrix, source status, and model limits.
- Add an operator-facing remediation section in `status` when the project is in exception or role baseline is incomplete.

## Implemented Capabilities

- Codex-style agent loop: plan, call model through handoff, execute tool, observe, retry, escalate, validate, persist state.
- Multi-model routing: local, cheap, ChatGPT/OpenAI, Claude with escalation and fallback.
- Provider/account configuration: model add/remove/use/list/variant/block/unblock, account add/use/remove/block/unblock/login.
- Online usage-limit capture: usage-limit messages such as `try again at 8:05 PM` are persisted as blocked-until metadata.
- Device-code style OpenAI login flow scaffolded for real browser login, without browser token scraping.
- Claude credential handling aligned to provider-style credential files and account profiles.
- Interactive shell mode: start in a folder and run `stagewarden`, then use commands or natural task input.
- Rich interactive help with model, account, permission, handoff, git, LJSON, and Caveman commands.
- Git prerequisite governance: repository initialization, runtime ignores, local snapshot commits, history inspection.
- Git shell commands: status, log, history, show, show stat.
- Git tool actions for autonomous execution: status, log, show, file history.
- Permission engine: workspace settings, default modes, allow/ask/deny rules.
- Permission modes: `default`, `accept_edits`, `plan`, `auto`, `dont_ask`.
- Fast mode aliases: `mode plan`, `mode auto`, `mode accept-edits`, `mode dont-ask`, `mode default`.
- Session-only permissions: `permission session mode`, `permission session allow|ask|deny`, `permission session reset`.
- Live permission refresh: active agent tools reload permission policy after shell permission changes.
- Approval prompt flow: interactive `ask` decisions support `y`, `n`, `always`, `session`, and `deny`; non-interactive tools remain fail-closed.
- Tool invocation transcript: tool calls are recorded in memory, persisted as LJSON, and exposed through `transcript`/`trace`.
- Shell execution across OS families: POSIX shell, PowerShell, cmd fallback.
- File tools: read, write, patch, patch files, list, search.
- Wet-run enforcement: dry-run or narrative completion is not accepted as final checkpoint.
- LJSON core: encode/decode, numeric-key variant, gzip, schema version, streaming chunk support, benchmark examples.
- LJSON use for runtime trace.
- ASCII/confusable safety for generated and tool output.
- Caveman mode: inspired by Julius Brussee's Caveman, with command ergonomics, review/commit/compress commands, README acknowledgements.
- PRINCE2 governance gate: task assessment, PID generation, project controls, closure checks.
- Persistent PRINCE2 handoff: plan, stage, latest observation, git boundary, registers, exception plan, lessons.
- Dedicated registers: risks, issues, quality, lessons, exception plan.
- Operational posture: governance summary, stage health, next action, active stage, git boundary.
- Stage boundary view: closed stages, active stage, PID boundary, decision, registers, exception plan.
- Implementation backlog in handoff: persisted `planned`, `ready`, `in_progress`, `blocked`, `done` lifecycle states.
- Planner stage gating: only `ready` and `in_progress` stages are executed.
- Automatic promotion: next `planned` stage becomes `ready` after controlled completion.
- Recovery lane: exception plans generate explicit `recovery-step-*` stages.
- Recovery resume: recovery stages can be resumed from handoff.
- Recovery boundary states: `exception_active`, `recovery_active`, `recovery_cleared`, `none`.
- Recovery closure gate: completed recovery lanes close open issues/risks, clear exception controls, close covered failed stages, and resume normal planned stages.
- Handoff Markdown auto-export: `handoff export` and `handoff md` update the generated runtime section in `HANDOFF.md` with redaction.
- Safer command classification: shell permission checks now distinguish read-only git commands from write/high-risk operations, redirection, package installs, and mutating commands.

## Codex/Claude-Inspired Behaviours To Apply

These are the implementation items still worth applying, based on prior source/research review and Stagewarden's current architecture.

### 1. Approval Prompt Flow

Status: implemented

Implement an interactive approval flow similar to Codex/Claude tool approvals.

Implemented behaviour:

- When permission decision is `ask`, the interactive shell prompts the user with capability, target, and rule.
- Supported answers: `y`, `n`, `always`, `session`, and `deny`.
- `always` persists an allow rule in `.stagewarden_settings.json` and removes the matching ask rule.
- `session` adds a session-only allow rule.
- `deny` persists a deny rule.
- Non-interactive tools remain fail-closed for `ask`.

Validation:

- Unit tests cover allow precedence over matching ask rules.
- CLI tests cover `session` approval without workspace allow persistence.
- CLI tests cover `always` approval with workspace allow persistence and ask removal.
- Tool tests confirm non-interactive ask remains blocked.

### 2. Tool Invocation Transcript

Status: implemented

Implement a Codex-like visible transcript for tool calls.

Implemented behaviour:

- Tool actions produce compact transcript entries.
- Entries include iteration, step, tool, action type, success/failure, summary, detail preview, duration where available, and error type.
- Transcript is persisted in `.stagewarden_memory.json` as LJSON.
- Shell commands `transcript` and `trace` render recent tool calls.

Validation:

- Memory tests cover transcript persistence and rendering.
- Executor tests cover transcript recording from tool actions.
- CLI tests cover `transcript` rendering after an actual agent run.

### 3. Stronger Patch Application UX

Status: implemented

Improve patch handling toward Codex-style editing discipline.

Implemented behaviour:

- Prefer unified patch application for multi-file edits.
- Multi-file patches return per-file summaries such as `add path`, `update path`, and `delete path`.
- Duplicate patch targets in one diff are rejected as ambiguous before any write occurs.
- Executor outcomes keep before/after git head metadata for patching steps through the standard step outcome.
- `preview_patch_files` validates and summarizes a unified diff without writing, including in plan mode.

Validation:

- Patch tests cover add, update, delete, failed hunk, duplicate targets, and plan-mode preview.
- Plan mode allows preview but blocks write.
- Wet-run file content checks verify patch results after application.
- Executor tests cover model-dispatched patch preview and transcript recording.

### 4. Model Context Files

Status: implemented

Expose persistent handoff and logs to model prompts more deliberately.

Implemented behaviour:

- Include concise handoff summary in every model prompt.
- Include recent LJSON trace summary.
- Include current recovery state and backlog status.
- Include git boundary and dirty state.
- Keep prompt bounded with truncation rules.
- Add a dedicated `Model context files` prompt section naming `.stagewarden_handoff.json`, `.stagewarden_memory.json`, and `.stagewarden_trace.ljson`.

Validation:

- Executor prompt tests assert context file names, recovery state, backlog status, git boundary, and dirty state are present.
- Prompt size remains bounded and truncation markers are asserted for oversized registers.

### 5. Provider Capability Registry

Status: implemented

Move model/provider capabilities into a registry closer to Claude/Codex provider abstractions.

Implemented behaviour:

- Provider capabilities are centralized in `stagewarden/provider_registry.py`: auth type, model aliases, default model, context assumptions, account profiles, browser login, API-key support, env vars, URLs, and login hints.
- `handoff.py`, `modelprefs.py`, `router.py`, `secrets.py`, and CLI model/account rendering consume the registry.
- `model list` now shows capability metadata in addition to variants.
- `chatgpt` plan login semantics are explicitly separate from OpenAI API-key semantics.
- Keep no token scraping and no hidden browser extraction.

Validation:

- Provider registry unit tests cover auth/capability data and variant/backend derivation.
- Model list CLI tests assert different login hints for `chatgpt`, `openai`, and `claude`.
- Routing and handoff tests still pass.

### 6. Shell Sessions As First-Class Tools

Status: implemented

Expand persistent shell sessions toward Codex/Claude terminal behaviour.

Implemented behaviour:

- Expose interactive commands: `sessions`, `session list`, `session create [cwd]`, `session send <id|last> <command>`, and `session close <id|last>`.
- Persist shell session IDs only for current process, not repo.
- Track cwd and return code.
- Keep permission checks per command.

Validation:

- Tool tests cover create/list/send/close with marker-based command output.
- CLI tests cover `last` alias, cwd visibility, return-code preview, and close.
- CLI tests verify plan-mode permission denial works inside a persistent session.

### 7. Resume Command Over Handoff

Status: implemented

Even though Stagewarden uses implicit handoff resume, add explicit commands for operator control.

Implemented behaviour:

- `resume` reloads current handoff context into the active agent and reruns the task stored in handoff.
- `resume --show` prints task, current step, next action, and stage view.
- `resume --clear` archives current handoff as `.stagewarden_handoff.archive.<timestamp>.json` and starts fresh.
- Preserve implicit resume as default.

Validation:

- CLI tests verify `resume --show` uses existing `current_step_id`.
- CLI tests verify `resume --clear` archives the old handoff, creates a fresh context, and leaves the archive inspectable.

### 8. Recovery Closure Gate

Status: implemented

Make `recovery_cleared` perform a formal PRINCE2 closure action instead of only rendering next action.

Implemented behaviour:

- When all `recovery-step-*` stages complete with wet-run evidence, the agent closes the recovery gate.
- Open issues and risks are closed with recovery evidence.
- Failed non-recovery stages covered by recovery are marked completed.
- Exception plan is cleared only after recovery evidence closes open issues.
- The next planned normal stage is promoted to `ready`.

Validation:

- Integration tests cover a project starting in exception, executing recovery steps, closing registers, clearing exception plan, and completing the resumed normal stage.
- Wet-run gate remains enforced by the executor before any recovery stage can complete.

### 9. Handoff Markdown Auto-Update

Status: implemented

Keep this file updated automatically from runtime handoff and implementation backlog.

Implemented behaviour:

- Commands `handoff md` and `handoff export` update the generated runtime section in `HANDOFF.md`.
- Export includes task, status, plan status, active stage, git boundary, PID boundary, recovery state, next action, registers, backlog, and recent entries.
- Manual roadmap content is preserved outside stable generated markers.
- Token-like values, bearer secrets, and JWT-like strings are redacted.

Validation:

- CLI tests cover export command, marker insertion, manual content preservation, and secret redaction.

### 10. Board Review Command

Status: implemented

Add a PRINCE2 board-level summary command.

Implemented behaviour:

- Command: `board` or `stage review`.
- Show business justification, current boundary decision, open issues, open risks, quality status, recovery state, and recommended authorization.
- Distinguish continue, stop, recover, close.

Validation:

- Closed clean project recommends closure.
- Open issues recommend review before closure.
- Recovery active recommends recovery execution.

### 11. Safer Command Classification

Status: implemented

Improve shell permission classification beyond first token.

Implemented behaviour:

- `git status`, `git log`, `git show`, `git diff`, and other inspection commands are classified as read.
- Mutating git commands such as `git add`, `commit`, `push`, `checkout`, `merge`, and `rebase` are no longer treated as read-only.
- Shell redirection and tee-style output are classified as write.
- Package installation and mutating npm/python/node/test commands are classified as write/network-risk.
- Delete/move/copy/install-style operations are classified as write.

Validation:

- Tool tests verify read-only git commands are not blocked by plan mode policy.
- Tool tests verify write git commands are blocked in plan mode.
- Tool tests verify redirection and package install commands are blocked in plan mode.

### 12. Rich Help Reorganization

Status: implemented

Current help is complete but long. Reorganize it like modern CLIs.

Implemented behaviour:

- `help` shows compact categories and fast examples.
- `help models`, `help accounts`, `help permissions`, `help handoff`, `help git`, and `help ljson` show focused command lists and examples.
- `help caveman` remains wired to Caveman-specific help for compatibility.
- Keep examples in each category.

Validation:

- CLI tests cover compact top-level help.
- CLI tests cover category help for models, accounts, permissions, handoff, git, and LJSON.

### 13. Model Handoff Result Schema

Status: implemented

Harden model output parsing with a stricter schema.

Implemented behaviour:

- Accept strict JSON object with `summary`, `action`, `confidence`, `risks`, and `validation`.
- Preserve compatibility with simpler `{summary, action}` responses.
- Validate optional schema fields when present.
- Reject unknown destructive action types before tool execution.
- Invalid output is recorded through the existing executor memory/handoff failure path.

Validation:

- Executor tests cover valid strict schema execution.
- Executor tests cover invalid schema rejection and failure memory.
- Executor tests cover denial of an unknown destructive action.

### 14. Cost-Aware Execution Budget

Status: implemented

Make cost control explicit in router and handoff.

Implemented behaviour:

- Track model usage counts from persisted execution attempts.
- Record model chosen per step in handoff through existing step completion entries.
- Expose budget policy: prefer local, then cheap, then ChatGPT/OpenAI/Claude for complex or failing tasks.
- Expose `models usage` and `cost` shell commands.

Validation:

- Memory tests cover model usage counts, failures, step coverage, and cost tiers.
- CLI tests cover `models usage` and `cost` alias.
- Existing router tests continue to validate local-first/simple-task routing.
- Failures escalate according to policy.
- Usage summary is visible in shell.

### 15. Cross-OS Setup Verification

Status: implemented

Strengthen setup scripts for macOS, Linux, and Windows.

Implemented behaviour:

- `stagewarden doctor` validates Python 3.11+, Git availability, PATH launcher visibility, and repository state.
- `doctor` reports provider capabilities for each configured model family: auth type, profile support, browser login, API-key support, token env state, and default model.
- `doctor` does not install prerequisites and does not initialize git.
- Interactive shell command `doctor` exposes the same report.
- Setup scripts for Unix and Windows now perform a best-effort post-install `doctor` check through `python -m stagewarden.main doctor`.
- If the post-install check cannot run successfully, setup prints an explicit next-step command instead of silently skipping validation.
- Do not auto-install git silently; report prerequisite clearly.

Validation:

- CLI tests verify `stagewarden doctor` reports Python/Git/PATH/repository state and does not create `.git`.
- Interactive shell tests verify `doctor` rendering.
- Setup script tests verify post-install doctor wiring and still pass.

## Immediate Next Implementation Order


## Recently Completed

### Setup Post-Install Doctor

Status: implemented

Implemented behaviour:

- `scripts/setup_unix.sh` and `scripts/setup_windows.ps1` now run a best-effort `doctor` check immediately after install.
- Successful validation emits `Post-install check: stagewarden doctor OK`.
- Failed validation falls back to an explicit command suggestion for the operator.

Validation:

- Setup script tests cover doctor invocation wiring and Unix fallback execution path.
- Full suite remains green after the setup changes.

### Doctor JSON Output

Status: implemented

Implemented behaviour:

- `stagewarden doctor --json` emits a stable machine-readable report for automation.
- The JSON report includes Python, Git, PATH launcher, repository state, provider capabilities, and policy flags.
- Human-readable `stagewarden doctor` output remains unchanged for operators.

Validation:

- CLI tests parse the JSON output and verify provider and policy fields.

### Final Summary Cost/Budget

Status: implemented

Implemented behaviour:

- Final agent summaries now include a dedicated `Cost and budget:` section.
- The section reports routing policy, per-model usage counts, highest cost tier reached, and failed model call count.
- The summary is driven by execution memory so it reflects the actual run, not static configuration.

Validation:

- Memory tests cover budget summary rendering.
- Agent integration tests verify the final user-facing summary includes the budget section.

### Resume Wet-Run

Status: implemented

Implemented behaviour:

- Interactive `resume` now has an end-to-end wet-run test with a success stub backend.
- The test starts from persisted handoff context, resumes execution, creates the target artifact, and verifies handoff closure.
- `resume` now reports the original resumed step id, not the mutated post-run step id.

Validation:

- CLI tests cover `resume --show`, `resume --clear`, and full `resume` execution against a fake model binary.

### Richer Model Usage and Cost Reporting

Status: implemented

Implemented behaviour:

- `models usage` and `cost` now include totals, failure rate, highest tier reached, last model used, and escalation path.
- Memory now exposes `model_usage_stats()` as a machine-readable aggregate for automation and future JSON/telemetry output.
- Budget summaries reuse the same aggregated stats to avoid divergent reporting.

Validation:

- Memory tests cover machine-readable usage stats and richer summaries.
- Interactive shell tests verify enriched `models usage` and `cost` output.

### Model Usage JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden "models usage" --json` and `stagewarden cost --json`.
- The JSON output reuses `model_usage_stats()` and includes routing budget policy metadata.

Validation:

- CLI tests parse the JSON output and verify totals, failures, and escalation path.

### Transcript JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden transcript --json` and `stagewarden trace --json`.
- The JSON output exposes recent transcript entries from persisted workspace memory without parsing the text renderer.

Validation:

- Memory tests cover machine-readable transcript reports.
- CLI tests parse transcript JSON output and verify stored entry fields.

### Handoff and Resume JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden handoff --json`.
- Non-interactive CLI now supports `stagewarden "resume --show" --json`.
- Both outputs reuse runtime handoff/state logic instead of parsing text views.

Validation:

- CLI tests parse handoff JSON and resume-show JSON output and verify task, current step, next action, and boundary state.

### Status and Boundary JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden status --json`.
- Non-interactive CLI now supports `stagewarden boundary --json`.
- Outputs expose operational posture, permissions, model state, and PRINCE2 boundary control state without text parsing.

Validation:

- CLI tests parse status JSON and boundary JSON output and verify mode, stage view, and boundary decisions.

### Register JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `risks`, `issues`, `quality`, `exception`, `lessons`, and `todo` with `--json`.
- Outputs expose raw PRINCE2 registers and implementation backlog directly from runtime handoff state.

Validation:

- CLI tests parse register/backlog JSON output and verify representative fields for each command.

### Models and Accounts JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden models --json`.
- Non-interactive CLI now supports `stagewarden accounts --json`.
- Outputs expose provider routing state, preferred model, configured accounts, active account, token-store presence, and env mapping.

Validation:

- CLI tests parse models/accounts JSON output and verify preferred model, account activity, and token-store state.

### Permissions JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden permissions --json`.
- Output exposes workspace, session, and effective permission policy without relying on text rendering.

Validation:

- CLI tests parse permissions JSON output and verify workspace mode and allow/ask/deny rules.

### Git Read-Only JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports JSON output for `git status`, `git log`, `git history`, and `git show --stat`.
- Outputs include raw command text plus lightweight derived fields like `lines` or `commits` for easier automation.

Validation:

- CLI tests parse git JSON output and verify status, commit subjects, history path, and show-stat metadata.

### Shell Sessions JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden sessions --json` and `stagewarden "session list" --json`.
- Output exposes current process shell-session ids, cwd, and running/closed state.

Validation:

- CLI tests parse sessions JSON output and verify the empty-state contract.

### Handoff Export and Resume-Clear JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden "handoff export" --json` and `stagewarden "handoff md" --json`.
- Non-interactive CLI now supports `stagewarden "resume --clear" --json`.
- Outputs expose target/archive path and operation outcome for automation workflows.

Validation:

- CLI tests parse export/reset JSON output and verify target/archive metadata.

### Overview Command

Status: implemented

Implemented behaviour:

- Added `overview` as a compact operational command for operators.
- Added `stagewarden overview --json` as a single machine-readable snapshot aggregating status, board, handoff, model usage, and transcript signals.

Validation:

- CLI tests parse overview JSON and verify authorization, model-usage totals, transcript count, and handoff task.

## Recently Completed

## Autonomous Backlog

### Provider Limit Status Across Active Providers

Status: implemented

Current state already implemented:

- Stagewarden is already multiprovider at routing level: `local`, `cheap`, `chatgpt`, `openai`, and `claude`.
- Provider and account usage-limit messages are already parsed into `blocked-until` metadata.
- The executor already blocks the failing model or account until the reported reset time and retries another eligible route.
- Current operator visibility is partial:
  - `models` and `status` show enabled/active/preferred state and `blocked-until` at model level.
  - `accounts` shows configured accounts, active account, stored token presence, env mapping, and `blocked-until` at account level.
  - `models usage` / `cost` shows Stagewarden-internal usage history, not provider-native remaining quota.

Implemented behaviour:

- `status` now includes a dedicated `Provider limit status:` section.
- `status --json` now includes a stable `provider_limits` object.
- For each enabled provider, Stagewarden now exposes:
  - enabled/active/preferred
  - routed variant
  - active account
  - model `blocked_until`
  - blocked accounts with `blocked_until`
  - last known error reason from recorded attempts
  - last attempt route/status
  - last successful use
- The implementation keeps a strict distinction between:
  - Stagewarden-internal usage history
  - provider/account temporary lockouts
  - provider-native remaining quota, which remains unsupported unless an official source exists
- The latest provider-reported limit message is now persisted per model/account together with `blocked_until`.
- Provider-limit views now expose both the lock time and the last known lockout cause text.
- Provider-limit views now classify lockout causes as `usage_limit`, `rate_limit`, `credits_exhausted`, or `provider_unavailable` when the provider message supports it.

Explicit non-goal for now:

- Do not invent fake remaining credits/messages for ChatGPT, Claude, or other providers when the upstream provider does not expose an official remaining-quota source to this agent.

Validation:

- CLI tests verify `status --json` includes provider-limit state for mixed multiprovider scenarios.
- Interactive shell tests verify `status` renders provider-limit posture together with resume context.
- Test coverage includes model-level blocks, account-level blocks, and recent error/success state.
- `overview` and `report` now also surface compact provider-limit summaries for faster operator reading.
- `overview --json` and `report --json` now carry provider-limit posture in machine-readable form.
- Persistence tests verify roundtrip storage of last limit messages in model preferences.
- Executor tests verify classification of provider limit messages.


### Caveman Help Snapshot

Status: implemented

Implemented behaviour:

- Added a CLI snapshot-style test for `help caveman`.
- The test protects supported levels, aliases, and key commands from accidental regression.

Validation:

- CLI test verifies Caveman help still exposes levels, aliases, and review/commit/compress commands.

## Recently Completed

### Resume Context Command

Status: implemented

Implemented behaviour:

- Added `resume context` to the shell and non-interactive CLI.
- The command exposes the latest implicit execution context without opening `HANDOFF.md`.
- Output includes the current task/step, latest model attempt, routed account/variant, latest tool evidence, and latest git snapshot.

Validation:

- CLI tests verify `resume context --json` returns structured route, tool, and git snapshot data.
- Interactive shell tests verify `resume context` renders the latest execution evidence in human-readable form.

### Shell UX Direction

Status: decided

Decision:

- Keep mini-block shell rendering as the preferred interaction style.
- Do not collapse shell progress and agent result output into a single compact status line.
- Favor short titled sections such as `Running task:`, `Shell progress (before|after):`, and `Agent result:`.

### Interactive Model Streaming In Shell

Status: implemented

Implemented behaviour:

- Interactive shell sessions now forward live `run_model` stdout through a streaming callback while still capturing the full final payload for strict JSON parsing.
- Streaming is attached only to the interactive shell agent path; non-interactive CLI commands keep the previous buffered behavior.
- Stream output is prefixed with a compact marker such as `[model-stream local]`.
- Added session-scoped shell controls `stream on`, `stream off`, and `stream status`.
- Interactive task execution is now framed with `Running task:` before execution and `Agent result:` before the final summary.
- Interactive shell now prints a compact `Shell progress (before|after)` block with active step, stage health, boundary decision, recovery state, and git head.
- Shell progress blocks now also show route context: planned model/account/variant before execution and actual model/account/variant after execution.
- The `after` shell progress block now also shows the latest local git checkpoint recorded for the run.
- Shell output now also includes a `Last step outcome:` mini-block between the final agent summary and the `after` progress block.
- `Last step outcome:` now also shows the concrete evidence source from the latest tool transcript, including tool, tool action, and duration when available.
- Runtime handoff markdown export now includes an `Execution Resume Context` block with latest model attempt, route, latest tool evidence, and latest git snapshot.

Validation:

- Handoff tests verify the streaming callback receives live model output.
- Interactive shell tests verify streamed model output is visible during task execution.
- Interactive shell tests verify stream toggling and suppression when streaming is disabled.
- Interactive shell tests verify the task/result framing is present around streamed execution.
- Interactive shell tests verify progress blocks are rendered around task execution.
- Memory and shell tests verify account and variant route details are preserved and rendered.
- Interactive shell tests verify the latest git snapshot is surfaced in the `after` block.
- Interactive shell tests verify the focused `Last step outcome:` block is rendered.
- Interactive shell tests verify the focused outcome block includes tool evidence details.
- Interactive shell export tests verify `HANDOFF.md` includes execution resume context and redacts sensitive values in latest observations and tool details.

### Multi-Account Failover Across Primary And Fallback Models

Status: implemented

Implemented behaviour:

- The executor now iterates across all available non-blocked accounts for the selected model instead of stopping after a single alternate profile.
- The same account failover logic now also applies to the fallback model after a primary model failure.
- Usage-limit messages continue to block the specific account that failed, and the next eligible account is tried automatically.

Validation:

- Executor tests verify repeated same-model account failover until success.
- Executor tests verify fallback-model account failover when the first fallback account is also blocked.

### PRINCE2 Git Step Checkpoints

Status: implemented

Implemented behaviour:

- Per-step automatic git snapshots now use structured commit messages with explicit PRINCE2 context.
- Step checkpoint commits now include step id, resulting status, stage health, boundary decision, and a compact task label.
- The git history is therefore usable as a lightweight control timeline, not just as a generic autosave stream.

Validation:

- Agent integration tests inspect real `git log --oneline` output and verify PRINCE2 boundary annotations are present in snapshot commits.

### Project Report Command

Status: implemented

Implemented behaviour:

- Added `report` as a compact human-readable summary for issue updates, project closure notes, and operator handoff.
- Added `stagewarden report --json` as a machine-readable summary with task, project status, stage health, governance status, authorization recommendation, next action, open controls, model activity, recent lessons, and backlog preview.
- Interactive shell now supports `report`.
- README now documents `report` together with `overview`, `health`, and `board`.

Validation:

- CLI tests parse `report` JSON output and verify task, authorization, issue count, model calls, lessons, and backlog preview.
- Interactive shell tests verify `report` rendering and backlog visibility.

### Interactive Shell History And Completion

Status: implemented

Implemented behaviour:

- Added optional `readline` integration for the interactive shell.
- Interactive sessions now persist history per workspace in `.stagewarden_history` when `readline` is available.
- Added TAB completion for core shell commands and targeted workspace-path completion for `git history`, `patch preview`, and `session create`.
- The feature degrades safely on platforms without `readline`; the shell still works normally without history/completion.

Validation:

- CLI tests verify command completion candidates include core shell commands.
- CLI tests verify workspace-path completion candidates for `git history` and `patch preview`.

### Health Command

Status: implemented

Implemented behaviour:

- Added `health` as a compact operational command for quick automation and shell inspection.
- Added `stagewarden health --json` as a stable machine-readable readiness snapshot.
- The report exposes authorization, boundary decision, open issues, open risks, open quality items, recovery state, next action, model failures, model calls, and transcript count.
- Interactive shell now supports `health` with a concise human-readable rendering.
- Help and README now document `health` alongside `overview`, `board`, and `doctor`.

Validation:

- CLI tests parse `health` JSON output and verify readiness, authorization, issue count, failure count, and transcript count.
- Interactive shell tests verify `health` rendering for a clean closed project.

### Patch Preview Command

Status: implemented

Implemented behaviour:

- Interactive shell command `patch preview <diff-file>` reads a unified diff file from the workspace.
- The command validates the diff through `preview_patch_files` and returns per-file summaries without writing.
- The command works in plan mode because it performs only read/validation operations.

Validation:

- CLI test covers plan-mode preview and verifies target file contents remain unchanged.

## Validation Standard

Every implementation must include:

- unit tests
- integration or CLI tests where applicable
- wet-run verification
- git snapshot
- push to remote

Dry-run alone is not a valid checkpoint.

## External Source Base

Status: initialized

Local reference directory:

- `external_sources/` is ignored by Git and contains shallow clones for study only.
- Tracked manifest: `docs/source_references.md`.

Cloned upstream references:

- Caveman: `external_sources/caveman`, upstream `https://github.com/JuliusBrussee/caveman`, current shallow head `84cc3c1`.
- OpenAI Codex CLI: `external_sources/codex`, upstream `https://github.com/openai/codex`, current shallow head `2a17b32`.
- Claude Code public repo: `external_sources/claude-code`, upstream `https://github.com/anthropics/claude-code`, current shallow head `0385848`.

Important source boundary:

- Do not vendor or republish third-party source in Stagewarden.
- Do not use leaked or unofficial Claude Code mirrors.
- Prefer reimplementing behavior from documented interfaces and observed public source.
- Copy code only when the upstream license permits it and attribution is added.

Study targets to extract into Stagewarden:

- Codex `tui/src/status/card.rs`: status card structure, configurable status line items, model/account/sandbox/approval display.
- Codex protocol model: token usage updates, rate-limit snapshots, model reroute events, auth status responses.
- Codex auth flow: `codex login status`, device/browser login, ChatGPT plan usage-limit parsing, retry-until time extraction.
- Codex sandbox/approval model: read-only/workspace-write/full-access, command approval decisions, network approval context.
- Claude Code public docs/plugins: plugin packaging, command discovery, setup conventions.
- Claude Code npm bundle, official package only: `claude auth status`, rate-limit headers, `rate_limit_event`, `resetsAt`, `rateLimitType`, `overageStatus`, `billing_error`, `authentication_failed`.
- Caveman: command grammar, hook activation, statusline integration, compression skills, benchmark/test structure.

Next implementation candidates:

- Add `sources update` command that runs `git pull --ff-only` in each reference repo and writes a handoff event with old/new heads.
- Add `sources status --strict` for CI/operator preflight checks.
- Extend Stagewarden `status` remediation output with explicit next commands for incomplete PRINCE2 role baseline, active exception plan, dirty git state, and blocked provider limits.
- Add Claude-style provider-limit fields: `rate_limit_type`, `utilization`, `resets_at`, `overage_status`, `overage_resets_at`, `overage_disabled_reason`.

## Status Research: Codex and Claude

Status: completed initial study

Detailed notes:

- `docs/status_research.md`

Codex findings to implement:

- Treat status as a full operational dashboard, not only login state.
- Render model, provider, cwd, permissions, agents, account, thread/session, token usage, context window, limits, credits, and stale/missing limit state.
- Use a 15-minute stale threshold for provider-limit snapshots.
- Represent limits as primary and secondary windows with `usedPercent`, `windowDurationMins`, and `resetsAt`.
- Represent credits separately with `hasCredits`, `unlimited`, and `balance`.
- Use `rateLimitReachedType` to distinguish generic rate limit from workspace credits/usage exhaustion.
- Never print raw auth tokens; Codex only includes tokens when explicitly requested by app-server clients.

Claude findings to implement:

- Expose auth status as machine-readable JSON equivalent to `claude auth status --json`.
- Track statusline-style fields: workspace, version, model, output style, context window, current usage, worktree, and rate limits.
- Track Claude rate-limit events with `status`, `resetsAt`, `rateLimitType`, `utilization`, `overageStatus`, `overageResetsAt`, `overageDisabledReason`, `isUsingOverage`, and `surpassedThreshold`.
- Distinguish `authentication_failed`, `billing_error`, `rate_limit`, `invalid_request`, `server_error`, `unknown`, and `max_output_tokens`.
- Surface long retry/reset waits immediately so the agent does not appear stuck.

Backlog from study:

- Add `status --full` grouped as Identity, Model, Account, Limits, Workspace, Permissions, Git, Handoff, Usage, Quality Gates.
- Add `statusline --json` for prompt/status scripts.
- Add `auth status <provider> --json` wrappers for Codex/OpenAI and Claude without token disclosure.
- Extend provider-limit persistence with Claude overage/rate-limit fields.
- Add token/context-window accounting to handoff and memory events.
- Add tests for status redaction, stale limits, missing limits, provider auth status, and JSON schema stability.

## Status Implementation Pass

Status: implemented partial

Implemented:

- `stagewarden status --full` and `stagewarden "status full"` render a Codex-style grouped dashboard.
- `stagewarden status --full --json` returns sections: identity, model, account, limits, workspace, permissions, git, handoff, usage, quality_gates.
- `stagewarden statusline --json` returns a Claude-style compact JSON surface for prompt/status scripts.
- `stagewarden auth status chatgpt --json` shells to `codex login status` and reports login state without token output.
- `stagewarden auth status claude --json` shells to `claude auth status --json` and reports login state without token output.
- CLI parser now accepts unquoted multi-word commands such as `stagewarden auth status chatgpt --json`.
- Read-only status commands use a read-only agent configuration and no longer create Git snapshots.

Validation:

- `python3 -m unittest tests/test_trace_cli.py` passed with 77 tests.
- Wet-run `python3 -m stagewarden.main status --full --json` passed.
- Wet-run `python3 -m stagewarden.main statusline --json` passed.
- Wet-run `python3 -m stagewarden.main auth status chatgpt --json` passed and detected ChatGPT login through Codex.
- Wet-run `python3 -m stagewarden.main auth status claude --json` passed and detected not-logged-in Claude state.

Remaining:

- Persist real provider-limit windows/credits when upstream CLIs expose them.
- Add first-class Claude overage fields to `.stagewarden_models.json` instead of only dashboard placeholders.
- Add token/context-window accounting from actual model calls.

<!-- STAGEWARDEN_RUNTIME_HANDOFF_START -->
## Runtime Handoff Export

Generated: 2026-04-19T11:06:05

### Current State

- task: unknown
- project_status: idle
- plan_status: unknown
- recovery_state: none
- stage_health: stable
- next_action: review current handoff and confirm next stage
- current_step: none
- git_boundary: baseline=unknown current=unknown
- pid_boundary: project_status=idle updated_at=2026-04-19T09:06:05+00:00

### Registers

governance=clean risks_open=0 risks_closed=0 issues_open=0 issues_closed=0 quality_open=0 quality_accepted=0 exception_plan_items=0

### Implementation Backlog

Implementation backlog:
- none

### Risks

Risk register:
- none

### Issues

Issue register:
- none

### Quality

Quality register:
- none

### Lessons

Lessons log:
- none

### Recent Entries

- none

<!-- STAGEWARDEN_RUNTIME_HANDOFF_END -->
