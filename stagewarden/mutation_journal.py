from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any


class MutationJournal:
    """Append-only idempotency journal for mutating file actions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @staticmethod
    def key(action_type: str, action: dict[str, Any]) -> str:
        canonical = json.dumps({"type": action_type, "action": action}, sort_keys=True, ensure_ascii=True)
        return "mutation:" + hashlib.sha256(canonical.encode()).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        for line in reversed(self.path.read_text(encoding="utf-8").splitlines()):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("key") == key:
                return item
        return None

    def append(self, *, key: str, action_type: str, path: str, status: str, message: str) -> dict[str, Any]:
        item = {"key": key, "action_type": action_type, "path": path, "status": status, "message": message}
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=True, sort_keys=True) + "\n")
        return item

    def list(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        items: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            if status is not None and item.get("status") != status:
                continue
            items.append(item)
        return items[-max(1, int(limit)):]
