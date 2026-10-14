from __future__ import annotations

import multiprocessing
import tempfile
import threading
import unittest
from pathlib import Path

from stagewarden.event_stream import EventStream


def _event_process_writer(path: str, index: int, barrier, errors) -> None:
    try:
        stream = EventStream(Path(path))
        barrier.wait(timeout=10)
        for item in range(10):
            stream.append("tick", tree_id="tree", node_id=f"p{index}", message=str(item))
    except BaseException as exc:
        errors.put(repr(exc))
        raise


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
            verified = stream.verify_integrity()
            self.assertTrue(verified["valid"])
            self.assertEqual(verified["events_verified"], 2)

    def test_windows_process_lock_locks_one_initialized_byte(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            events_path = stream.path
            class FakeLockFile:
                def __init__(self, wrapped):
                    self.wrapped = wrapped
                def __enter__(self): return self
                def __exit__(self, *_args): self.wrapped.close()
                def seek(self, *args): return self.wrapped.seek(*args)
                def read(self, *args): return self.wrapped.read(*args)
                def write(self, *args): return self.wrapped.write(*args)
                def flush(self): return self.wrapped.flush()
                def fileno(self): return self.wrapped.fileno()

            fake_file = None
            real_open = open
            def open_lock(*_args, **_kwargs):
                nonlocal fake_file
                lock_path = events_path.with_name(events_path.name + ".lock")
                fake_file = FakeLockFile(real_open(lock_path, "a+b"))
                return fake_file

            calls = []
            class FakeMsvcrt:
                LK_LOCK = 1
                LK_UNLCK = 2
                @staticmethod
                def locking(_fd, mode, length):
                    calls.append((mode, fake_file.wrapped.tell(), length))

            from unittest.mock import patch
            real_path_open = Path.open
            def patched_path_open(path, *args, **kwargs):
                if path.name.endswith(".lock"):
                    return open_lock()
                return real_path_open(path, *args, **kwargs)
            with patch("os.name", "nt"), patch.dict("sys.modules", {"msvcrt": FakeMsvcrt}):
                with patch.object(Path, "open", patched_path_open):
                    with stream._process_lock():
                        pass
            self.assertEqual([length for _mode, _offset, length in calls], [1, 1])
            self.assertEqual(calls[0][0], FakeMsvcrt.LK_LOCK)
            self.assertEqual(calls[1][0], FakeMsvcrt.LK_UNLCK)
            self.assertEqual(len(stream.path.with_name(stream.path.name + ".lock").read_bytes()), 1)

    def test_shared_path_instances_serialize_concurrent_appends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            streams = [EventStream(path), EventStream(path)]
            failures: list[BaseException] = []

            def writer(index: int) -> None:
                try:
                    for item in range(25):
                        streams[index].append("tick", tree_id="tree", node_id=f"n{index}", message=str(item))
                except BaseException as exc:
                    failures.append(exc)

            threads = [threading.Thread(target=writer, args=(index,)) for index in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(failures, [])
            report = EventStream(path).verify_integrity()
            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(report["events_verified"], 50)

    def test_alias_paths_share_process_lock_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "events.jsonl"
            alias = root / "alias.jsonl"
            target.touch()
            alias.symlink_to(target)
            direct_stream = EventStream(target)
            alias_stream = EventStream(alias)
            self.assertEqual(direct_stream._lock, alias_stream._lock)
            self.assertEqual(
                direct_stream.path.resolve().with_name("events.jsonl.lock"),
                alias_stream.path.resolve().with_name("events.jsonl.lock"),
            )

    def test_separate_process_writers_preserve_hash_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            context = multiprocessing.get_context("spawn")
            barrier = context.Barrier(2)
            errors = context.Queue()

            processes = [
                context.Process(target=_event_process_writer, args=(str(path), index, barrier, errors))
                for index in range(2)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=30)
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            self.assertTrue(all(not process.is_alive() for process in processes))
            self.assertEqual([process.exitcode for process in processes], [0, 0])
            self.assertTrue(errors.empty())
            report = EventStream(path).verify_integrity()
            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(report["events_verified"], 20)

    def test_invalid_line_after_legacy_events_blocks_later_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            stream = EventStream(path)
            path.write_text('{"event":"legacy","details":{}}\nnot-json\n', encoding="utf-8")
            report = stream.verify_integrity()
            self.assertFalse(report["valid"])
            self.assertTrue(report["chain_corrupted"])
            with self.assertRaisesRegex(ValueError, "corrupt event stream"):
                stream.append("later", tree_id="tree")

    def test_event_hash_chain_rejects_unhashed_insertion_and_reordering(self) -> None:
        for corruption in ("insert", "reverse"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "events.jsonl"
                stream = EventStream(path)
                stream.append("first", tree_id="tree", message="1")
                stream.append("second", tree_id="tree", message="2")
                lines = path.read_text(encoding="utf-8").splitlines()
                if corruption == "insert":
                    import json
                    lines.insert(1, json.dumps({"event": "injected", "details": {}}))
                else:
                    lines.reverse()
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                self.assertFalse(stream.verify_integrity()["valid"])
                with self.assertRaisesRegex(ValueError, "corrupt event stream"):
                    stream.append("third", tree_id="tree")

    def test_hash_chain_rejects_unparseable_line_inside_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            stream = EventStream(path)
            stream.append("first", tree_id="tree")
            stream.append("second", tree_id="tree")
            lines = path.read_text(encoding="utf-8").splitlines()
            lines.insert(1, "not-json")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            report = stream.verify_integrity()
            self.assertFalse(report["valid"])
            self.assertTrue(report["chain_corrupted"])
            self.assertEqual(report["events_verified"], 1)
            self.assertIn("unparseable_line_inside_chain", {item["error"] for item in report["errors"]})
            with self.assertRaisesRegex(ValueError, "corrupt event stream"):
                stream.append("third", tree_id="tree")

    def test_event_hash_chain_detects_record_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            stream = EventStream(path)
            stream.append("start", tree_id="tree", node_id="n", message="original")
            stream.append("result", tree_id="tree", node_id="n", message="done")
            self.assertTrue(stream.verify_integrity()["valid"])
            raw = path.read_text(encoding="utf-8").replace("original", "tampered")
            path.write_text(raw, encoding="utf-8")
            report = stream.verify_integrity()
            self.assertFalse(report["valid"])
            self.assertEqual(report["errors"][0]["error"], "event_hash_mismatch")
            with self.assertRaisesRegex(ValueError, "corrupt event stream"):
                stream.append("next", tree_id="tree", node_id="n")

    def test_readers_survive_undecodable_bytes_in_the_event_stream(self) -> None:
        """read() and follow() decoded events.jsonl with no error handling, so
        any bytes that are not valid UTF-8 raised UnicodeDecodeError out of the
        MVP replay path and out of the CLI `events` task."""
        bodies = {
            "binary garbage": b"\xff\xfe\x00\x01\x80\x81 not utf-8",
            "lone continuation": b"\x80\x81\x82 only continuation bytes\n",
            "null bytes": b"\x00\x00\x00\n",
            "not json": b"this is not json\n",
            "truncated": b'{"event": "node_start", ',
        }
        for label, body in bodies.items():
            with self.subTest(stream=label):
                with tempfile.TemporaryDirectory() as tmp:
                    stream = EventStream(Path(tmp) / "events.jsonl")
                    stream.path.parent.mkdir(parents=True, exist_ok=True)
                    stream.path.write_bytes(body)
                    self.assertEqual(stream.read(), [])
                    self.assertEqual(stream.follow("node.a", after=1), [])
                    self.assertIsInstance(stream.replay(), dict)

    def test_undecodable_bytes_do_not_hide_surrounding_valid_events(self) -> None:
        """The point of the auditability surface: valid events on BOTH sides of
        undecodable bytes must still replay, and line numbers must survive so
        the follow() cursor keeps addressing the right event."""
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append("node_start", tree_id="tree-1", node_id="node.a", purpose="inspect")
            with stream.path.open("ab") as handle:
                handle.write(b"\xff\xfe not utf-8\n")
            stream.append("node_end", tree_id="tree-1", node_id="node.a", purpose="inspect")

            events = stream.read()
            self.assertEqual([e["event"] for e in events], ["node_start", "node_end"])

            # the bad bytes are line 2, so a cursor of 2 must still return node_end
            self.assertEqual(
                [e["event"] for e in stream.follow("node.a", after=2)], ["node_end"]
            )
            self.assertEqual(
                [e["event"] for e in stream.follow("node.a", after=1)], ["node_end"]
            )
            replayed = stream.replay(node_id="node.a")
            self.assertEqual(replayed["nodes"]["node.a"]["last_event"], "node_end")
            self.assertEqual(replayed["nodes"]["node.a"]["purpose"], "inspect")

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

    def test_node_uuid_replay_matrix_preserves_identity_and_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            node_a_uuid = "11111111-1111-4111-8111-111111111111"
            node_b_uuid = "22222222-2222-4222-8222-222222222222"
            stream.append("start", tree_id="tree", node_id="node-a", node_uuid=node_a_uuid, purpose="A")
            stream.append("start", tree_id="tree", node_id="node-b", node_uuid=node_b_uuid, purpose="B")
            stream.append("result", tree_id="tree", node_id="node-a", node_uuid=node_a_uuid, purpose="A", node={"status": "completed"})
            raw = (Path(tmp) / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn(node_a_uuid, raw)
            replay = stream.replay(node_id="node-a")
            self.assertEqual(replay["nodes"]["node-a"]["node_uuid"], node_a_uuid)
            self.assertEqual(set(replay["nodes"]), {"node-a"})
            self.assertNotEqual(node_a_uuid, node_b_uuid)

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

    def test_mutation_failure_replay_matrix_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            key = "mutation:failed"
            stream.append("mutation_failure", tree_id="tree-1", node_id="node-a", purpose="mutation failure", message="patch failed", mutation_key=key, action_type="apply_patch", status="failed")
            stream.append("mutation_failure", tree_id="tree-1", node_id="node-b", purpose="mutation failure", message="other failed", mutation_key="mutation:other", action_type="apply_patch", status="failed")
            replay = stream.replay(node_id="node-a")
            state = replay["nodes"]["node-a"]
            # 1. Replay preserves stable mutation key.
            self.assertEqual(state["mutation_key"], key)
            # 2. Replay exposes failed mutation status.
            self.assertEqual(state["mutation_status"], "failed")
            # 3. Node filtering excludes other mutation failures.
            self.assertEqual(set(replay["nodes"]), {"node-a"})

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

    def test_follow_cursor_input_validation_matrix_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stream = EventStream(Path(tmp) / "events.jsonl")
            stream.append("start", tree_id="tree-1", node_id="leaf-a", purpose="A")
            # 1. Negative cursor remains a safe initial poll.
            self.assertEqual([item["event"] for item in stream.follow("leaf-a", after=-1)], ["start"])
            # 2. String cursor is rejected instead of coerced.
            with self.assertRaises(ValueError):
                stream.follow("leaf-a", after="1")  # type: ignore[arg-type]
            # 3. Bool cursor is rejected instead of treated as integer one.
            with self.assertRaises(ValueError):
                stream.follow("leaf-a", after=True)

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
