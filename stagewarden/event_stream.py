from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterable


class EventStream:
    """Append-only redacted JSONL event stream with deterministic replay."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event: str, *, tree_id: str, node_id: str | None = None, parent_node_id: str | None = None, purpose: str = "", message: str = "", **details: Any) -> dict[str, Any]:
        payload = {
            "event": event,
            "tree_id": tree_id,
            "node_id": node_id,
            "parent_node_id": parent_node_id,
            "purpose": purpose,
            "message": message,
            "details": _redact(details),
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
        return payload

    def read(self, *, node_id: str | None = None, event: str | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            if node_id is not None and item.get("node_id") != node_id:
                continue
            if event is not None and item.get("event") != event:
                continue
            events.append(item)
        return events

    def follow(self, node_id: str, *, event: str | None = None) -> list[dict[str, Any]]:
        """Return ordered events for one node; suitable for live/polling consumers."""
        return self.read(node_id=node_id, event=event)

    def replay(self, *, node_id: str | None = None) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        last_event: dict[str, Any] | None = None
        for event_item in self.read(node_id=node_id):
            event_node_id = event_item.get("node_id")
            if isinstance(event_node_id, str) and event_node_id:
                state = nodes.setdefault(event_node_id, {"node_id": event_node_id})
                state.update({key: event_item.get(key) for key in ("parent_node_id", "purpose") if event_item.get(key) is not None})
                state["last_event"] = event_item.get("event")
                state["message"] = event_item.get("message", "")
                details = event_item.get("details")
                if isinstance(details, dict):
                    state.update({
                        key: details.get(key)
                        for key in ("context_revision", "summary_ref", "remaining_input_tokens")
                        if key in details
                    })
                    if event_item.get("event") == "mutation_recovery":
                        state["mutation_key"] = details.get("mutation_key")
                        state["mutation_status"] = details.get("status") or "recovered"
                    node = details.get("node")
                    if isinstance(node, dict):
                        state.update({
                            key: node.get(key)
                            for key in (
                                "status", "active_work", "output_summary", "error_message",
                                "cycle_id", "cycle_phase", "context_revision", "last_checkpoint",
                            )
                            if key in node
                        })
            last_event = event_item
        return {"tree_id": last_event.get("tree_id") if last_event else None, "nodes": nodes, "last_event": last_event}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("secret", "password", "api_key", "authorization")):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = _redact(item)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
