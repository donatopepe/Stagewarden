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
}


def json_schema(command: str) -> dict[str, str]:
    return {
        "name": JSON_SCHEMA_REGISTRY[command],
        "version": JSON_SCHEMA_VERSION,
    }


def json_schema_commands() -> tuple[str, ...]:
    return tuple(JSON_SCHEMA_REGISTRY)

