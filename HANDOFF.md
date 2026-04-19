# Stagewarden Handoff

Author: Donato Pepe

License: MIT

Last updated: 2026-04-19

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

Latest pushed baseline at the time of this handoff:

- `bd6a6ec Document recovery boundary states`

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

Status: planned

Expose persistent handoff and logs to model prompts more deliberately.

Required behaviour:

- Include concise handoff summary in every model prompt.
- Include recent LJSON trace summary.
- Include current recovery state and backlog status.
- Include git boundary and dirty state.
- Keep prompt bounded with truncation rules.

Validation:

- Executor prompt tests assert handoff, recovery state, backlog, and git boundary are present.
- Prompt size remains bounded.

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

Status: planned

Even though Stagewarden uses implicit handoff resume, add explicit commands for operator control.

Required behaviour:

- `resume` starts from current handoff context.
- `resume --show` prints what will be resumed.
- `resume --clear` archives current handoff and starts fresh.
- Preserve implicit resume as default.

Validation:

- Resume command uses existing `current_step_id`.
- Clear command does not delete git history.
- Archived handoff remains inspectable.

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

Status: planned

Add a PRINCE2 board-level summary command.

Required behaviour:

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

Status: planned

Make cost control explicit in router and handoff.

Required behaviour:

- Track model usage count by run.
- Record model chosen per step in handoff.
- Add budget policy: prefer local, then cheap, then GPT/Claude for complex/failing tasks.
- Expose `cost` or `models usage` shell command.

Validation:

- Simple tasks choose local first.
- Failures escalate according to policy.
- Usage summary is visible in shell.

### 15. Cross-OS Setup Verification

Status: planned

Strengthen setup scripts for macOS, Linux, and Windows.

Required behaviour:

- Validate Python 3.11+.
- Validate git installed.
- Validate PATH launcher works.
- Provide `stagewarden doctor`.
- Do not auto-install git silently; report prerequisite clearly.

Validation:

- Setup script tests pass.
- Doctor command reports missing git/python clearly.

## Immediate Next Implementation Order

1. Patch preview command in the interactive shell, if direct manual preview becomes useful.
2. Model context files.
3. Resume command over handoff.
4. Cost-aware execution budget.
5. CLI help snapshot tests for Caveman category, if Caveman help changes.

## Validation Standard

Every implementation must include:

- unit tests
- integration or CLI tests where applicable
- wet-run verification
- git snapshot
- push to remote

Dry-run alone is not a valid checkpoint.
