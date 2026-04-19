# Stagewarden

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Autore: Donato Pepe
Licenza: MIT

Stagewarden is a production-grade CLI coding agent for controlled software delivery, with Codex-style agent loops, multi-model routing, PRINCE2-aligned governance, structured traces, and safe file/shell execution.

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
- The agent plans in the handoff context, executes one controlled action, updates the same handoff, and records the current `git HEAD`.
- The handoff file is persisted as `.stagewarden_handoff.json`.
- Resume is implicit: each new run inherits the latest project handoff context for the workspace.
- The executor prompt always includes the current project handoff summary, so planning and execution stay aligned to the same controlled context.
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

Inside the shell:

```text
stagewarden> help
stagewarden> models
stagewarden> model use openai
stagewarden> model list claude
stagewarden> model variant claude opus
stagewarden> model variant openai gpt-5.4-mini
stagewarden> model block openai until 2026-05-01T18:30
stagewarden> model unblock openai
stagewarden> status
stagewarden> boundary
stagewarden> risks
stagewarden> issues
stagewarden> quality
stagewarden> exception
stagewarden> lessons
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

Model control:

- `models` shows enabled, active, preferred, blocked, and backend state.
- `model use <local|cheap|chatgpt|openai|claude>` pins a preferred model.
- `model add <local|cheap|chatgpt|openai|claude>` enables a model.
- `model list <provider>` shows the official aliases or model IDs supported for that provider.
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
- If no variant is pinned, Stagewarden now selects one automatically from task complexity:
  - `claude`: prefers `haiku` for simple tasks, `sonnet` for normal coding, `opus` for harder debugging, and `opusplan` for explicit planning/design work.
  - `openai`: prefers `gpt-5.4-mini` for light work, `gpt-5.2-codex` for normal coding, and `gpt-5.4` for harder debugging or risky changes.
  - `chatgpt`: prefers `codex-mini-latest` for light work, `gpt-5.1-codex-mini` for standard execution, and `gpt-5.3-codex` for harder debugging sessions.

Stagewarden also records online model usage-limit messages such as `try again at 8:05 PM` and automatically blocks that model until the reported local time.

Project handoff:

- The human-readable implementation handoff lives in [`HANDOFF.md`](HANDOFF.md).
- Runtime handoff remains in `.stagewarden_handoff.json`; `HANDOFF.md` tracks the durable roadmap and Codex/Claude-inspired implementation backlog.

Interactive permission commands:

- `permissions` shows the active workspace permission settings.
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
