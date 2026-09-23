#!/usr/bin/env python3
"""Run small repository hygiene checks used by unified validation matrix."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_ROOTS = (
    ROOT / "README.md",
    ROOT / "README_IT.md",
    ROOT / "AGENT_MANIFESTO.md",
    ROOT / "AGENT_POLICY.md",
    ROOT / "AGENTS.md",
    ROOT / "AGENT_HANDOFF.md",
    ROOT / "HANDOFF.md",
    ROOT / "TODO.md",
    ROOT / "ROADMAP.md",
    ROOT / "docs",
)


def markdown_files() -> list[Path]:
    files: list[Path] = []
    for item in DOC_ROOTS:
        if item.is_file() and item.suffix.lower() == ".md":
            files.append(item)
        elif item.is_dir():
            files.extend(sorted(item.rglob("*.md")))
    return sorted(set(files))


def check_docs() -> list[str]:
    errors: list[str] = []
    files = markdown_files()
    for path in files:
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{path}: invalid UTF-8: {exc}")
            continue
        if data.startswith(b"\xef\xbb\xbf"):
            errors.append(f"{path}: UTF-8 BOM")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            target = target.split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            candidate = (path.parent / target).resolve()
            if not candidate.exists():
                errors.append(f"{path}: missing link target {target}")
    print(f"docs_checked={len(files)}")
    print(f"docs_errors={len(errors)}")
    for error in errors:
        print(error, file=sys.stderr)
    return errors


def check_diff() -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--check"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="", file=sys.stderr)
        return ["git diff --check failed"]
    print("git_diff_check=ok")
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-only", action="store_true", help="Skip git diff check.")
    args = parser.parse_args(argv)
    errors = check_docs()
    if not args.docs_only:
        errors.extend(check_diff())
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
