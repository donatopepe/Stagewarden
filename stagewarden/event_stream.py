from __future__ import annotations

import hashlib
import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


class EventStream:
    """Append-only redacted JSONL event stream with deterministic replay."""

    _path_locks_guard = threading.Lock()
    _path_locks: dict[str, threading.RLock] = {}

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_key = str(path.resolve())
        with self._path_locks_guard:
            self._lock = self._path_locks.setdefault(lock_key, threading.RLock())

    @contextmanager
    def _process_lock(self):
        """Serialize appends across processes using a sidecar advisory lock."""
        canonical_path = self.path.resolve()
        lock_path = canonical_path.with_name(canonical_path.name + ".lock")
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                if handle.read(1) == b"":
                    handle.seek(0)
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

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
        with self._lock, self._process_lock():
            integrity = self.verify_integrity()
            chain_errors = [item for item in integrity["errors"] if item["error"] != "invalid_json"]
            if integrity.get("chain_corrupted") or any(item["error"] in {"unchained_record_after_chain", "unchained_record_within_chain", "chain_after_legacy_records"} for item in integrity["errors"]):
                raise ValueError(f"Cannot append to corrupt event stream: {integrity['errors']}")
            chained_count = integrity["events_verified"]
            previous_hash = "0" * 64
            if chained_count:
                for existing in reversed(self._read_lines()):
                    try:
                        existing_record = json.loads(existing)
                        existing_details = existing_record.get("details", {})
                    except (json.JSONDecodeError, AttributeError):
                        continue
                    if isinstance(existing_details, dict) and existing_details.get("event_hash"):
                        previous_hash = existing_details["event_hash"]
                        break
            details_with_chain = dict(payload["details"])
            details_with_chain.update({
                "event_sequence": chained_count + 1,
                "previous_event_hash": previous_hash,
            })
            payload["details"] = details_with_chain
            payload["details"]["event_hash"] = hashlib.sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
        return payload

    def verify_integrity(self) -> dict[str, Any]:
        """Verify event records that carry optional sequence/hash metadata.

        Legacy streams without metadata remain valid but are reported as
        unchained. This detects accidental edits, not malicious rewriting.
        """
        sequence = 0
        previous_hash = "0" * 64
        chain_position = 0
        verified = 0
        unchained = 0
        chain_started = False
        chain_corrupted = False
        unparseable_after_chain = False
        errors: list[dict[str, Any]] = []
        if not self.path.exists():
            return {"valid": True, "events_verified": 0, "unchained_events": 0, "errors": []}
        for line_number, line in enumerate(self._read_lines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                errors.append({"line": line_number, "error": "invalid_json"})
                if chain_started:
                    unparseable_after_chain = True
                continue
            if not isinstance(record, dict):
                errors.append({"line": line_number, "error": "invalid_record"})
                continue
            details = record.get("details")
            details = details if isinstance(details, dict) else {}
            record_sequence = details.get("event_sequence")
            record_hash = details.get("event_hash")
            record_previous = details.get("previous_event_hash")
            if record_sequence is None and record_hash is None and record_previous is None:
                unchained += 1
                if chain_started or chain_position:
                    chain_corrupted = True
                    errors.append({"line": line_number, "error": "unchained_record_within_chain"})
                continue
            if unchained:
                chain_corrupted = True
                errors.append({"line": line_number, "error": "chain_after_legacy_records"})
                continue
            expected_sequence = sequence + 1
            if record_sequence != expected_sequence:
                chain_corrupted = True
                errors.append({"line": line_number, "error": "sequence_mismatch"})
                continue
            if unparseable_after_chain:
                chain_corrupted = True
                errors.append({"line": line_number, "error": "unparseable_line_inside_chain"})
                unparseable_after_chain = False
            if record_previous != previous_hash:
                chain_corrupted = True
                errors.append({"line": line_number, "error": "previous_hash_mismatch"})
                continue
            unsigned = dict(record)
            unsigned_details = dict(details)
            unsigned_details.pop("event_hash", None)
            unsigned["details"] = unsigned_details
            expected_hash = hashlib.sha256(json.dumps(unsigned, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            if record_hash != expected_hash:
                chain_corrupted = True
                errors.append({"line": line_number, "error": "event_hash_mismatch"})
                continue
            sequence = expected_sequence
            chain_position = expected_sequence
            chain_started = True
            previous_hash = record_hash
            verified += 1
        return {"valid": not errors and not chain_corrupted, "events_verified": verified, "unchained_events": unchained, "chain_corrupted": chain_corrupted, "errors": errors}

    def _read_lines(self) -> list[str]:
        # The stream is append-only JSONL, so it can accumulate bytes that are
        # not valid UTF-8 (a truncated or externally written file). Decode
        # leniently so the existing per-line JSON check discards just the bad
        # lines, instead of raising UnicodeDecodeError out of read()/follow()
        # and blocking the MVP replay path. Replacement preserves the line
        # structure exactly, so follow()'s line cursor stays correct.
        return self.path.read_text(encoding="utf-8", errors="replace").splitlines()

    def read(self, *, node_id: str | None = None, event: str | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self._read_lines():
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

    def follow(self, node_id: str, *, event: str | None = None, after: int = 0) -> list[dict[str, Any]]:
        """Return ordered events for one node after an optional JSONL line cursor."""
        if isinstance(after, bool) or not isinstance(after, int):
            raise ValueError("Event stream cursor must be an integer.")
        cursor = max(0, after)
        if cursor == 0:
            return self.read(node_id=node_id, event=event)
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(self._read_lines(), start=1):
            if line_number <= cursor or not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            if item.get("node_id") != node_id:
                continue
            if event is not None and item.get("event") != event:
                continue
            events.append(item)
        return events

    def replay(self, *, node_id: str | None = None) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        in_flight_tools: dict[str, dict[str, Any]] = {}
        tool_recoveries: list[dict[str, Any]] = []
        last_event: dict[str, Any] | None = None
        for event_item in self.read(node_id=node_id):
            event_name = event_item.get("event")
            details = event_item.get("details")
            if not isinstance(details, dict):
                details = {}
            operation_id = details.get("operation_id")
            if isinstance(operation_id, str) and operation_id and event_name in {"tool_started", "tool_checkpoint"}:
                in_flight_tools[operation_id] = {
                    "operation_id": operation_id,
                    "node_id": event_item.get("node_id"),
                    "tool": details.get("tool"),
                    "action_type": details.get("action_type"),
                    "session_id": details.get("session_id"),
                    "message": event_item.get("message", ""),
                    "retry_authorized": False,
                    "status": "in_flight",
                }
            elif isinstance(operation_id, str) and operation_id and event_name in {"tool_result", "tool_recovery"}:
                in_flight_tools.pop(operation_id, None)
            if event_name == "tool_recovery" and isinstance(operation_id, str) and operation_id:
                details = {**details, "retry_authorized": False}
                tool_recoveries.append({
                    "operation_id": operation_id,
                    "node_id": event_item.get("node_id"),
                    "tool": details.get("tool"),
                    "action_type": details.get("action_type"),
                    "session_id": details.get("session_id"),
                    "retry_authorized": False,
                    "status": "recovered",
                })

            event_node_id = event_item.get("node_id")
            if isinstance(event_node_id, str) and event_node_id:
                state = nodes.setdefault(event_node_id, {"node_id": event_node_id})
                state.update({key: event_item.get(key) for key in ("parent_node_id", "purpose") if event_item.get(key) is not None})
                if isinstance(details, dict) and "node_uuid" in details:
                    state["node_uuid"] = details["node_uuid"]
                state["last_event"] = event_item.get("event")
                state["message"] = event_item.get("message", "")
                details = event_item.get("details")
                if isinstance(details, dict):
                    state.update({
                        key: details.get(key)
                        for key in (
                            "node_uuid", "context_revision", "summary_ref", "remaining_input_tokens",
                            "provider", "model", "context_window", "input_limit",
                            "reserved_output", "safety_margin", "available_input_tokens",
                            "prompt_chars_before", "prompt_chars_after",
                        )
                        if key in details
                    })
                    if event_item.get("event") in {"file_read_failure", "action_field_rejected"}:
                        state.update({
                            key: details.get(key)
                            for key in ("path", "error", "status", "action_type", "field")
                            if key in details
                        })
                    if event_item.get("event") in {"mutation_failure", "mutation_recovery", "mutation_replay"}:
                        state["mutation_key"] = details.get("mutation_key")
                        state["mutation_status"] = details.get("status") or (
                            "recovered" if event_item.get("event") == "mutation_recovery" else "replayed"
                        )
                    node = details.get("node")
                    if isinstance(node, dict):
                        state.update({
                            key: node.get(key)
                            for key in (
                                "node_uuid", "status", "active_work", "output_summary", "error_message",
                                "execution_mode", "cycle_id", "cycle_phase", "context_revision", "last_checkpoint",
                                "retry_count", "max_retries",
                            )
                            if key in node
                        })
            last_event = event_item
        return {
            "tree_id": last_event.get("tree_id") if last_event else None,
            "nodes": nodes,
            "in_flight_tools": in_flight_tools,
            "tool_recoveries": tool_recoveries,
            "last_event": last_event,
        }


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
