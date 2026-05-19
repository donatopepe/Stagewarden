from __future__ import annotations

from . import cli_dispatch as _cli_dispatch


BASELINE_CAPABILITY_GROUPS: tuple[dict[str, object], ...] = (
    {
        "id": "interactive_shell",
        "source": "codex_cli+claude_code",
        "required_commands": ("help", "slash", "slash choose", "status", "statusline", "preflight", "doctor"),
        "description": "Interactive shell, slash discovery, compact status, and readiness checks.",
    },
    {
        "id": "model_provider_control",
        "source": "codex_cli+claude_code",
        "required_commands": ("models", "model list", "model choose", "model params", "model limits", "model use"),
        "description": "Provider/model selection, parameter visibility, usage limits, and routing control.",
    },
    {
        "id": "account_auth",
        "source": "codex_cli+claude_code",
        "required_commands": ("accounts", "auth status", "account login", "account use", "account logout"),
        "description": "Provider account profiles, browser login where supported, status, selection, and logout.",
    },
    {
        "id": "workspace_tools",
        "source": "codex_cli+claude_code",
        "required_commands": ("shell backend", "sessions", "file inspect", "file stat", "file copy", "file move", "file delete", "git status", "git log", "git history"),
        "description": "Cross-platform shell execution, persistent sessions, file operations, and git history.",
    },
    {
        "id": "permission_safety",
        "source": "codex_cli+claude_code",
        "required_commands": ("permissions", "permission mode", "permission allow", "permission ask", "permission deny"),
        "description": "Explicit permission modes and allow/ask/deny governance.",
    },
    {
        "id": "handoff_resume_trace",
        "source": "codex_cli+claude_code",
        "required_commands": ("handoff", "handoff actions", "resume", "transcript", "report", "board"),
        "description": "Resume context, transcript visibility, action history, and board/report surfaces.",
    },
    {
        "id": "agent_governance",
        "source": "stagewarden_prince2+codex_goals",
        "required_commands": ("goal", "goal set", "goal status", "roles runtime", "roles control", "roles messages", "role message", "roles tick"),
        "description": "Persisted goal, PRINCE2 runtime nodes, governed node messaging, and orchestration.",
    },
    {
        "id": "external_sources_extensions",
        "source": "codex_cli+claude_code+caveman",
        "required_commands": ("sources", "sources update", "web search", "download", "extensions", "extension scaffold", "caveman help"),
        "description": "Source-study refresh, governed external IO, extension discovery, and Caveman mode.",
    },
)


BASELINE_REMEDIATION_BY_GROUP: dict[str, str] = {
    "interactive_shell": "Run `/help`, `/slash`, `/status`, and `/preflight`; restore missing command catalog entries before changing shell UX.",
    "model_provider_control": "Run `/models`, `/model list`, `/model choose`, and `/model limits`; restore provider routing surfaces before model work.",
    "account_auth": "Run `/accounts` and `/auth status <provider>`; restore account login/use/logout surfaces before auth changes.",
    "workspace_tools": "Run `/shell backend`, `/file stat <path>`, and `/git status`; restore file, shell, and git tools before delivery work.",
    "permission_safety": "Run `/permissions`; restore permission mode and allow/ask/deny controls before executing risky tools.",
    "handoff_resume_trace": "Run `/handoff`, `/handoff actions`, `/resume --show`, and `/transcript`; restore traceability before autonomous work.",
    "agent_governance": "Run `/goal`, `/roles runtime`, and `/roles control`; restore PRINCE2 goal/runtime governance before role-routed work.",
    "external_sources_extensions": "Run `/sources status --strict`, `/extensions`, and `/caveman help`; restore source and extension surfaces before source-derived changes.",
}


def main() -> int:
    return _cli_dispatch.run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
