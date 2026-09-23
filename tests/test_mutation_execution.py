from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewarden.config import AgentConfig
from stagewarden.executor import Executor
from stagewarden.handoff import HandoffManager
from stagewarden.memory import MemoryStore
from stagewarden.project_handoff import ProjectHandoff
from stagewarden.rag import DesignRag
from stagewarden.router import ModelRouter


class MutationExecutionTests(unittest.TestCase):
    def test_apply_patch_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "apply_patch", "path": "result.txt", "search": "before", "replace": "after"}
            first = executor._run_action(action, step_id="node.apply-patch")
            second = executor._run_action(action, step_id="node.apply-patch")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_apply_patch_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "apply_patch", "path": "result.txt", "search": "before", "replace": "after"}
            key = executor.mutations.key("apply_patch", action)
            executor.mutations.append(key=key, action_type="apply_patch", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.apply-patch")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_apply_patch_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "apply_patch", "path": "result.txt", "search": "missing", "replace": "after"}
            result = executor._run_action(action, step_id="node.apply-patch")
            key = executor.mutations.key("apply_patch", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_completed_apply_patch_is_idempotently_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before\n", encoding="utf-8")
            executor = Executor(
                config=AgentConfig(workspace_root=root),
                router=ModelRouter(),
                handoff=HandoffManager(),
                memory=MemoryStore(),
                project_handoff=ProjectHandoff(),
                rag=DesignRag(),
            )
            action = {"type": "apply_patch", "path": "result.txt", "search": "before", "replace": "after"}
            first = executor._run_action(action, step_id="node.patch")
            second = executor._run_action(action, step_id="node.patch")
            self.assertTrue(first["ok"])
            self.assertTrue(second["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
            executor.close()

    def test_interrupted_write_journal_is_recovered_without_duplicate_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor = Executor(
                config=AgentConfig(workspace_root=root),
                router=ModelRouter(),
                handoff=HandoffManager(),
                memory=MemoryStore(),
                project_handoff=ProjectHandoff(),
                rag=DesignRag(),
            )
            action = {"type": "write_file", "path": "result.txt", "content": "done\\n"}
            key = executor.mutations.key("write_file", action)
            executor.mutations.append(key=key, action_type="write_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.write")
            self.assertTrue(result["ok"])
            self.assertFalse(result.get("replayed", False))
            self.assertTrue(result.get("recovered", False))
            self.assertIn("mutation_recovery", {item["event"] for item in executor.events.read()})
            entries = [item for item in executor.mutations.list() if item["key"] == key]
            self.assertEqual([item["status"] for item in entries], ["in_flight", "completed"])
            self.assertEqual((root / "result.txt").read_text(encoding="utf-8"), "done\\n")
            executor.close()

    def test_insert_text_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "result.txt").write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "insert_text_file", "path": "result.txt", "content": "added\n", "line_number": 1, "position": "after"}
            first = executor._run_action(action, step_id="node.insert")
            second = executor._run_action(action, step_id="node.insert")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual((root / "result.txt").read_text(encoding="utf-8"), "before\nadded\n")
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_insert_text_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "insert_text_file", "path": "result.txt", "content": "added\n", "line_number": 1, "position": "after"}
            key = executor.mutations.key("insert_text_file", action)
            executor.mutations.append(key=key, action_type="insert_text_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.insert")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_insert_text_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "insert_text_file", "path": "result.txt", "content": "added\n", "pattern": "missing"}
            result = executor._run_action(action, step_id="node.insert")
            key = executor.mutations.key("insert_text_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_search_replace_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "search_replace_file", "path": "result.txt", "search": "before", "replace": "after", "count": 1}
            first = executor._run_action(action, step_id="node.search")
            second = executor._run_action(action, step_id="node.search")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(target.read_text(encoding="utf-8"), "after before\n")
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_search_replace_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "search_replace_file", "path": "result.txt", "search": "before", "replace": "after", "count": 1}
            key = executor.mutations.key("search_replace_file", action)
            executor.mutations.append(key=key, action_type="search_replace_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.search")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
            executor.close()

    def test_failed_search_replace_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "search_replace_file", "path": "result.txt", "search": "missing", "replace": "after", "count": 1}
            result = executor._run_action(action, step_id="node.search")
            key = executor.mutations.key("search_replace_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_patch_file_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "patch_file", "path": "result.txt", "diff": "\n".join(("--- a/result.txt", "+++ b/result.txt", "@@ -1,1 +1,1 @@", "-before", "+after"))}
            first = executor._run_action(action, step_id="node.patch-file")
            second = executor._run_action(action, step_id="node.patch-file")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_patch_file_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "patch_file", "path": "result.txt", "diff": "\n".join(("--- a/result.txt", "+++ b/result.txt", "@@ -1,1 +1,1 @@", "-before", "+after"))}
            key = executor.mutations.key("patch_file", action)
            executor.mutations.append(key=key, action_type="patch_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.patch-file")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
            executor.close()

    def test_failed_patch_file_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "patch_file", "path": "result.txt", "diff": "\n".join(("--- a/result.txt", "+++ b/result.txt", "@@ -1,1 +1,1 @@", "-missing", "+after"))}
            result = executor._run_action(action, step_id="node.patch-file")
            key = executor.mutations.key("patch_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_patch_files_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.txt").write_text("before\n", encoding="utf-8")
            (root / "delete.txt").write_text("old\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            diff = "\n".join(("--- a/keep.txt", "+++ b/keep.txt", "@@ -1,1 +1,1 @@", "-before", "+after", "--- /dev/null", "+++ b/new.txt", "@@ -0,0 +1,1 @@", "+created", "--- a/delete.txt", "+++ /dev/null", "@@ -1,1 +0,0 @@", "-old"))
            action = {"type": "patch_files", "diff": diff}
            first = executor._run_action(action, step_id="node.patch-files")
            second = executor._run_action(action, step_id="node.patch-files")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual((root / "keep.txt").read_text(encoding="utf-8"), "after\n")
            self.assertEqual((root / "new.txt").read_text(encoding="utf-8"), "created\n")
            self.assertFalse((root / "delete.txt").exists())
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_patch_files_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.txt").write_text("before\n", encoding="utf-8")
            (root / "delete.txt").write_text("old\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            diff = "\n".join(("--- a/keep.txt", "+++ b/keep.txt", "@@ -1,1 +1,1 @@", "-before", "+after", "--- /dev/null", "+++ b/new.txt", "@@ -0,0 +1,1 @@", "+created", "--- a/delete.txt", "+++ /dev/null", "@@ -1,1 +0,0 @@", "-old"))
            action = {"type": "patch_files", "diff": diff}
            key = executor.mutations.key("patch_files", action)
            executor.mutations.append(key=key, action_type="patch_files", path="", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.patch-files")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_patch_files_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.txt").write_text("before\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            diff = "\n".join(("--- a/keep.txt", "+++ b/keep.txt", "@@ -1,1 +1,1 @@", "-missing", "+after"))
            action = {"type": "patch_files", "diff": diff}
            result = executor._run_action(action, step_id="node.patch-files")
            key = executor.mutations.key("patch_files", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_delete_range_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("one\ntwo\nthree\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "delete_range_file", "path": "result.txt", "start_line": 2, "end_line": 2}
            first = executor._run_action(action, step_id="node.delete-range")
            second = executor._run_action(action, step_id="node.delete-range")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(target.read_text(encoding="utf-8"), "one\nthree\n")
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_delete_range_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("one\ntwo\nthree\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "delete_range_file", "path": "result.txt", "start_line": 2, "end_line": 2}
            key = executor.mutations.key("delete_range_file", action)
            executor.mutations.append(key=key, action_type="delete_range_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.delete-range")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_delete_range_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("one\ntwo\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "delete_range_file", "path": "result.txt", "start_line": 3, "end_line": 3}
            result = executor._run_action(action, step_id="node.delete-range")
            key = executor.mutations.key("delete_range_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_delete_backward_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("one\ntwo\nthree\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "delete_backward_file", "path": "result.txt", "count": 1, "line_number": 3}
            first = executor._run_action(action, step_id="node.delete-backward")
            second = executor._run_action(action, step_id="node.delete-backward")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(target.read_text(encoding="utf-8"), "one\nthree\n")
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_delete_backward_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("one\ntwo\nthree\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "delete_backward_file", "path": "result.txt", "count": 1, "line_number": 3}
            key = executor.mutations.key("delete_backward_file", action)
            executor.mutations.append(key=key, action_type="delete_backward_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.delete-backward")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_delete_backward_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("one\ntwo\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "delete_backward_file", "path": "result.txt", "count": 1, "pattern": "missing"}
            result = executor._run_action(action, step_id="node.delete-backward")
            key = executor.mutations.key("delete_backward_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_replace_range_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("one\ntwo\nthree\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "replace_range_file", "path": "result.txt", "start_line": 2, "end_line": 2, "content": "TWO\n"}
            first = executor._run_action(action, step_id="node.replace-range")
            second = executor._run_action(action, step_id="node.replace-range")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(target.read_text(encoding="utf-8"), "one\nTWO\nthree\n")
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_replace_range_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("one\ntwo\nthree\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "replace_range_file", "path": "result.txt", "start_line": 2, "end_line": 2, "content": "TWO\n"}
            key = executor.mutations.key("replace_range_file", action)
            executor.mutations.append(key=key, action_type="replace_range_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.replace-range")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_replace_range_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("one\ntwo\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "replace_range_file", "path": "result.txt", "start_line": 3, "end_line": 3, "content": "THREE\n"}
            result = executor._run_action(action, step_id="node.replace-range")
            key = executor.mutations.key("replace_range_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_convert_encoding_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_bytes(b"caf\xe9\n")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "convert_encoding_file", "path": "result.txt", "target_encoding": "utf-8", "source_encoding": "latin-1"}
            first = executor._run_action(action, step_id="node.convert")
            second = executor._run_action(action, step_id="node.convert")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(target.read_bytes(), "café\n".encode("utf-8"))
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_convert_encoding_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_bytes(b"caf\xe9\n")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "convert_encoding_file", "path": "result.txt", "target_encoding": "utf-8", "source_encoding": "latin-1"}
            key = executor.mutations.key("convert_encoding_file", action)
            executor.mutations.append(key=key, action_type="convert_encoding_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.convert")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_convert_encoding_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("café\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "convert_encoding_file", "path": "result.txt", "target_encoding": "not-an-encoding"}
            result = executor._run_action(action, step_id="node.convert")
            key = executor.mutations.key("convert_encoding_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_normalize_line_endings_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_bytes(b"one\r\ntwo\r\n")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "normalize_line_endings_file", "path": "result.txt", "newline": "lf"}
            first = executor._run_action(action, step_id="node.normalize")
            second = executor._run_action(action, step_id="node.normalize")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(target.read_bytes(), b"one\ntwo\n")
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_normalize_line_endings_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_bytes(b"one\r\ntwo\r\n")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "normalize_line_endings_file", "path": "result.txt", "newline": "lf"}
            key = executor.mutations.key("normalize_line_endings_file", action)
            executor.mutations.append(key=key, action_type="normalize_line_endings_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.normalize")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_normalize_line_endings_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("one\ntwo\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "normalize_line_endings_file", "path": "result.txt", "newline": "invalid"}
            result = executor._run_action(action, step_id="node.normalize")
            key = executor.mutations.key("normalize_line_endings_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_copy_path_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("alpha\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "copy_path_file", "source": "source.txt", "destination": "copy.txt"}
            first = executor._run_action(action, step_id="node.copy")
            second = executor._run_action(action, step_id="node.copy")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual((root / "copy.txt").read_text(encoding="utf-8"), "alpha\n")
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_copy_path_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("alpha\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "copy_path_file", "source": "source.txt", "destination": "copy.txt"}
            key = executor.mutations.key("copy_path_file", action)
            executor.mutations.append(key=key, action_type="copy_path_file", path="copy.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.copy")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_copy_path_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "copy_path_file", "source": "missing.txt", "destination": "copy.txt"}
            result = executor._run_action(action, step_id="node.copy")
            key = executor.mutations.key("copy_path_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_move_path_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("alpha\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "move_path_file", "source": "source.txt", "destination": "moved.txt"}
            first = executor._run_action(action, step_id="node.move")
            second = executor._run_action(action, step_id="node.move")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertFalse((root / "source.txt").exists())
            self.assertEqual((root / "moved.txt").read_text(encoding="utf-8"), "alpha\n")
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_move_path_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("alpha\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "move_path_file", "source": "source.txt", "destination": "moved.txt"}
            key = executor.mutations.key("move_path_file", action)
            executor.mutations.append(key=key, action_type="move_path_file", path="moved.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.move")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_move_path_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "move_path_file", "source": "missing.txt", "destination": "moved.txt"}
            result = executor._run_action(action, step_id="node.move")
            key = executor.mutations.key("move_path_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_delete_path_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("alpha\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "delete_path_file", "path": "result.txt"}
            first = executor._run_action(action, step_id="node.delete-path")
            second = executor._run_action(action, step_id="node.delete-path")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertFalse(target.exists())
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_delete_path_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("alpha\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "delete_path_file", "path": "result.txt"}
            key = executor.mutations.key("delete_path_file", action)
            executor.mutations.append(key=key, action_type="delete_path_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.delete-path")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_delete_path_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "delete_path_file", "path": "missing.txt"}
            result = executor._run_action(action, step_id="node.delete-path")
            key = executor.mutations.key("delete_path_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_chmod_path_action_is_journaled_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("alpha\n", encoding="utf-8")
            target.chmod(0o644)
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "chmod_path_file", "path": "result.txt", "mode": "600"}
            first = executor._run_action(action, step_id="node.chmod")
            second = executor._run_action(action, step_id="node.chmod")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_chmod_path_journal_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("alpha\n", encoding="utf-8")
            target.chmod(0o644)
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "chmod_path_file", "path": "result.txt", "mode": "600"}
            key = executor.mutations.key("chmod_path_file", action)
            executor.mutations.append(key=key, action_type="chmod_path_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.chmod")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_chmod_path_action_closes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "result.txt").write_text("alpha\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "chmod_path_file", "path": "result.txt", "mode": "not-a-mode"}
            result = executor._run_action(action, step_id="node.chmod")
            key = executor.mutations.key("chmod_path_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_chown_path_action_is_journaled_and_replayed(self) -> None:
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.txt"
            target.write_text("alpha\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "chown_path_file", "path": "result.txt", "user": os.getuid(), "group": os.getgid()}
            first = executor._run_action(action, step_id="node.chown")
            second = executor._run_action(action, step_id="node.chown")
            self.assertTrue(first["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(len(executor.mutations.list(status="completed")), 1)
            executor.close()

    def test_interrupted_chown_path_journal_is_recovered(self) -> None:
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "result.txt").write_text("alpha\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "chown_path_file", "path": "result.txt", "user": os.getuid(), "group": os.getgid()}
            key = executor.mutations.key("chown_path_file", action)
            executor.mutations.append(key=key, action_type="chown_path_file", path="result.txt", status="in_flight", message="crash before commit")
            result = executor._run_action(action, step_id="node.chown")
            self.assertTrue(result["ok"])
            self.assertTrue(result["recovered"])
            self.assertEqual([item["status"] for item in executor.mutations.list() if item["key"] == key], ["in_flight", "completed"])
            executor.close()

    def test_failed_chown_path_action_closes_journal(self) -> None:
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "result.txt").write_text("alpha\n", encoding="utf-8")
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            action = {"type": "chown_path_file", "path": "result.txt", "user": "not-a-user", "group": os.getgid()}
            result = executor._run_action(action, step_id="node.chown")
            key = executor.mutations.key("chown_path_file", action)
            self.assertFalse(result["ok"])
            self.assertEqual(executor.mutations.get(key)["status"], "failed")
            executor.close()

    def test_completed_write_action_is_idempotently_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor = Executor(
                config=AgentConfig(workspace_root=root),
                router=ModelRouter(),
                handoff=HandoffManager(),
                memory=MemoryStore(),
                project_handoff=ProjectHandoff(),
                rag=DesignRag(),
            )
            action = {"type": "write_file", "path": "result.txt", "content": "done\n"}
            first = executor._run_action(action, step_id="node.write")
            second = executor._run_action(action, step_id="node.write")
            self.assertTrue(first["ok"])
            self.assertTrue(second["ok"])
            self.assertTrue(second["replayed"])
            self.assertEqual(second["mutation_key"], first["mutation_key"])
            self.assertEqual((root / "result.txt").read_text(encoding="utf-8"), "done\n")
            self.assertIn("mutation_replay", {item["event"] for item in executor.events.read()})
            executor.close()


if __name__ == "__main__":
    unittest.main()
