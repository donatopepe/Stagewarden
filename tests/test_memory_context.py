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

    def test_token_budget_compacts_only_with_supplied_counter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("important durable facts " * 200, encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            missing_counter = load_memory_context(root, path, max_tokens=20)
            self.assertFalse(missing_counter.ok)
            counter = lambda text: (len(text) + 3) // 4
            compacted = load_memory_context(root, path, max_tokens=20, token_counter=counter, token_counter_name="test_char_estimator")
            self.assertTrue(compacted.ok)
            self.assertLessEqual((len(compacted.content) + 3) // 4, 20)
            self.assertEqual(compacted.token_count, counter(compacted.content))
            self.assertEqual(compacted.token_limit, 20)
            self.assertEqual(compacted.token_counter_name, "test_char_estimator")
            self.assertEqual(compacted.report()["content_tokens"], compacted.token_count)
            self.assertIn("truncated by memory token budget", compacted.content)

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

    def test_prompt_memory_uses_available_input_budget_and_reports_estimator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("critical memory phrase " * 200, encoding="utf-8")
            self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            step = PlanStep(id="step", title="Read context", instruction="inspect", validation="context")
            packet = executor._build_model_communication_packet(
                task="inspect", step=step, plan=[step], last_observation="none",
                provider_limits={"available_input": 80},
            )
            section = next(item for item in packet.sections if item.title == "Configured Hermes/Obsidian memory")
            self.assertIn("critical memory phrase", section.body)
            self.assertIn("truncated by memory token budget", section.body)
            self.assertIn("not_provider_tokenizer", section.body)
            context = executor.config.memory_context_with_budget(
                80, executor._estimate_memory_tokens,
                counter_name="executor_configured_estimator_not_provider_tokenizer",
            )
            self.assertLessEqual(context.token_count, 80)
            self.assertIn("not_provider_tokenizer", context.token_counter_name)
            executor.close()

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
