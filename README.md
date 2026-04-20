# Stagewarden

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Autore: Donato Pepe
Licenza: MIT

Stagewarden is a production-grade CLI coding agent for controlled software delivery, with Codex-style agent loops, multi-model routing, PRINCE2-aligned governance, structured traces, and safe file/shell execution.

Agent policy artifacts:

- `AGENT_MANIFESTO.md`: short operating manifesto
- `AGENT_POLICY.md`: formal human-readable policy
- `AGENT_POLICY.json`: machine-readable policy baseline

Caratteristiche principali:

- iterative agent loop
- planner and executor split
- model routing and escalation
- `RUN_MODEL:` handoff execution
- persistent PRINCE2 project handoff context with implicit resume
- declarative permission policy with workspace settings and session modes
- shell, file, and git tools
- cross-platform shell execution on macOS, Linux, and Windows
- local stub support for smoke tests

Install locally:

```bash
python3 -m pip install -e .
```

Prerequisites:

- Python 3.11+
- Git installed and available in `PATH`

Git is mandatory. Stagewarden initializes a repository automatically when needed and commits local snapshots of agent actions.

Git behavior:

- If the workspace has no `.git`, Stagewarden runs `git init` automatically.
- Runtime files are added to `.gitignore`.
- Stagewarden creates local commits for workspace snapshots during agent execution.
- If `git` is missing, the agent refuses to start.

Permissions behavior:

- Stagewarden now supports a workspace permission file: `.stagewarden_settings.json`
- The policy supports:
  - `defaultMode`
  - `allow`
  - `ask`
  - `deny`
- Supported modes:
  - `default`
  - `accept_edits`
  - `plan`
  - `auto`
  - `dont_ask`
- `plan` blocks mutating shell and file operations.
- `dont_ask` denies mutating operations unless explicitly allowed.
- `ask` rules currently fail closed in the CLI and require an explicit allow rule.

Minimal example:

```json
{
  "permissions": {
    "defaultMode": "plan",
    "allow": ["shell:git status"],
    "ask": ["file:secrets.txt"],
    "deny": ["shell:rm"]
  }
}
```

PRINCE2 handoff behavior:

- Stagewarden treats handoff as the live project context, not as an optional resume command.
- Stagewarden applies PRINCE2 adaptively: small tasks use the lightest viable governance, while complex or risky work increases staged control, validation evidence, and formal checkpoints.
- The agent does not drop PRINCE2 principles on small tasks; it reduces ceremony, not control intent.
- The agent plans in the handoff context, executes one controlled action, updates the same handoff, and records the current `git HEAD`.
- The handoff file is persisted as `.stagewarden_handoff.json`.
- Resume is implicit: each new run inherits the latest project handoff context for the workspace.
- The executor prompt always includes the current project handoff summary, so planning and execution stay aligned to the same controlled context.
- `stagewarden handoff --json` and `stagewarden "resume --show" --json` expose the same runtime state for automation.
- `stagewarden status --json` and `stagewarden boundary --json` expose operational posture and boundary control state for automation.
- `status` and `status --json` now also expose current multiprovider limit posture: model lockouts, blocked accounts, classified provider lockout reason, last known provider message, and latest routed success/failure context.
- `stagewarden board --json` or `stagewarden "stage review" --json` exposes the PRINCE2 board-level authorization recommendation.
- `stagewarden overview --json` aggregates status, board review, handoff, transcript, model-usage signals, and provider-limit posture into a single machine-readable snapshot.
- `stagewarden health --json` exposes a compact readiness snapshot for automation: authorization, boundary decision, open controls, recovery state, and minimal model/transcript signals.
- `stagewarden report --json` exposes a compact closure/shareable summary with governance state, next action, recent lessons, backlog preview, model activity, and provider-limit posture.
- `stagewarden risks|issues|quality|exception|lessons|todo --json` exposes PRINCE2 registers and backlog in machine-readable form.
- The executor prompt also includes the active PRINCE2 registers: risks, issues, quality evidence, lessons learned, and any current exception plan.
- The planner also reuses those registers to shape the next active step, so resumed work carries forward open risks, issues, quality evidence, lessons, and exception actions.
- `handoff` shows the full persisted project context, while `boundary` shows only the current PRINCE2 stage-boundary recommendation.
- `boundary` now blocks closure when open issues remain and prefers an explicit exception-path decision when an exception plan is active.
- On controlled project closure, Stagewarden now closes remaining open issues and risks and clears the exception plan when the project has recovered.
- On controlled project closure, Stagewarden also finalizes quality evidence by marking remaining quality entries as accepted.
- `boundary` and `handoff` now show both register counts and register closure state, so you can see open vs closed risks/issues and open vs accepted quality evidence.
- The final agent summary now includes a governance status line that tells you whether closure is `clean` or still has residual open controls.
- The interactive `status` and `handoff` views now include the same governance status line for consistency with the final agent summary.
- The interactive `status` and `handoff` views also show the current boundary decision directly, so you can see status plus control decision without switching to `boundary`.
- The interactive `status` and `handoff` views now also show the active stage in compact form.
- The interactive `status` and `handoff` views now also show the compact git boundary (baseline HEAD vs current HEAD).
- The interactive views now also show a compact `stage health` indicator such as `active`, `at_risk`, `exception`, or `ready_to_close`.
- The interactive views now also show a compact `next action` recommendation derived from the boundary decision and current stage state.
- The final summary, `status`, and `handoff` now reuse the same compact `operational posture` block so the high-level reading stays consistent across views.

