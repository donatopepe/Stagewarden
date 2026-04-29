from __future__ import annotations

from typing import Final


JSON_SCHEMA_VERSION: Final[str] = "1"
JSON_SCHEMA_REGISTRY: Final[dict[str, str]] = {
    "status": "stagewarden.status",
    "statusline": "stagewarden.statusline",
    "overview": "stagewarden.overview",
    "health": "stagewarden.health",
    "preflight": "stagewarden.preflight",
    "report": "stagewarden.report",
    "handoff": "stagewarden.handoff",
    "boundary": "stagewarden.boundary",
    "board": "stagewarden.board",
    "doctor": "stagewarden.doctor",
    "models": "stagewarden.models",
    "model limits": "stagewarden.model_limits",
    "catalog status": "stagewarden.catalog_status",
    "catalog search": "stagewarden.catalog_search",
    "goal": "stagewarden.goal",
    "goal set": "stagewarden.goal_set",
    "goal status": "stagewarden.goal_status",
    "goal clear": "stagewarden.goal_clear",
    "help": "stagewarden.help",
    "commands": "stagewarden.commands",
    "slash": "stagewarden.slash",
    "slash choose": "stagewarden.slash_choose",
    "accounts": "stagewarden.accounts",
    "permissions": "stagewarden.permissions",
    "git status": "stagewarden.git_status",
    "git log": "stagewarden.git_log",
    "git history": "stagewarden.git_history",
    "git show": "stagewarden.git_show",
    "sessions": "stagewarden.sessions",
    "risks": "stagewarden.risks",
    "issues": "stagewarden.issues",
    "quality": "stagewarden.quality",
    "exception": "stagewarden.exception",
    "lessons": "stagewarden.lessons",
    "todo": "stagewarden.todo",
    "transcript": "stagewarden.transcript",
    "resume --show": "stagewarden.resume_show",
    "resume context": "stagewarden.resume_context",
    "models usage": "stagewarden.models_usage",
}


def json_schema(command: str) -> dict[str, str]:
    return {
        "name": JSON_SCHEMA_REGISTRY[command],
        "version": JSON_SCHEMA_VERSION,
    }


def json_schema_commands() -> tuple[str, ...]:
    return tuple(JSON_SCHEMA_REGISTRY)
