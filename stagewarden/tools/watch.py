from __future__ import annotations

from dataclasses import dataclass
import os
import time
from pathlib import Path
from typing import Any

try:  # Optional dependency.
    from watchdog.events import FileSystemEventHandler  # type: ignore
    from watchdog.observers import Observer  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    FileSystemEventHandler = object  # type: ignore[assignment]
    Observer = None


@dataclass(slots=True)
class WatchResult:
    ok: bool
    command: str
    message: str
    path: str | None = None
    duration_ms: int = 0
    items: list[dict[str, str]] | None = None
    error_type: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "message": self.message,
            "path": self.path,
            "duration_ms": self.duration_ms,
            "items": list(self.items or []),
            "error_type": self.error_type,
            "error": self.error,
        }


class WatchTool:
    def __init__(self, workspace_root: Path, *, timeout_seconds: float = 2.0, max_events: int = 100, poll_interval: float = 0.2) -> None:
        self.workspace_root = workspace_root.resolve()
        self.timeout_seconds = timeout_seconds
        self.max_events = max_events
        self.poll_interval = poll_interval

    def watch(self, path: str = ".", *, timeout_seconds: float | None = None, recursive: bool = True, poll_interval: float | None = None) -> WatchResult:
        started = time.monotonic()
        try:
            target = self._safe_path(path)
            timeout = max(0.1, float(timeout_seconds or self.timeout_seconds))
            interval = max(0.05, float(poll_interval or self.poll_interval))
            if Observer is not None:
                items = self._watch_with_watchdog(target, timeout=timeout, recursive=recursive)
            else:
                items = self._watch_with_polling(target, timeout=timeout, recursive=recursive, interval=interval)
            message = f"Observed {len(items)} filesystem event(s)."
            return WatchResult(True, "watch", message, path=self._display_path(target), duration_ms=self._elapsed_ms(started), items=items)
        except (OSError, ValueError) as exc:
            return self._error("watch", str(exc), started, path=path)

    def _watch_with_watchdog(self, target: Path, *, timeout: float, recursive: bool) -> list[dict[str, str]]:
        base_path = target.parent if target.is_file() else target
        target_file = target if target.is_file() else None
        self_outer = self

        class Handler(FileSystemEventHandler):  # type: ignore[misc]
            def __init__(self) -> None:
                self.items: list[dict[str, str]] = []

            def on_any_event(self, event) -> None:  # noqa: ANN001
                src_path = getattr(event, "src_path", "") or ""
                dest_path = getattr(event, "dest_path", "") or ""
                if target_file is not None:
                    if Path(src_path).resolve() != target_file.resolve() and (not dest_path or Path(dest_path).resolve() != target_file.resolve()):
                        return
                self.items.append(
                    {
                        "event_type": getattr(event, "event_type", "unknown"),
                        "src_path": self._display_path(Path(src_path)) if src_path else "",
                        "dest_path": self._display_path(Path(dest_path)) if dest_path else "",
                        "is_directory": str(bool(getattr(event, "is_directory", False))),
                    }
                )

            def _display_path(self, candidate: Path) -> str:
                try:
                    return str(candidate.resolve().relative_to(self_outer.workspace_root))
                except Exception:
                    return str(candidate)

        handler = Handler()
        observer = Observer()
        observer.schedule(handler, str(base_path), recursive=recursive if not target.is_file() else False)
        observer.start()
        try:
            time.sleep(timeout)
        finally:
            observer.stop()
            observer.join(timeout=max(1.0, timeout))
        return handler.items[: self.max_events]

    def _watch_with_polling(self, target: Path, *, timeout: float, recursive: bool, interval: float) -> list[dict[str, str]]:
        baseline = self._snapshot(target, recursive=recursive)
        items: list[dict[str, str]] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(items) < self.max_events:
            time.sleep(interval)
            current = self._snapshot(target, recursive=recursive)
            items.extend(self._diff_snapshots(baseline, current))
            baseline = current
            if items:
                break
        return items

    def _snapshot(self, target: Path, *, recursive: bool) -> dict[str, tuple[int, int]]:
        if target.is_file():
            stat = target.stat()
            return {str(target): (int(stat.st_mtime_ns), int(stat.st_size))}
        snapshot: dict[str, tuple[int, int]] = {}
        for root, dirs, files in os.walk(target):
            for name in list(files) + list(dirs):
                candidate = Path(root) / name
                try:
                    stat = candidate.stat()
                except OSError:
                    continue
                snapshot[str(candidate)] = (int(stat.st_mtime_ns), int(stat.st_size))
            if not recursive:
                break
        return snapshot

    def _diff_snapshots(self, baseline: dict[str, tuple[int, int]], current: dict[str, tuple[int, int]]) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for path in sorted(set(current) - set(baseline)):
            items.append({"event_type": "created", "path": self._display_path(Path(path))})
        for path in sorted(set(baseline) - set(current)):
            items.append({"event_type": "deleted", "path": self._display_path(Path(path))})
        for path in sorted(set(current) & set(baseline)):
            if current[path] != baseline[path]:
                items.append({"event_type": "modified", "path": self._display_path(Path(path))})
        return items

    def _safe_path(self, path: str) -> Path:
        candidate = (self.workspace_root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if candidate != self.workspace_root and self.workspace_root not in candidate.parents:
            raise ValueError("Path must stay inside the workspace.")
        return candidate

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.workspace_root))
        except Exception:
            return str(path)

    def _elapsed_ms(self, started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    def _error(self, command: str, message: str, started: float, *, path: str | None = None) -> WatchResult:
        return WatchResult(False, command, message, path=path, duration_ms=self._elapsed_ms(started), error_type="watch_error", error=message)