Validation behavior:

- Every implementation must include relevant verification checks or tests.
- Dry-runs are not valid completion checkpoints by themselves.
- Steps close only with wet-run evidence such as executed tests, real commands, observed files, or real tool output.
- If the obvious wet-run is blocked, Stagewarden must find another feasible wet-run instead of accepting dry-run completion.

Quick setup:

macOS/Linux:

```bash
sh setup.sh
```

Windows PowerShell:

```powershell
.\setup.ps1
```

Platform-specific setup scripts:

```bash
sh scripts/setup_macos.sh
sh scripts/setup_linux.sh
```

```powershell
.\scripts\setup_windows.ps1
```

If editable installation cannot download build dependencies, setup falls back to a source launcher in the user bin/Scripts directory. The `stagewarden` command still runs from the checked-out repository through `PYTHONPATH`.

Prerequisite check:

```bash
stagewarden doctor
stagewarden doctor --json
stagewarden health
stagewarden health --json
stagewarden report
stagewarden report --json
```

`doctor` validates Python 3.11+, Git availability, PATH launcher visibility, repository state, and provider capabilities/token env expectations without installing anything or initializing git. Use `stagewarden doctor --json` for machine-readable automation output.
`health` is the compact operational variant for scripts and dashboards when `overview` is too broad and `board` is not enough.
`report` is the shareable operator summary for issue updates, project closure notes, or quick GitHub-ready status text.

Shell execution:

- macOS/Linux use `bash` when available, otherwise `sh`.
- Windows uses PowerShell when available, otherwise `cmd`.
- Shell sessions are persistent within an agent run and constrained to the workspace.

Run:

```bash
stagewarden "create a file named hello.txt"
```

Interactive shell:

```bash
stagewarden
```

On terminals with `readline` support, the shell also keeps a per-workspace history in `.stagewarden_history` and enables TAB completion for core commands plus selected workspace-path commands such as `git history` and `patch preview`.
During interactive task execution, Stagewarden now also forwards live `run_model` stdout into the shell with compact prefixes such as `[model-stream local]`, while still parsing the final JSON response normally.
Use `stream on`, `stream off`, or `stream status` inside the shell to control this behavior per session.
Task execution is visually split into `Running task: ...` and `Agent result:` so the live model stream stays distinct from the final agent summary.
The interactive shell also emits a compact `Shell progress (before|after)` block with active step, stage health, boundary decision, recovery state, and current git head.
These mini-blocks now also show the planned route before execution and the actual route after execution: model, account, and variant.
The `after` block also shows the latest local git checkpoint created during the run, so the shell immediately exposes the snapshot just recorded.
Between the full agent summary and the final progress block, the shell now also shows a focused `Last step outcome:` section with step id, action, status, route, and observed result.
That block now also exposes the concrete evidence source used for the last step, including tool name, tool action, and duration when available.
`handoff export` and `handoff md` now also include an `Execution Resume Context` block in `HANDOFF.md` with the latest model attempt, route, tool evidence, and git snapshot so resume stays implicit and auditable.

