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
stagewarden> model use gpt
stagewarden> model block gpt until 2026-05-01T18:30
stagewarden> model unblock gpt
stagewarden> status
stagewarden> mode caveman ultra
stagewarden> mode normal
stagewarden> caveman on ultra
stagewarden> fix failing tests
stagewarden> quit
```

Model control:

- `models` shows enabled, active, preferred, blocked, and backend state.
- `model use <local|cheap|gpt|claude>` pins a preferred model.
- `model add <local|cheap|gpt|claude>` enables a model.
- `model remove <local|cheap|gpt|claude>` disables a model.
- `model block <model> until YYYY-MM-DDTHH:MM` blocks a model until a date and time.
- `model unblock <model>` removes a temporary block.
- `model clear` restores automatic routing.

Stagewarden also records online model usage-limit messages such as `try again at 8:05 PM` and automatically blocks that model until the reported local time.

Account profiles:

Stagewarden can keep multiple account profiles for the same provider. Secrets are not stored in the repository or model config; profiles store only the environment variable name that already contains the token.

```text
stagewarden> account add gpt lavoro OPENAI_API_KEY_WORK
stagewarden> account add gpt personale OPENAI_API_KEY_PERSONAL
stagewarden> account use gpt lavoro
stagewarden> account block gpt lavoro until 2026-05-01T18:30
stagewarden> account unblock gpt lavoro
stagewarden> accounts
```

Runtime behavior:

- Stagewarden calls `RUN_MODEL: gpt:lavoro <prompt>` internally.
- The external `run_model` command still receives `run_model gpt "<prompt>"`.
- Stagewarden sets `STAGEWARDEN_MODEL_ACCOUNT=lavoro` and `STAGEWARDEN_MODEL_TARGET=gpt:lavoro`.
- If `OPENAI_API_KEY_WORK` exists, Stagewarden maps it to `OPENAI_API_KEY` only for that subprocess.
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

- The Caveman mode and related command ergonomics were inspired by [caveman](https://github.com/JuliusBrussee/caveman) by Julius Brussee.
- Stagewarden is an independent project and does not include Caveman source code.

Credits:

- UX direction and agent-loop ergonomics were influenced by Codex-style CLI workflows.
- Caveman-inspired command ergonomics and mode design draw from [caveman](https://github.com/JuliusBrussee/caveman) by Julius Brussee.
- Stagewarden implementation, package structure, routing, handoff system, persistence, tests, and project integration are original work for this repository.
