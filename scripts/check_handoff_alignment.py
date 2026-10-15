#!/usr/bin/env python3
"""Check AGENT_HANDOFF.md, HANDOFF.md and .stagewarden_handoff.json stay aligned.

The repository protocol (AGENTS.md) requires the three handoff artifacts to stay
in sync. This check validates structure only, so it stays deterministic, offline
and free of false positives on free-form prose:

- `AGENT_HANDOFF.md` contains every required section heading.
- `HANDOFF.md` exists and is non-empty.
- `.stagewarden_handoff.json` is a JSON object with the required keys and a
  non-empty `waiting_reason`.

Exit code 0 means aligned, 1 means at least one structural problem.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_SECTIONS: tuple[str, ...] = (
    "## Current objective",
    "## Current state",
    "## Recent changes",
    "## Important files",
    "## Technical decisions",
    "## Open issues",
    "## Next steps",
    "## Commands",
)

REQUIRED_JSON_KEYS: tuple[str, ...] = (
    "status",
    "waiting_reason",
    "current_step_id",
    "current_step_title",
    "current_step_status",
)


def check(root: Path) -> list[str]:
    errors: list[str] = []
    agent_handoff = root / "AGENT_HANDOFF.md"
    legacy_handoff = root / "HANDOFF.md"
    state_file = root / ".stagewarden_handoff.json"

    if not agent_handoff.is_file():
        errors.append("AGENT_HANDOFF.md is missing")
    else:
        text = agent_handoff.read_text(encoding="utf-8", errors="replace")
        for section in REQUIRED_SECTIONS:
            if section not in text:
                errors.append(f"AGENT_HANDOFF.md missing required section: {section}")

    if not legacy_handoff.is_file():
        errors.append("HANDOFF.md is missing")
    elif not legacy_handoff.read_text(encoding="utf-8", errors="replace").strip():
        errors.append("HANDOFF.md is empty")

    if not state_file.is_file():
        errors.append(".stagewarden_handoff.json is missing")
        return errors

    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f".stagewarden_handoff.json is not valid JSON: {exc}")
        return errors

    if not isinstance(payload, dict):
        errors.append(".stagewarden_handoff.json must be a JSON object")
        return errors
    for key in REQUIRED_JSON_KEYS:
        if key not in payload:
            errors.append(f".stagewarden_handoff.json missing key: {key}")
    reason = payload.get("waiting_reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append(".stagewarden_handoff.json waiting_reason must be a non-empty string")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    errors = check(Path(args.root).resolve())
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"handoff_alignment=error count={len(errors)}")
        return 1
    print("handoff_alignment=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