Inside the shell:

```text
stagewarden> help
stagewarden> help models
stagewarden> help handoff
stagewarden> models
stagewarden> patch preview changes.diff
stagewarden> model use openai
stagewarden> model list claude
stagewarden> model variant claude opus
stagewarden> model variant openai gpt-5.4-mini
stagewarden> model block openai until 2026-05-01T18:30
stagewarden> model unblock openai
stagewarden> status
stagewarden> health
stagewarden> report
stagewarden> stream status
stagewarden> stream off
stagewarden> boundary
stagewarden> risks
stagewarden> issues
stagewarden> quality
stagewarden> exception
stagewarden> lessons
stagewarden> transcript
stagewarden> todo
stagewarden> permissions
stagewarden> permission mode plan
stagewarden> permission session mode auto
stagewarden> permission allow shell:git status
stagewarden> permission session allow shell:python3 -m pytest
stagewarden> mode plan
stagewarden> mode auto
stagewarden> mode accept-edits
stagewarden> mode dont-ask
stagewarden> mode default
stagewarden> mode caveman ultra
stagewarden> mode normal
stagewarden> caveman on ultra
stagewarden> fix failing tests
stagewarden> quit
```

Interactive help is topic-based: `help` shows compact categories, while `help models`, `help accounts`, `help permissions`, `help handoff`, `help git`, `help caveman`, and `help ljson` show focused command examples.

Model control:

- `models` shows enabled, active, preferred, blocked, and backend state.
- `stagewarden models --json` exposes the same model routing state in machine-readable form.
- `models usage` or `cost` shows persisted model call counts, failures, step coverage, cost tiers, and the routing budget policy.
- `stagewarden "models usage" --json` emits the same data in machine-readable form.
- `model use <local|cheap|chatgpt|openai|claude>` pins a preferred model.
- `model add <local|cheap|chatgpt|openai|claude>` enables a model.
- `model list <provider>` shows the official aliases or model IDs and provider capabilities for that provider.
- `model variant <provider> <variant>` pins a provider-specific model alias or model ID.
- `model variant-clear <provider>` clears the variant override and returns to the provider default.
- `model remove <local|cheap|chatgpt|openai|claude>` disables a model.
- `model block <model> until YYYY-MM-DDTHH:MM` blocks a model until a date and time.
- `model unblock <model>` removes a temporary block.
- `model clear` restores automatic routing.

Provider model selection is aligned to public provider behavior:

- `openai` and `chatgpt` accept explicit OpenAI model IDs such as `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex`, `gpt-5.2-codex`, `gpt-5.1-codex`, and `codex-mini-latest`.
- `claude` accepts Claude Code style aliases such as `default`, `sonnet`, `opus`, `haiku`, `sonnet[1m]`, and `opusplan`.
- Stagewarden passes the selected variant to the backend via `STAGEWARDEN_MODEL_VARIANT` and the provider-native env var such as `OPENAI_MODEL` or `ANTHROPIC_MODEL`.
- Provider auth capabilities live in `stagewarden/provider_registry.py`: ChatGPT plan login is separate from OpenAI API-key profiles, Claude can use API keys or imported Claude Code credentials, and Stagewarden does not scrape hidden browser tokens.
- If no variant is pinned, Stagewarden now selects one automatically from task complexity:
  - `claude`: prefers `haiku` for simple tasks, `sonnet` for normal coding, `opus` for harder debugging, and `opusplan` for explicit planning/design work.
  - `openai`: prefers `gpt-5.4-mini` for light work, `gpt-5.2-codex` for normal coding, and `gpt-5.4` for harder debugging or risky changes.
  - `chatgpt`: prefers `codex-mini-latest` for light work, `gpt-5.1-codex-mini` for standard execution, and `gpt-5.3-codex` for harder debugging sessions.

Stagewarden also records online model usage-limit messages such as `try again at 8:05 PM` and automatically blocks that model until the reported local time.

Project handoff:

