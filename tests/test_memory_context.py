from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stagewarden.config import AgentConfig
from stagewarden.memory_context import load_memory_context
from stagewarden.executor import Executor
from stagewarden.handoff import HandoffManager
from stagewarden.memory import MemoryStore
from stagewarden.project_handoff import ProjectHandoff
from stagewarden.router import ModelRouter
from stagewarden.rag import DesignRag
from stagewarden.planner import PlanStep


class MemoryContextTests(unittest.TestCase):
    def settings(self, root: Path, payload: dict) -> Path:
        path = root / ".stagewarden_settings.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = load_memory_context(root, root / ".stagewarden_settings.json")
            self.assertFalse(context.enabled)
            self.assertEqual(context.content, "")

    def test_loads_multiple_markdown_files_and_bounds_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("durable fact", encoding="utf-8")
            (memory / "decisions.md").write_text("decision", encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md", "decisions.md"], "max_chars": 500}})
            context = load_memory_context(root, path)
            self.assertTrue(context.enabled)
            self.assertEqual(len(context.files), 2)
            self.assertLessEqual(len(context.content), 500 + len("\n[truncated by memory.max_chars]"))
            self.assertIn("pi-memory.md", context.content)

    def test_missing_optional_file_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["missing.md"]}})
            context = load_memory_context(root, path)
            self.assertTrue(context.ok)
            self.assertTrue(any(issue.level == "warning" for issue in context.issues))

    def test_rejects_traversal_and_non_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (root / "secret.txt").write_text("secret", encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["../secret.txt", "x.json"]}})
            context = load_memory_context(root, path)
            self.assertFalse(context.ok)
            self.assertEqual(sum(issue.level == "error" for issue in context.issues), 2)

    def test_prompt_includes_configured_context_without_writing_external_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            source = memory / "pi-memory.md"
            source.write_text("external durable context", encoding="utf-8")
            settings = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            config = AgentConfig(workspace_root=root)
            executor = Executor(config=config, router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            step = PlanStep(id="step", title="Read context", instruction="inspect", validation="context")
            prompt = executor._build_prompt(task="inspect", step=step, plan=[step], last_observation="none")
            self.assertIn("Configured Hermes/Obsidian memory", prompt)
            self.assertIn("external durable context", prompt)
            self.assertEqual(source.read_text(encoding="utf-8"), "external durable context")


if __name__ == "__main__":
    unittest.main()
