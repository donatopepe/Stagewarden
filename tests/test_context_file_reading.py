from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewarden.config import AgentConfig
from stagewarden.executor import Executor
from stagewarden.handoff import HandoffManager
from stagewarden.memory import MemoryStore
from stagewarden.planner import PlanStep
from stagewarden.project_handoff import ProjectHandoff
from stagewarden.router import ModelRouter
from stagewarden.rag import DesignRag
from stagewarden.tools.files import FileTool


class ContextAwareFileReadingTests(unittest.TestCase):
    def _executor(self, root: Path, **kwargs: object) -> Executor:
        config = AgentConfig(workspace_root=root, **kwargs)
        return Executor(
            config=config,
            router=ModelRouter(),
            handoff=HandoffManager(),
            memory=MemoryStore(),
            project_handoff=ProjectHandoff(),
            rag=DesignRag(),
        )

    def test_chunk_reader_reports_offsets_and_reconstructs_complete_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = "0123456789" * 2000
            (root / "large.txt").write_text(expected, encoding="utf-8")
            tool = FileTool(AgentConfig(workspace_root=root, file_chunk_chars=137))
            chunks = list(tool.iter_chunks("large.txt", chunk_chars=137))
            self.assertGreater(len(chunks), 1)
            self.assertEqual("".join(item.content for item in chunks), expected)
            self.assertEqual(chunks[0].report["start"], 0)
            self.assertEqual(chunks[-1].report["end"], len(expected))
            self.assertFalse(chunks[-1].report["has_more"])

    def test_read_file_chunk_directory_error_emits_failure_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "directory").mkdir()
            executor = self._executor(root, file_chunk_chars=5)
            result = executor._run_action(
                {"type": "read_file_chunk", "path": "directory", "start": 0, "size": 5},
                step_id="node.directory",
            )
            # 1. Directory read returns structured file failure.
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_type"], "file_error")
            self.assertEqual(result["report"]["effective_size"], 5)
            # 2. IO failure emits failed event.
            failures = executor.events.read(node_id="node.directory", event="file_read_failure")
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["details"]["status"], "failed")
            # 3. Replay keeps node failure state.
            self.assertEqual(executor.events.replay(node_id="node.directory")["nodes"]["node.directory"]["status"], "failed")
            executor.close()

    def test_read_file_chunk_missing_file_emits_failure_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor = self._executor(root, file_chunk_chars=5)
            result = executor._run_action(
                {"type": "read_file_chunk", "path": "missing.txt", "start": 0, "size": 5},
                step_id="node.chunk",
            )
            # 1. Missing chunk returns structured failure.
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_type"], "file_error")
            # 2. Failure event includes path/status.
            failures = executor.events.read(node_id="node.chunk", event="file_read_failure")
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["details"]["status"], "failed")
            self.assertEqual(failures[0]["details"]["path"], "missing.txt")
            # 3. Replay exposes node-scoped failure.
            state = executor.events.replay(node_id="node.chunk")["nodes"]["node.chunk"]
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["path"], "missing.txt")
            executor.close()

    def test_read_file_complete_missing_file_emits_failure_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor = self._executor(root, file_chunk_chars=5)
            result = executor._run_action(
                {"type": "read_file_complete", "path": "missing.txt", "chunk_size": 5},
                step_id="node.missing",
            )
            # 1. Missing source returns structured failure.
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_type"], "file_error")
            # 2. Missing source emits failed node event.
            failures = executor.events.read(node_id="node.missing", event="file_read_failure")
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["details"]["status"], "failed")
            self.assertEqual(failures[0]["details"]["path"], "missing.txt")
            # 3. Replay exposes failure metadata for node.
            state = executor.events.replay(node_id="node.missing")["nodes"]["node.missing"]
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["path"], "missing.txt")
            executor.close()

    def test_read_file_complete_repeated_action_returns_structured_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("abcdefghij", encoding="utf-8")
            executor = self._executor(root, file_chunk_chars=5)
            action = {"type": "read_file_complete", "path": "source.txt", "chunk_size": 5}
            # 1. First complete read succeeds.
            first = executor._run_action(action, step_id="node.repeat")
            self.assertTrue(first["ok"])
            # 2. Repeated read returns structured file failure, not exception.
            second = executor._run_action(action, step_id="node.repeat")
            self.assertFalse(second["ok"])
            self.assertEqual(second["error_type"], "file_error")
            self.assertIn("complete", second["message"].lower())
            # 3. Recovery failure is visible for node replay.
            failures = executor.events.read(node_id="node.repeat", event="file_read_failure")
            self.assertEqual(len(failures), 1)
            self.assertEqual(executor.events.replay(node_id="node.repeat")["nodes"]["node.repeat"]["status"], "failed")
            executor.close()

    def test_file_read_complete_failure_event_has_failed_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            source.write_text("abcdefghij", encoding="utf-8")
            executor = self._executor(root, file_chunk_chars=5)
            original_read = executor.files.read_chunk
            calls = 0

            def read_chunk(path: str, *, start: int = 0, size: int | None = None):
                nonlocal calls
                result = original_read(path, start=start, size=size)
                calls += 1
                if calls == 1:
                    source.write_text("ABCDEfghij", encoding="utf-8")
                return result

            executor.files.read_chunk = read_chunk
            result = executor._run_action(
                {"type": "read_file_complete", "path": "source.txt", "chunk_size": 5},
                step_id="node.status",
            )
            self.assertFalse(result["ok"])
            failure = executor.events.read(node_id="node.status", event="file_read_failure")
            self.assertEqual(failure[0]["details"]["status"], "failed")
            self.assertEqual(executor.events.replay(node_id="node.status")["nodes"]["node.status"]["status"], "failed")
            executor.close()

    def test_read_file_complete_drift_emits_failure_event_for_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            source.write_text("abcdefghij", encoding="utf-8")
            executor = self._executor(root, file_chunk_chars=5)
            original_read = executor.files.read_chunk
            calls = 0

            def read_chunk(path: str, *, start: int = 0, size: int | None = None):
                nonlocal calls
                result = original_read(path, start=start, size=size)
                calls += 1
                if calls == 1:
                    source.write_text("ABCDEfghij", encoding="utf-8")
                return result

            executor.files.read_chunk = read_chunk
            result = executor._run_action(
                {"type": "read_file_complete", "path": "source.txt", "chunk_size": 5},
                step_id="node.drift",
            )
            # 1. Drift result remains fail-closed.
            self.assertFalse(result["ok"])
            # 2. Failure event records scoped path/error.
            failures = executor.events.read(node_id="node.drift", event="file_read_failure")
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["details"]["path"], "source.txt")
            self.assertIn("hash", failures[0]["details"]["error"].lower())
            # 3. Replay projects failure only for selected node.
            replay = executor.events.replay(node_id="node.drift")
            self.assertEqual(set(replay["nodes"]), {"node.drift"})
            self.assertEqual(replay["nodes"]["node.drift"]["last_event"], "file_read_failure")
            executor.close()

    def test_read_file_complete_rejects_source_drift_and_shortened_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original = "abcdefghij"

            def run_case(name: str, replacement: str | None, mutate_after_call: int) -> dict[str, object]:
                case_root = Path(tmp) / name
                case_root.mkdir()
                source = case_root / "source.txt"
                source.write_text(original, encoding="utf-8")
                executor = self._executor(case_root, file_chunk_chars=5)
                first_read = executor.files.read_chunk
                calls = 0

                def read_chunk(path: str, *, start: int = 0, size: int | None = None):
                    nonlocal calls
                    result = first_read(path, start=start, size=size)
                    calls += 1
                    if calls == mutate_after_call:
                        source.write_text(replacement or "", encoding="utf-8")
                    return result

                executor.files.read_chunk = read_chunk
                try:
                    return executor._run_action(
                        {"type": "read_file_complete", "path": "source.txt", "chunk_size": 5},
                        step_id="node.drift",
                    )
                finally:
                    executor.close()

            # 1. Stable source completes.
            stable = run_case("stable", None, 99)
            self.assertTrue(stable["ok"])
            # 2. Same-length mutation after final chunk is caught by final probe.
            changed = run_case("same-length", "ABCDEfghij", 3)
            self.assertFalse(changed["ok"])
            self.assertIn("hash", str(changed["message"]).lower())
            # 3. Shortened source after opening an empty file is caught by final probe.
            shortened = run_case("shortened", "ABCDE", 1)
            self.assertFalse(shortened["ok"])
            self.assertIn("hash", str(shortened["message"]).lower())

    def test_read_file_complete_action_returns_full_content_beyond_chunk_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = "line\n" * 5000
            (root / "large.txt").write_text(expected, encoding="utf-8")
            executor = self._executor(root, file_chunk_chars=100)
            result = executor._run_action({"type": "read_file_complete", "path": "large.txt", "chunk_size": 100})
            self.assertTrue(result["ok"])
            self.assertEqual(result["content"], expected)
            self.assertGreater(result["report"]["chunks"], 1)
            self.assertTrue(result["report"]["complete"])
            self.assertNotIn(expected, result["message"])
            self.assertIn("content_ref", result["report"])

    def test_chunk_size_is_capped_and_compaction_runs_when_context_is_full(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "large.txt").write_text("x" * 1000, encoding="utf-8")
            executor = self._executor(
                root,
                context_window_tokens=100,
                context_reserved_output_tokens=20,
                context_safety_margin_tokens=10,
                context_chars_per_token=4,
                file_chunk_chars=500,
            )
            executor._active_context_budget = executor._context_budget("cheap")
            executor._active_prompt_chars = 390
            result = executor._run_action(
                {"type": "read_file_chunk", "path": "large.txt", "start": 0, "size": 500},
                step_id="node.read",
            )
            self.assertTrue(result["ok"])
            self.assertTrue(result["report"]["auto_compacted"])
            self.assertLessEqual(len(result["content"]), 500)
            self.assertGreater(executor._context_compaction_count, 0)

    def test_chunk_event_records_context_budget_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("x" * 1000, encoding="utf-8")
            executor = self._executor(
                root,
                context_window_tokens=100,
                context_reserved_output_tokens=20,
                context_safety_margin_tokens=10,
                file_chunk_chars=500,
            )
            executor._active_context_budget = executor._context_budget("cheap")
            executor._active_prompt_chars = 390
            result = executor._run_action(
                {"type": "read_file_chunk", "path": "source.txt", "start": 0, "size": 500},
                step_id="node.read",
            )
            self.assertTrue(result["ok"])
            chunk_events = executor.events.read(event="file_chunk")
            self.assertGreaterEqual(len(chunk_events), 1)
            details = next(event["details"] for event in chunk_events if "available_input_tokens" in event["details"])
            self.assertIn("available_input_tokens", details)
            self.assertIn("prompt_chars_before", details)
            self.assertIn("prompt_chars_after", details)
            self.assertTrue(details["auto_compacted"])
            executor.close()

    def test_compaction_event_records_context_budget_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor = self._executor(
                root,
                context_window_tokens=100,
                context_reserved_output_tokens=20,
                context_safety_margin_tokens=10,
            )
            step = PlanStep("step-1", "Inspect", "inspect repository", "run tests", wet_run_required=False)
            budget = executor._context_budget("cheap")
            executor._build_prompt(task="x" * 1000, step=step, plan=[step], last_observation="y" * 1000, context_budget=budget)
            events = executor.events.read(event="context_compaction")
            self.assertEqual(len(events), 1)
            details = events[0]["details"]
            self.assertIn("available_input_tokens", details)
            self.assertIn("max_chars", details)
            self.assertIn("before_chars", details)
            self.assertIn("after_chars", details)
            self.assertLess(details["after_chars"], details["before_chars"])
            executor.close()

    def test_context_budget_matrix_records_provider_node_and_replay_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            source.write_text("x" * 1000, encoding="utf-8")
            executor = self._executor(root, context_window_tokens=120, context_reserved_output_tokens=20, context_safety_margin_tokens=10, file_chunk_chars=500)
            executor._active_context_budget = executor._context_budget("cheap")
            executor._active_prompt_chars = 390
            result = executor._run_action({"type": "read_file_chunk", "path": "source.txt", "start": 0, "size": 500}, step_id="node.context")
            self.assertTrue(result["ok"])
            report = result["report"]
            self.assertTrue(report["auto_compacted"])
            self.assertLessEqual(report["effective_size"], 165)
            self.assertGreater(report["effective_size"], 0)
            replay = executor.events.replay(node_id="node.context")
            self.assertTrue(replay["nodes"])
            node_state = replay["nodes"]["node.context"]
            self.assertIn(node_state["last_event"], {"file_chunk", "tool_result"})
            chunk_events = executor.events.read(node_id="node.context", event="file_chunk")
            self.assertTrue(chunk_events)
            details = next(event["details"] for event in chunk_events if "available_input_tokens" in event["details"])
            self.assertIn("available_input_tokens", details)
            self.assertLess(details["prompt_chars_after"], details["prompt_chars_before"] + report["effective_size"])
            executor.close()

    def test_context_budget_matrix_covers_user_budget_and_replay_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("x" * 400, encoding="utf-8")
            executor = self._executor(root, context_window_tokens=200, context_reserved_output_tokens=40, context_safety_margin_tokens=20, file_chunk_chars=300)
            budget = executor._context_budget("cheap")
            self.assertEqual(budget["context_window"], 200)
            self.assertEqual(budget["available_input"], 140)
            executor._active_context_budget = budget
            executor._active_prompt_chars = 500
            result = executor._run_action({"type": "read_file_chunk", "path": "source.txt", "start": 0, "size": 300}, step_id="node.budget")
            self.assertTrue(result["ok"])
            replay = executor.events.replay(node_id="node.budget")
            self.assertIn("node.budget", replay["nodes"])
            self.assertEqual(replay["nodes"]["node.budget"]["last_event"], "tool_result")
            chunk_events = executor.events.read(node_id="node.budget", event="file_chunk")
            details = next(event["details"] for event in chunk_events if "available_input_tokens" in event["details"])
            self.assertEqual(details["available_input_tokens"], 140)
            self.assertIn(details["auto_compacted"], {False, True})
            self.assertGreaterEqual(details["prompt_chars_after"], details["prompt_chars_before"])
            executor.close()

    def test_context_budget_provider_node_matrix_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            source.write_text("x" * 1000, encoding="utf-8")
            executor = self._executor(root, context_window_tokens=100, context_reserved_output_tokens=20, context_safety_margin_tokens=10, file_chunk_chars=500)
            budget = executor._context_budget("cheap")
            # 1. budget identity
            for key in ("provider", "model", "context_window", "input_limit", "reserved_output", "safety_margin", "available_input"):
                self.assertIn(key, budget)
            # 2. node chunk identity and budget
            executor._active_context_budget = budget
            executor._active_prompt_chars = 390
            chunk = executor._run_action({"type": "read_file_chunk", "path": "source.txt", "start": 0, "size": 500}, step_id="node.context")
            self.assertTrue(chunk["ok"])
            details = next(item["details"] for item in executor.events.read(node_id="node.context", event="file_chunk") if "available_input_tokens" in item["details"])
            for key in ("node_id", "provider", "model", "context_window", "input_limit", "reserved_output", "safety_margin", "available_input_tokens"):
                self.assertIn(key, {**details, "node_id": "node.context"})
            # 3. compaction identity and budget
            step = PlanStep("step-1", "Inspect", "inspect repository", "run tests", wet_run_required=False)
            executor._build_prompt(task="x" * 1000, step=step, plan=[step], last_observation="y" * 1000, context_budget=budget)
            compact = executor.events.read(event="context_compaction")
            self.assertTrue(compact)
            compact_details = compact[-1]["details"]
            for key in ("provider", "model", "context_window", "input_limit", "reserved_output", "safety_margin", "available_input_tokens"):
                self.assertIn(key, compact_details)
            executor.close()

    def test_context_provider_selection_matrix_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            source.write_text("x" * 1000, encoding="utf-8")
            executor = self._executor(root, context_window_tokens=100, context_reserved_output_tokens=20, context_safety_margin_tokens=10, file_chunk_chars=500)
            # 1. explicitly selected cheap identity
            cheap = executor._context_budget("cheap")
            self.assertEqual(cheap["provider"], "cheap")
            self.assertEqual(cheap["available_input"], 70)
            # 2. explicitly selected chatgpt identity
            chatgpt = executor._context_budget("chatgpt")
            self.assertEqual(chatgpt["provider"], "chatgpt")
            self.assertEqual(chatgpt["available_input"], 70)
            # 3. selected budget propagates into node events
            executor._active_context_budget = chatgpt
            executor._active_prompt_chars = 390
            result = executor._run_action({"type": "read_file_chunk", "path": "source.txt", "start": 0, "size": 500}, step_id="node.chatgpt")
            self.assertTrue(result["ok"])
            details = next(item["details"] for item in executor.events.read(node_id="node.chatgpt", event="file_chunk") if "available_input_tokens" in item["details"])
            self.assertEqual(details["provider"], "chatgpt")
            self.assertEqual(details["available_input_tokens"], 70)
            executor.close()

    def test_context_budget_boundary_matrix_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("x" * 200, encoding="utf-8")
            # 1. reserved output + margin exceed configured window: available=0, chunk remains bounded.
            executor = self._executor(root, context_window_tokens=20, context_reserved_output_tokens=15, context_safety_margin_tokens=10, file_chunk_chars=100)
            zero = executor._context_budget("cheap")
            self.assertEqual(zero["available_input"], 0)
            executor._active_context_budget = zero
            result = executor._run_action({"type": "read_file_chunk", "path": "source.txt", "start": 0, "size": 100}, step_id="node.zero")
            self.assertTrue(result["ok"])
            self.assertGreater(result["report"]["effective_size"], 0)
            # 2. unknown provider catalog must remain unknown, not guessed.
            unknown_executor = self._executor(root, context_window_tokens=None, context_reserved_output_tokens=0, context_safety_margin_tokens=0)
            unknown = unknown_executor._context_budget("unknown-provider")
            self.assertIsNone(unknown["context_window"])
            self.assertIsNone(unknown["available_input"])
            # 3. exact available boundary emits compaction metadata.
            boundary = self._executor(root, context_window_tokens=100, context_reserved_output_tokens=20, context_safety_margin_tokens=10)
            budget = boundary._context_budget("cheap")
            self.assertEqual(budget["available_input"], 70)
            step = PlanStep("step-boundary", "Inspect", "inspect", "run tests", wet_run_required=False)
            boundary._build_prompt(task="x" * 280, step=step, plan=[step], last_observation="y" * 280, context_budget=budget)
            events = boundary.events.read(event="context_compaction")
            self.assertTrue(events)
            self.assertEqual(events[-1]["details"]["available_input_tokens"], 70)
            executor.close()
            boundary.close()

    def test_prompt_compacts_when_configured_input_budget_is_small(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AgentConfig(workspace_root=root, context_window_tokens=100, context_reserved_output_tokens=20, context_safety_margin_tokens=10)
            executor = self._executor(root, context_window_tokens=100, context_reserved_output_tokens=20, context_safety_margin_tokens=10)
            step = PlanStep("step-1", "Inspect", "inspect repository", "run tests", wet_run_required=False)
            prompt = executor._build_prompt(task="x" * 1000, step=step, plan=[step], last_observation="y" * 1000, context_budget=executor._context_budget("cheap"))
            self.assertLessEqual(len(prompt), 70 * config.context_chars_per_token)
            self.assertIn("automatic node-context compaction", prompt)


if __name__ == "__main__":
    unittest.main()
