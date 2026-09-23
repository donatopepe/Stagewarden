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