- The human-readable implementation handoff lives in [`HANDOFF.md`](HANDOFF.md).
- Runtime handoff remains in `.stagewarden_handoff.json`; `HANDOFF.md` tracks the durable roadmap and Codex/Claude-inspired implementation backlog.
- Use `handoff export` or `handoff md` to update the generated runtime section in `HANDOFF.md` from the current runtime handoff.
- `stagewarden "handoff export" --json` and `stagewarden "resume --clear" --json` expose structured operational results for export/reset workflows.
- Every model prompt includes bounded references to `.stagewarden_handoff.json`, `.stagewarden_memory.json`, and `.stagewarden_trace.ljson`, plus recovery state, backlog status, git boundary, and dirty state.
- `resume --show` previews the current handoff target, `resume --clear` archives and resets handoff, and `resume` reruns the task stored in handoff after reloading the context.
- `resume context` shows the latest implicit execution context: last model attempt, routed account/variant, tool evidence, and latest git snapshot.

Tool transcript:

- `transcript` or `trace` shows recent tool invocations from workspace memory.
- `stagewarden transcript --json` emits the recent tool transcript in machine-readable form.
- `stagewarden accounts --json` exposes configured provider profiles, active account, token-store state, and env mapping.
- Transcript entries are persisted in `.stagewarden_memory.json` using LJSON.

Persistent shell sessions:

- `sessions` or `session list` shows active shell sessions for the current Stagewarden process.
- `stagewarden sessions --json` exposes active shell sessions for the current Stagewarden process in machine-readable form.
- `session create [cwd]` starts a persistent shell in the workspace or a relative directory.
- `session send <id|last> <command>` runs one command in that session and returns marker-based output with exit code.
- `session close <id|last>` closes the session.
- Permission checks are applied to every `session send` command; session IDs are not persisted to the repository.

Patch workflow:

- Model actions can use `preview_patch_files` to validate a unified multi-file diff and get a per-file summary without writing.
- Interactive shell users can run `patch preview <diff-file>` to validate a unified diff file without writing.
- `patch_files` applies the same unified diff format and reports `add`, `update`, and `delete` entries per path.
- Duplicate targets in the same diff are rejected before writes, preventing ambiguous multi-hunk edits.
- In `plan` mode patch preview is allowed, while actual file writes remain blocked.

Model action schema:

- Model responses may use the strict schema `{summary, confidence, risks, validation, action}`.
- Simpler legacy responses with `{summary, action}` remain valid.
- Unknown destructive action types are denied before tool execution.

Interactive permission commands:

- `permissions` shows the active workspace permission settings.
- `stagewarden permissions --json` exposes workspace, session, and effective permission policy in machine-readable form.
- `permission mode <default|accept_edits|plan|auto|dont_ask>` changes the workspace default permission mode.
- `permission session mode <default|accept_edits|plan|auto|dont_ask>` changes the permission mode only for the current shell session.
- `permission allow <rule>` adds an allow rule.
- `permission ask <rule>` adds an ask rule.
- `permission deny <rule>` adds a deny rule.
- `permission session allow <rule>`, `permission session ask <rule>`, and `permission session deny <rule>` add temporary session-only rules.
- `permission session reset` clears all session permission overrides.
- `permission reset` resets the workspace permission file to defaults.
- `mode plan|auto|accept-edits|dont-ask|default` is a fast alias for changing the workspace permission mode.
- Interactive `ask` prompts support `y`, `n`, `always`, `session`, and `deny`; autonomous/non-interactive tool execution remains fail-closed.
- Shell permission classification distinguishes read-only git inspection from mutating git, redirection, package install, and other write/high-risk commands.

Handoff tracking:

- `handoff` now includes the persisted implementation backlog alongside stage posture, registers, and git boundary context.
- `todo` prints the current implementation backlog derived from the active PRINCE2 plan and kept in sync while the agent runs.
- The handoff backlog now uses normalized lifecycle states: `planned`, `ready`, `in_progress`, `blocked`, and `done`.
- `blocked` backlog items surface alongside exception handling so the shell can distinguish a blocked stage from a clean ready queue.
- The planner now promotes the first executable stage to `ready`, keeps later stages as `planned`, and the agent loop only starts stages that are `ready` or already `in_progress`.
- When a stage completes under control, the next `planned` stage is promoted automatically to `ready`.
- When a project enters `exception` with an active exception plan, the planner now injects an explicit recovery lane as `recovery-step-*` stages instead of only retrying the failed stage inline.
- Recovery stages participate in the same lifecycle gates and can be resumed from persisted handoff context like any other stage.
- The handoff boundary view now reports `recovery_state` as `exception_active`, `recovery_active`, `recovery_cleared`, or `none`.
- `recovery_active` drives the next action toward executing recovery stages; `recovery_cleared` drives cleanup of exception controls before normal execution resumes.
- Completed recovery lanes now close the recovery gate by clearing exception controls, closing open issues/risks with wet-run evidence, and resuming the next normal stage.

