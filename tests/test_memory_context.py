from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import PropertyMock, patch
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
            self.assertTrue(all(isinstance(item, str) for item in compacted.report()["diagnostics"]))
            self.assertIn("truncated by memory token budget", compacted.content)

    def test_counter_failure_after_compaction_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("memory payload " * 100, encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            calls = 0
            def flaky_counter(text: str) -> int:
                nonlocal calls
                calls += 1
                if calls == 1:
                    return len(text)
                raise RuntimeError("counter transient failure")
            context = load_memory_context(root, path, max_tokens=10, token_counter=flaky_counter)
            self.assertFalse(context.ok)
            self.assertEqual(context.content, "")
            self.assertIn("counter transient failure", context.report()["diagnostics"][0])

    def test_discontinuous_counter_never_returns_over_budget_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("abcdef" * 50, encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            def discontinuous(text: str) -> int:
                if text == "\n[truncated by memory token budget]":
                    return 35
                if "truncated by memory token budget" in text:
                    return 100
                return len(text)
            context = load_memory_context(root, path, max_tokens=40, token_counter=discontinuous)
            self.assertFalse(context.ok)
            self.assertEqual(context.content, "")
            self.assertIn("no truncated memory candidate fits", context.report()["diagnostics"][0])

    def test_marker_budget_failure_returns_zero_count_and_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("source text " * 10, encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            def counter(text: str) -> int:
                if text == "":
                    raise AssertionError("no-fit marker case must return without recounting empty text")
                if "truncated by memory token budget" in text:
                    return 50
                return len(text)
            context = load_memory_context(root, path, max_tokens=40, token_counter=counter)
            self.assertFalse(context.ok)
            self.assertEqual(context.content, "")
            self.assertEqual(context.token_count, 0)
            self.assertIn("token budget too small", context.report()["diagnostics"][0])
            self.assertEqual(context.report()["issue_count"], len(context.report()["issues"]))

    def test_no_fit_counter_failure_does_not_report_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("source text " * 10, encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            def discontinuous(text: str) -> int:
                if text == "\n[truncated by memory token budget]":
                    return 5
                if "truncated by memory token budget" in text:
                    return 100
                return len(text) if len(text) > 20 else 100
            context = load_memory_context(root, path, max_tokens=40, token_counter=discontinuous)
            self.assertFalse(context.ok)
            self.assertEqual(context.content, "")
            self.assertIn("no truncated memory candidate fits", context.report()["diagnostics"][0])

    def test_counter_rejection_clears_original_content_that_exceeded_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("large original payload " * 20, encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            def counter(text: str) -> int:
                if "truncated by memory token budget" in text:
                    return 100
                return len(text)
            context = load_memory_context(root, path, max_tokens=40, token_counter=counter)
            self.assertFalse(context.ok)
            self.assertEqual(context.content, "")
            self.assertLessEqual(context.token_count, 40)
            self.assertIn("token budget too small", context.report()["diagnostics"][0])

    def test_no_fit_path_does_not_run_final_counter_on_cleared_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("large source text " * 20, encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            def counter(text: str) -> int:
                if text == "":
                    raise AssertionError("counter must not be called on cleared no-fit content")
                if text == "\n[truncated by memory token budget]":
                    return 1
                if "truncated by memory token budget" in text:
                    return 100
                return len(text)
            context = load_memory_context(root, path, max_tokens=40, token_counter=counter)
            self.assertFalse(context.ok)
            self.assertEqual(context.content, "")
            self.assertEqual(context.token_count, 0)
            self.assertIn("no truncated memory candidate fits", context.report()["diagnostics"][0])

    def test_nonmonotonic_counter_that_rejects_every_sample_is_not_treated_as_fitting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("x" * 1000, encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            def counter(text: str) -> int:
                if text == "\n[truncated by memory token budget]":
                    return 1
                if "truncated by memory token budget" in text:
                    return 100
                return len(text)
            context = load_memory_context(root, path, max_tokens=40, token_counter=counter)
            self.assertFalse(context.ok)
            self.assertEqual(context.content, "")
            self.assertEqual(context.token_count, 0)
            self.assertIn("no truncated memory candidate fits", context.report()["diagnostics"][0])

    def test_token_counter_exception_during_binary_search_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("abcdef" * 50, encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            calls = 0
            def counter(text: str) -> int:
                nonlocal calls
                calls += 1
                if calls > 2:
                    raise RuntimeError("search failed")
                return len(text)
            context = load_memory_context(root, path, max_tokens=40, token_counter=counter, token_counter_name="flaky")
            self.assertFalse(context.ok)
            self.assertEqual(context.content, "")
            self.assertIn("search failed", context.report()["diagnostics"][0])

    def test_non_monotonic_counter_does_not_escape_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("abcdef" * 50, encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            def non_monotonic(text: str) -> int:
                if "truncated by memory token budget" in text:
                    return 5
                if len(text) > 30:
                    return 200
                return len(text)
            context = load_memory_context(root, path, max_tokens=40, token_counter=non_monotonic)
            self.assertTrue(context.ok)
            self.assertLessEqual(context.token_count, 40)
            self.assertIn("truncated by memory token budget", context.content)

    def test_final_counter_type_failure_fails_closed_with_counter_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("short memory", encoding="utf-8")
            path = self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            calls = 0
            def counter(text: str):
                nonlocal calls
                calls += 1
                return len(text) if calls == 1 else True
            context = load_memory_context(
                root, path, max_tokens=1000, token_counter=counter,
                token_counter_name="bad-final-counter",
            )
            self.assertFalse(context.ok)
            self.assertEqual(context.content, "")
            self.assertEqual(context.token_counter_name, "bad-final-counter")
            self.assertIn("invalid count", context.report()["diagnostics"][0])

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
            self.assertLessEqual(executor._estimate_memory_tokens(section.body), 80)
            self.assertIn("not_provider_tokenizer", section.body)
            executor.close()

    def test_budget_loop_does_not_reload_memory_on_error_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("private payload", encoding="utf-8")
            self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            calls = 0
            original = type(executor.config).memory_context_with_budget
            def fail_second_load(config, max_tokens, token_counter, *, counter_name):
                nonlocal calls
                calls += 1
                if calls > 1:
                    raise AssertionError("memory loader repeated in budget error handling")
                return original(config, max_tokens, token_counter, counter_name=counter_name)
            with patch.object(type(executor.config), "memory_context_with_budget", new=fail_second_load):
                step = PlanStep(id="step", title="Read", instruction="inspect", validation="v")
                packet = executor._build_model_communication_packet(
                    task="inspect", step=step, plan=[step], last_observation="none",
                    provider_limits={"available_input": 1},
                )
            section = next(item for item in packet.sections if item.title == "Configured Hermes/Obsidian memory")
            self.assertLessEqual(calls, 1)
            self.assertNotIn("private payload", section.body)
            self.assertIn("metadata exceeds available input budget", section.body)
            executor.close()

    def test_model_context_metadata_uses_explicit_resolved_memory_not_mutable_executor_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            from stagewarden.memory_context import MemoryContext, MemoryContextIssue
            resolved = MemoryContext(True, "", (), (MemoryContextIssue("error", "resolved failure"),), 500)
            executor._external_memory_context = MemoryContext(False, "", (), (), 500)
            report = __import__("stagewarden.executor_prompting", fromlist=["model_context_files_section"]).model_context_files_section(
                executor, external_memory_context=resolved,
            )
            self.assertIn("configured_markdown_memory: enabled=True", report)
            self.assertIn("issues=1", report)
            executor.close()

    def test_prompt_memory_loader_exception_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("private durable payload", encoding="utf-8")
            self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            step = PlanStep(id="step", title="Read", instruction="inspect", validation="v")
            with patch.object(type(executor.config), "memory_context", new_callable=PropertyMock, side_effect=OSError("loader disk failure")):
                packet = executor._build_model_communication_packet(task="inspect", step=step, plan=[step], last_observation="none")
            section = next(item for item in packet.sections if item.title == "Configured Hermes/Obsidian memory")
            self.assertNotIn("private durable payload", section.body)
            self.assertIn("loader disk failure", section.body)
            executor.close()

    def test_prompt_memory_budget_counter_exception_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("sensitive memory " * 20, encoding="utf-8")
            self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            calls = 0
            def counter(text: str) -> int:
                nonlocal calls
                calls += 1
                if calls > 2:
                    raise RuntimeError("outer section counter failure")
                return len(text)
            executor._estimate_memory_tokens = counter
            step = PlanStep(id="step", title="Read context", instruction="inspect", validation="v")
            packet = executor._build_model_communication_packet(
                task="inspect", step=step, plan=[step], last_observation="none",
                provider_limits={"available_input": 10},
            )
            section = next(item for item in packet.sections if item.title == "Configured Hermes/Obsidian memory")
            self.assertNotIn("sensitive memory", section.body)
            self.assertIn("outer section counter failure", section.body)
            executor.close()

    def test_budget_error_paths_clear_untrusted_memory_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("sensitive cached fragment " * 50, encoding="utf-8")
            self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            executor._estimate_memory_tokens = lambda text: 100
            step = PlanStep(id="step", title="Read", instruction="inspect", validation="v")
            packet = executor._build_model_communication_packet(
                task="inspect", step=step, plan=[step], last_observation="none",
                provider_limits={"available_input": 1},
            )
            section = next(item for item in packet.sections if item.title == "Configured Hermes/Obsidian memory")
            self.assertNotIn("sensitive cached fragment", section.body)
            self.assertIn("metadata exceeds available input budget", section.body)
            self.assertFalse(executor._external_memory_context.ok)
            self.assertEqual(executor._external_memory_context.content, "")
            executor.close()

    def test_prompt_memory_budget_reports_nonconverging_outer_counter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("brief memory", encoding="utf-8")
            self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            executor._estimate_memory_tokens = lambda text: 100
            step = PlanStep(id="step", title="Read context", instruction="inspect", validation="context")
            packet = executor._build_model_communication_packet(
                task="inspect", step=step, plan=[step], last_observation="none",
                provider_limits={"available_input": 1},
            )
            section = next(item for item in packet.sections if item.title == "Configured Hermes/Obsidian memory")
            self.assertIn("metadata exceeds available input budget", section.body)
            self.assertNotIn("brief memory", section.body)
            executor.close()

    def test_prompt_memory_budget_too_small_for_metadata_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("tiny context", encoding="utf-8")
            self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"]}})
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            step = PlanStep(id="step", title="Read context", instruction="inspect", validation="context")
            packet = executor._build_model_communication_packet(
                task="inspect", step=step, plan=[step], last_observation="none",
                provider_limits={"available_input": 1},
            )
            section = next(item for item in packet.sections if item.title == "Configured Hermes/Obsidian memory")
            self.assertNotIn("tiny context", section.body)
            self.assertIn("metadata exceeds available input budget", section.body)
            # A one-unit budget cannot contain required section/diagnostic framing;
            # source memory is still excluded and outer prompt compaction owns that limit.
            executor.close()

    def test_legacy_memory_char_cap_is_applied_to_final_rendered_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory"
            memory.mkdir()
            (memory / "pi-memory.md").write_text("ordinary durable fact " * 200, encoding="utf-8")
            self.settings(root, {"memory": {"enabled": True, "roots": [str(memory)], "files": ["pi-memory.md"], "max_chars": 500}})
            executor = Executor(config=AgentConfig(workspace_root=root), router=ModelRouter(), handoff=HandoffManager(), memory=MemoryStore(), project_handoff=ProjectHandoff(), rag=DesignRag())
            step = PlanStep(id="step", title="Read context", instruction="inspect", validation="v")
            packet = executor._build_model_communication_packet(
                task="inspect", step=step, plan=[step], last_observation="none",
                provider_limits={"available_input": 1000},
            )
            section = next(item for item in packet.sections if item.title == "Configured Hermes/Obsidian memory")
            self.assertLessEqual(len(section.body), 500 + len("\n[truncated by hermes_obsidian_memory]"))
            self.assertIn("ordinary durable fact", section.body)
            self.assertIn("truncated", section.body)
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
