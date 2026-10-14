from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_MEMORY_FILES = (
    "MEMORY.md",
    "pi-memory.md",
    "preferences.md",
    "projects.md",
    "decisions.md",
    "conversation-log.md",
)

@dataclass(frozen=True, slots=True)
class MemoryContextIssue:
    level: str
    message: str
    path: str = ""

@dataclass(frozen=True, slots=True)
class MemoryContext:
    enabled: bool
    content: str
    files: tuple[str, ...]
    issues: tuple[MemoryContextIssue, ...]
    max_chars: int

    @property
    def ok(self) -> bool:
        return not any(issue.level == "error" for issue in self.issues)

    def report(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "ok": self.ok,
            "files": list(self.files),
            "issue_count": len(self.issues),
            "issues": [
                {"level": issue.level, "message": issue.message, "path": issue.path}
                for issue in self.issues
            ],
            "max_chars": self.max_chars,
            "content_chars": len(self.content),
        }


def _issue(level: str, message: str, path: Path | None = None) -> MemoryContextIssue:
    return MemoryContextIssue(level, message, str(path) if path else "")


def _safe_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _resolve_root(raw: object, workspace_root: Path, issues: list[MemoryContextIssue]) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        issues.append(_issue("error", "memory roots must contain non-empty strings"))
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    resolved = candidate.resolve()
    if not resolved.exists():
        issues.append(_issue("warning", "memory root does not exist", resolved))
        return None
    if not resolved.is_dir():
        issues.append(_issue("error", "memory root is not a directory", resolved))
        return None
    return resolved


def load_memory_context(
    workspace_root: Path,
    settings_path: Path,
    *,
    max_tokens: int | None = None,
    token_counter: Callable[[str], int] | None = None,
) -> MemoryContext:
    issues: list[MemoryContextIssue] = []
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return MemoryContext(False, "", (), (_issue("error", f"invalid workspace settings: {exc}", settings_path),), 12000)
    if not isinstance(payload, dict):
        return MemoryContext(False, "", (), (_issue("error", "workspace settings must be a JSON object", settings_path),), 12000)
    raw_memory = payload.get("memory", {})
    if raw_memory is None:
        raw_memory = {}
    if not isinstance(raw_memory, dict):
        return MemoryContext(False, "", (), (_issue("error", "memory settings must be an object"),), 12000)
    enabled = bool(raw_memory.get("enabled", False))
    max_chars = _safe_int(raw_memory.get("max_chars", 12000), 12000, minimum=500, maximum=100000)
    if not enabled:
        return MemoryContext(False, "", (), tuple(issues), max_chars)

    raw_roots = raw_memory.get("roots", [])
    if isinstance(raw_roots, str):
        raw_roots = [raw_roots]
    if not isinstance(raw_roots, list) or not raw_roots:
        issues.append(_issue("error", "enabled memory requires non-empty roots"))
        return MemoryContext(True, "", (), tuple(issues), max_chars)
    roots = [root for raw in raw_roots if (root := _resolve_root(raw, workspace_root, issues)) is not None]
    if not roots:
        return MemoryContext(True, "", (), tuple(issues), max_chars)

    raw_files = raw_memory.get("files", list(DEFAULT_MEMORY_FILES))
    if isinstance(raw_files, str):
        raw_files = [raw_files]
    if not isinstance(raw_files, list) or not raw_files or any(not isinstance(item, str) or not item.strip() for item in raw_files):
        issues.append(_issue("error", "memory files must be a non-empty list of strings"))
        return MemoryContext(True, "", (), tuple(issues), max_chars)

    chunks: list[str] = []
    loaded: list[str] = []
    for root in roots:
        for raw_file in raw_files:
            relative = Path(raw_file)
            if relative.is_absolute():
                issues.append(_issue("error", "memory file must be relative to configured root", relative))
                continue
            target = (root / relative).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                issues.append(_issue("error", "memory file escapes configured root", target))
                continue
            if target.suffix.lower() not in {".md", ".markdown"}:
                issues.append(_issue("error", "memory file must be Markdown", target))
                continue
            if not target.exists():
                issues.append(_issue("warning", "optional memory file missing", target))
                continue
            if not target.is_file():
                issues.append(_issue("error", "memory path is not a file", target))
                continue
            try:
                text = target.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError) as exc:
                issues.append(_issue("error", f"cannot read memory file: {exc}", target))
                continue
            if text:
                chunks.append(f"## {target.name}\n{text}")
                loaded.append(str(target))
    content = "\n\n".join(chunks)
    if len(content) > max_chars:
        content = content[:max_chars].rstrip() + "\n[truncated by memory.max_chars]"
    if max_tokens is not None:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 0:
            issues.append(_issue("error", "max_tokens must be a non-negative integer"))
            return MemoryContext(True, "", tuple(loaded), tuple(issues), max_chars)
        if token_counter is None:
            issues.append(_issue("error", "token_counter is required when max_tokens is set"))
            return MemoryContext(True, "", tuple(loaded), tuple(issues), max_chars)
        try:
            token_count = token_counter(content)
            if isinstance(token_count, bool) or not isinstance(token_count, int) or token_count < 0:
                raise ValueError("token counter returned invalid count")
            if token_count > max_tokens:
                suffix = "\\n[truncated by memory token budget]"
                low, high = 0, len(content)
                while low < high:
                    middle = (low + high + 1) // 2
                    candidate = content[:middle].rstrip() + suffix
                    if token_counter(candidate) <= max_tokens:
                        low = middle
                    else:
                        high = middle - 1
                candidate = content[:low].rstrip() + suffix
                content = candidate if token_counter(candidate) <= max_tokens else ""
        except Exception as exc:
            issues.append(_issue("error", f"token counting failed: {exc}"))
            return MemoryContext(True, "", tuple(loaded), tuple(issues), max_chars)
    return MemoryContext(True, content, tuple(loaded), tuple(issues), max_chars)


def render_memory_context(context: MemoryContext) -> str:
    if not context.enabled:
        return "Memory context disabled."
    if not context.content:
        return "Memory context enabled but no readable Markdown files were loaded."
    return context.content