Account profiles:

Stagewarden can keep multiple account profiles for the same provider. Secrets are not stored in the repository or model config; profiles store only the environment variable name that already contains the token.

```text
stagewarden> account login chatgpt personale
stagewarden> account add openai lavoro OPENAI_API_KEY_WORK
stagewarden> account add openai personale OPENAI_API_KEY_PERSONAL
stagewarden> account login openai lavoro
stagewarden> account use openai lavoro
stagewarden> account block openai lavoro until 2026-05-01T18:30
stagewarden> account unblock openai lavoro
stagewarden> accounts
```

Runtime behavior:

- `chatgpt` is a provider distinct from `openai`.
- `chatgpt` expects a ChatGPT session token and maps it to `CHATGPT_TOKEN` for the backend subprocess.
- Stagewarden calls `RUN_MODEL: openai:lavoro <prompt>` internally.
- For ChatGPT plan access it calls `RUN_MODEL: chatgpt:personale <prompt>` internally.
- The external `run_model` command still receives `run_model openai "<prompt>"`.
- For ChatGPT plan access the external command receives `run_model chatgpt "<prompt>"`.
- Stagewarden sets `STAGEWARDEN_MODEL_ACCOUNT=lavoro` and `STAGEWARDEN_MODEL_TARGET=openai:lavoro`.
- If `OPENAI_API_KEY_WORK` exists, Stagewarden maps it to `OPENAI_API_KEY` only for that subprocess.
- `account login <model> <profile>` starts provider login and saves credentials in macOS Keychain when available. For `chatgpt` and `openai`, Stagewarden uses a Codex-style device-code OAuth flow.
- If no environment variable mapping exists, Stagewarden loads the saved profile token and maps it to the provider env var only for the subprocess.
- `chatgpt` and `openai` store OAuth-style credential payloads, not a copy-pasted browser token.
- For `chatgpt` and `openai`, `account login <profile>` follows the Codex-style account flow using device authorization and token exchange.
- For providers like `claude`, interactive browser callback login is disabled; use `account env` with the provider's official API key or credentials.
- If one account reports a usage limit, Stagewarden blocks that account until the reported time and retries another account for the same model before falling back to another model.

Git history commands:

```text
stagewarden> git status
stagewarden> git log 10
stagewarden> git history stagewarden/main.py 20
stagewarden> git show --stat HEAD
```

`stagewarden "git status" --json`, `stagewarden "git log 10" --json`, `stagewarden "git history path 10" --json`, and `stagewarden "git show --stat HEAD" --json` expose read-only repository inspection in machine-readable form.

The autonomous executor can also call `git_status`, `git_log`, `git_show`, and `git_file_history` as first-class tool actions when it needs to inspect modification history before deciding or changing code.

Caveman mode:

```text
stagewarden> status
stagewarden> mode caveman ultra
stagewarden> mode normal
stagewarden> caveman help
stagewarden> caveman on ultra
stagewarden> caveman review
stagewarden> caveman commit
stagewarden> caveman compress notes.md
stagewarden> caveman off
```

Acknowledgements:

- Thanks to Julius Brussee for [caveman](https://github.com/JuliusBrussee/caveman), which influenced the Caveman mode and parts of the command ergonomics.
- Thanks to the public OpenAI Codex CLI sources and documentation for clarifying authentication and provider-model selection patterns.
- Thanks to the public Claude Code sources and Anthropic documentation for the provider-specific model aliasing and credential-handling references.
- Stagewarden is an independent project and does not include source code from Caveman, Codex CLI, or Claude Code.
- Stagewarden implementation, package structure, routing, handoff system, persistence, tests, and project integration are original work for this repository.
