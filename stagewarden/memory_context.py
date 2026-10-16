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

    def __post_init__(self) -> None:
        if not isinstance(self.level, str):
            raise TypeError("memory issue level must be a string")
        if not self.level.strip():
            raise ValueError("memory issue level must be a non-empty string")
        if not isinstance(self.message, str):
            raise TypeError("memory issue message must be a string")
        if not self.message.strip():
            raise ValueError("memory issue message must be a non-empty string")
        if not isinstance(self.path, str):
            raise TypeError("memory issue path must be a string")

    def __str__(self) -> str:
        return f"{self.level}: {self.message}" + (f" [{self.path}]" if self.path else "")

@dataclass(frozen=True, slots=True)
class MemoryContext:
    enabled: bool
    content: str
    files: tuple[str, ...]
    issues: tuple[MemoryContextIssue, ...]
    max_chars: int
    token_limit: int | None = None
    token_counter_name: str | None = None
    token_count: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("memory enabled flag must be a bool")
        if not isinstance(self.content, str):
            raise TypeError("memory content must be a string")
        if not isinstance(self.files, tuple) or any(not isinstance(item, str) for item in self.files):
            raise TypeError("memory files must be a tuple of strings")
        if not isinstance(self.issues, tuple) or any(not isinstance(item, MemoryContextIssue) for item in self.issues):
            raise TypeError("memory issues must be a tuple of MemoryContextIssue")
        if isinstance(self.max_chars, bool) or not isinstance(self.max_chars, int) or self.max_chars < 0:
            raise ValueError("max_chars must be a non-negative integer")
        for name in ("token_limit", "token_count"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if self.token_counter_name is not None and not isinstance(self.token_counter_name, str):
            raise TypeError("token_counter_name must be a string or None")
        if self.token_counter_name is not None and not self.token_counter_name.strip():
            raise ValueError("token_counter_name must be non-empty when provided")
        if self.token_limit is not None and self.token_count is None:
            raise ValueError("token_count is required when token_limit is set")
        if self.token_count is not None and self.token_limit is None:
            raise ValueError("token_limit is required when token_count is set")
        if self.token_limit is not None and self.token_count is not None and self.token_count > self.token_limit:
            raise ValueError("token_count must not exceed token_limit")

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
            "token_limit": self.token_limit,
            "token_counter": self.token_counter_name,
            "content_tokens": self.token_count,
            "diagnostics": [str(issue) for issue in self.issues],
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
    token_counter_name: str | None = None,
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
    final_token_count: int | None = None
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
                suffix = "\n[truncated by memory token budget]"
                suffix_count = token_counter(suffix)
                if isinstance(suffix_count, bool) or not isinstance(suffix_count, int) or suffix_count < 0:
                    raise ValueError("token counter returned invalid suffix count")
                if suffix_count > max_tokens:
                    issues.append(_issue("error", "token budget too small for truncation marker"))
                    return MemoryContext(True, "", tuple(loaded), tuple(issues), max_chars)
                else:
                    # Do not assume arbitrary pluggable counters are monotone over
                    # prefixes. Keep only candidates actually measured within budget;
                    # if a discontinuous estimator never finds one, fail closed empty.
                    source_content = content
                    end = len(source_content)
                    content = ""
                    fitted = False
                    while end > 0:
                        probe = source_content[:end].rstrip() + suffix
                        candidate_count = token_counter(probe)
                        if isinstance(candidate_count, bool) or not isinstance(candidate_count, int) or candidate_count < 0:
                            raise ValueError("token counter returned invalid count during compaction")
                        if candidate_count <= max_tokens:
                            content = probe
                            fitted = True
                            break
                        end //= 2
                    if not fitted:
                        issues.append(_issue("error", "no truncated memory candidate fits token budget"))
                        content = ""
                        return MemoryContext(True, "", tuple(loaded), tuple(issues), max_chars)
            try:
                final_token_count = token_counter(content)
                if isinstance(final_token_count, bool) or not isinstance(final_token_count, int) or final_token_count < 0:
                    raise ValueError("token counter returned invalid count")
            except Exception as exc:
                raise ValueError(f"token counter returned invalid count: {exc}") from exc
            if final_token_count > max_tokens:
                raise ValueError("compacted memory exceeds token budget")
        except Exception as exc:
            issues.append(_issue("error", f"token counting failed: {exc}"))
            return MemoryContext(
                True, "", tuple(loaded), tuple(issues), max_chars,
                token_counter_name=token_counter_name,
            )
        if any(issue.level == "error" for issue in issues):
            return MemoryContext(True, "", tuple(loaded), tuple(issues), max_chars, max_tokens, token_counter_name, final_token_count)
    return MemoryContext(True, content, tuple(loaded), tuple(issues), max_chars, max_tokens, token_counter_name, final_token_count)


def render_memory_context(context: MemoryContext) -> str:
    if not context.enabled:
        return "Memory context disabled."
    if not context.content:
        return "Memory context enabled but no readable Markdown files were loaded."
    return context.content


def character_counter(text: str) -> int:
    """Offline character-count token counter for injection; NOT provider tokens."""
    return len(text)
