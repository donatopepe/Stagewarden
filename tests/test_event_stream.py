from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewarden.event_stream import EventStream


class EventStreamTests(unittest.TestCase):
    def test_append_redacts_secrets_and_replays_node_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append(
                "start",
                tree_id="tree-1",
                node_id="leaf",
                parent_node_id="root",
                purpose="Inspect source",
                message="reading",
                node={"status": "running", "active_work": "read_file"},
                api_key="secret-value",
            )
            stream.append(
                "result",
                tree_id="tree-1",
                node_id="leaf",
                parent_node_id="root",
                purpose="Inspect source",
                message="done",
                node={"status": "completed", "output_summary": "ok"},
            )
            raw = (Path(tmp) / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("secret-value", raw)
            replay = stream.replay()
            self.assertEqual(replay["nodes"]["leaf"]["status"], "completed")
            self.assertEqual(replay["nodes"]["leaf"]["purpose"], "Inspect source")

    def test_replay_projects_in_flight_tool_and_clears_on_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append(
                "tool_started",
                tree_id="executor",
                node_id="node.shell",
                purpose="node tool execution",
                message="shell_session_send",
                operation_id="tool-1",
                tool="shell",
                action_type="shell_session_send",
                session_id="session-1",
            )
            replay = stream.replay()
            self.assertEqual(replay["in_flight_tools"]["tool-1"]["status"], "in_flight")
            self.assertFalse(replay["in_flight_tools"]["tool-1"]["retry_authorized"])
            stream.append(
                "tool_result",
                tree_id="executor",
                node_id="node.shell",
                purpose="node tool execution",
                message="shell_session_send",
                operation_id="tool-1",
                tool="shell",
                action_type="shell_session_send",
                success=True,
            )
            self.assertEqual(stream.replay()["in_flight_tools"], {})

    def test_replay_scopes_in_flight_tools_and_projects_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append("tool_started", tree_id="executor", node_id="node-a", purpose="tool", message="shell", operation_id="op-a", tool="shell", action_type="shell", retry_authorized=False)
            stream.append("tool_started", tree_id="executor", node_id="node-b", purpose="tool", message="shell", operation_id="op-b", tool="shell", action_type="shell", retry_authorized=False)
            self.assertEqual(set(stream.replay()["in_flight_tools"]), {"op-a", "op-b"})
            filtered = stream.replay(node_id="node-a")
            self.assertEqual(set(filtered["in_flight_tools"]), {"op-a"})
            stream.append("tool_recovery", tree_id="executor", node_id="node-a", purpose="recover", message="shell", operation_id="op-a", tool="shell", action_type="shell", retry_authorized=False)
            recovered = stream.replay(node_id="node-a")
            self.assertEqual(recovered["in_flight_tools"], {})
            self.assertEqual(recovered["tool_recoveries"][-1]["operation_id"], "op-a")
            self.assertFalse(recovered["tool_recoveries"][-1]["retry_authorized"])
            self.assertEqual(recovered["tool_recoveries"][-1]["status"], "recovered")

    def test_replay_recovery_closure_matrix_preserves_node_status_and_retry_denial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append("tool_started", tree_id="tree", node_id="node-a", purpose="tool", message="shell", operation_id="op-a", tool="shell", action_type="shell")
            in_flight = stream.replay(node_id="node-a")
            stream.append("tool_recovery", tree_id="tree", node_id="node-a", purpose="tool recovery", message="shell", operation_id="op-a", tool="shell", action_type="shell", retry_authorized=False)
            recovered = stream.replay(node_id="node-a")
            self.assertIn("op-a", in_flight["in_flight_tools"])
            self.assertEqual(recovered["in_flight_tools"], {})
            marker = recovered["tool_recoveries"][-1]
            self.assertEqual(marker["status"], "recovered")
            self.assertEqual(marker["node_id"], "node-a")
            self.assertFalse(marker["retry_authorized"])

    def test_replay_preserves_cycle_and_checkpoint_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append(
                "node_cycle_checkpoint",
                tree_id="tree-1",
                node_id="leaf",
                purpose="Inspect source",
                node={
                    "status": "running",
                    "cycle_id": 2,
                    "cycle_phase": "verify",
                    "context_revision": 3,
                    "last_checkpoint": "event-7",
                },
            )
            replay = stream.replay()
            self.assertEqual(replay["nodes"]["leaf"]["cycle_id"], 2)
            self.assertEqual(replay["nodes"]["leaf"]["cycle_phase"], "verify")
            self.assertEqual(replay["nodes"]["leaf"]["context_revision"], 3)
            self.assertEqual(replay["nodes"]["leaf"]["last_checkpoint"], "event-7")

    def test_replay_projects_latest_context_and_mutation_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append(
                "context_compaction",
                tree_id="tree-1",
                node_id="leaf",
                purpose="Inspect source",
                context_revision=4,
                summary_ref="summary-4",
                remaining_input_tokens=120,
            )
            stream.append(
                "mutation_recovery",
                tree_id="tree-1",
                node_id="leaf",
                purpose="Recover write",
                mutation_key="mutation:abc",
                action_type="write_file",
                status="completed",
            )
            replay = stream.replay()
            state = replay["nodes"]["leaf"]
            self.assertEqual(state["context_revision"], 4)
            self.assertEqual(state["summary_ref"], "summary-4")
            self.assertEqual(state["remaining_input_tokens"], 120)
            self.assertEqual(state["mutation_key"], "mutation:abc")
            self.assertEqual(state["mutation_status"], "completed")

    def test_context_metadata_redaction_and_node_replay_matrix_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            # 1. provider/model/context metadata survives replay
            stream.append(
                "file_chunk",
                tree_id="tree-1",
                node_id="node-a",
                purpose="Read source",
                provider="cheap",
                model="provider-default",
                context_window=200,
                input_limit=180,
                reserved_output=20,
                safety_margin=10,
                available_input_tokens=150,
                prompt_chars_before=100,
                prompt_chars_after=140,
            )
            replay = stream.replay(node_id="node-a")
            self.assertEqual(replay["nodes"]["node-a"]["provider"], "cheap")
            self.assertEqual(replay["nodes"]["node-a"]["model"], "provider-default")
            self.assertEqual(replay["nodes"]["node-a"]["context_window"], 200)
            # 2. secret-like values remain redacted
            stream.append("context_compaction", tree_id="tree-1", node_id="node-a", purpose="compact", provider="cheap", model="provider-default", api_key="do-not-persist", authorization="Bearer secret")
            raw = (Path(tmp) / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("do-not-persist", raw)
            self.assertNotIn("Bearer secret", raw)
            self.assertIn("provider-default", raw)
            self.assertIn("[REDACTED]", raw)
            # 3. node filter excludes other node events
            stream.append("file_chunk", tree_id="tree-1", node_id="node-b", purpose="Other", provider="other")
            filtered = stream.replay(node_id="node-a")
            self.assertEqual(set(filtered["nodes"]), {"node-a"})

    def test_replay_projects_file_read_failure_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append(
                "file_read_failure",
                tree_id="executor",
                node_id="node-a",
                purpose="complete file read recovery",
                message="hash changed",
                path="source.txt",
                error="hash changed",
                status="failed",
            )
            stream.append(
                "file_read_failure",
                tree_id="executor",
                node_id="node-b",
                purpose="complete file read recovery",
                message="other",
                path="other.txt",
                error="other",
                status="failed",
            )
            replay = stream.replay(node_id="node-a")
            self.assertEqual(replay["nodes"]["node-a"]["status"], "failed")
            self.assertEqual(set(replay["nodes"]), {"node-a"})

    def test_replay_projects_file_read_failure_metadata_and_node_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append(
                "file_read_failure",
                tree_id="executor",
                node_id="node-a",
                purpose="complete file read recovery",
                message="hash changed",
                path="source.txt",
                error="hash changed",
                status="failed",
            )
            stream.append(
                "file_read_failure",
                tree_id="executor",
                node_id="node-b",
                purpose="complete file read recovery",
                message="other",
                path="other.txt",
                error="other",
                status="failed",
            )
            replay = stream.replay(node_id="node-a")
            state = replay["nodes"]["node-a"]
            # 1. Replay keeps failure event identity.
            self.assertEqual(state["last_event"], "file_read_failure")
            # 2. Replay exposes path/error/status metadata.
            self.assertEqual(state["path"], "source.txt")
            self.assertEqual(state["error"], "hash changed")
            self.assertEqual(state["status"], "failed")
            # 3. Node filtering excludes other failure events.
            self.assertEqual(set(replay["nodes"]), {"node-a"})

    def test_follow_cursor_polling_matrix_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append("start", tree_id="tree-1", node_id="leaf-a", purpose="A")
            stream.append("start", tree_id="tree-1", node_id="leaf-b", purpose="B")
            # 1. Initial event filter remains node-scoped.
            self.assertEqual([item["event"] for item in stream.follow("leaf-a", event="start", after=0)], ["start"])
            cursor = len((Path(tmp) / "events.jsonl").read_text(encoding="utf-8").splitlines())
            stream.append("result", tree_id="tree-1", node_id="leaf-a", purpose="A")
            stream.append("result", tree_id="tree-1", node_id="leaf-b", purpose="B")
            # 2. Cursor returns only events appended after the checkpoint.
            self.assertEqual([item["event"] for item in stream.follow("leaf-a", event="result", after=cursor)], ["result"])
            # 3. Cursor polling cannot leak another node.
            self.assertEqual([item["node_id"] for item in stream.follow("leaf-a", after=cursor)], ["leaf-a"])

    def test_follow_filters_events_and_replay_to_one_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append("start", tree_id="tree-1", node_id="leaf-a", purpose="A")
            stream.append("start", tree_id="tree-1", node_id="leaf-b", purpose="B")
            stream.append("result", tree_id="tree-1", node_id="leaf-a", purpose="A", node={"status": "completed"})
            events = stream.read(node_id="leaf-a")
            self.assertEqual([item["node_id"] for item in events], ["leaf-a", "leaf-a"])
            replay = stream.replay(node_id="leaf-a")
            self.assertEqual(set(replay["nodes"]), {"leaf-a"})
            self.assertEqual(replay["nodes"]["leaf-a"]["status"], "completed")
            self.assertEqual([item["event"] for item in stream.follow("leaf-a")], ["start", "result"])


if __name__ == "__main__":
    unittest.main()
