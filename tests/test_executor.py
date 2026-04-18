from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from stagewarden.config import AgentConfig
from stagewarden.executor import Executor
from stagewarden.memory import MemoryStore
from stagewarden.modelprefs import ModelPreferences, extract_blocked_until
from stagewarden.planner import PlanStep
from stagewarden.project_handoff import ProjectHandoff
from stagewarden.router import ModelRouter
from stagewarden.tools.git import GitTool


class FakeHandoff:
    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self.outputs = outputs
        self.calls: list[str] = []
        self.model_variant_by_model: dict[str, str] = {}
        self.account_env_by_target: dict[str, str] = {}

    def execute(self, command: str):  # noqa: ANN001
        self.calls.append(command)
        payload = self.outputs.pop(0)
        return type("ModelResult", (), payload)()


class ExecutorTests(unittest.TestCase):
    def test_extracts_chatgpt_usage_limit_time(self) -> None:
        message = (
            "You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), "
            "visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 8:05 PM."
        )
        until = extract_blocked_until(message, now=datetime(2026, 4, 18, 19, 0))
        self.assertEqual(until, "2026-04-18T20:05")

    def test_extracts_chatgpt_usage_limit_time_next_day_if_passed(self) -> None:
        message = "You've hit your usage limit. Try again at 8:05 PM."
        until = extract_blocked_until(message, now=datetime(2026, 4, 18, 21, 0))
        self.assertEqual(until, "2026-04-19T20:05")

    def test_executor_writes_file_from_model_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir))
            memory = MemoryStore()
            handoff = FakeHandoff(
                [
                    {
                        "ok": True,
                        "model": "local",
                        "backend": "local/ollama",
                        "prompt": "x",
                        "command": "run_model local x",
                        "output": json.dumps(
                            {
                                "summary": "write file",
                                "action": {
                                    "type": "write_file",
                                    "path": "hello.txt",
                                    "content": "ciao\n",
                                },
                            }
                        ),
                        "error": "",
                    }
                ]
            )
            executor = Executor(
                config=config,
                router=ModelRouter(),
                handoff=handoff,
                memory=memory,
            )
            step = PlanStep(
                id="step-1",
                title="Implement",
                instruction="implement create file",
                validation="The target files or behavior exist and are internally consistent.",
            )

            outcome = executor.execute_step(
                task="create a file",
                step=step,
                plan=[step],
                iteration=1,
                last_observation="none",
            )

            self.assertTrue(outcome.ok)
            self.assertTrue(outcome.step_completed)
            self.assertTrue((Path(tmp_dir) / "hello.txt").exists())

    def test_executor_tracks_invalid_output_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir))
            memory = MemoryStore()
            handoff = FakeHandoff(
                [
                    {
                        "ok": True,
                        "model": "local",
                        "backend": "local/ollama",
                        "prompt": "x",
                        "command": "run_model local x",
                        "output": "not-json",
                        "error": "",
                    }
                ]
            )
            executor = Executor(
                config=config,
                router=ModelRouter(),
                handoff=handoff,
                memory=memory,
            )
            step = PlanStep(id="step-1", title="Bad", instruction="implement", validation="check")
            outcome = executor.execute_step(
                task="create a file",
                step=step,
                plan=[step],
                iteration=1,
                last_observation="none",
            )

            self.assertFalse(outcome.ok)
            self.assertEqual(memory.failure_count("step-1"), 1)

    def test_executor_can_patch_file_with_unified_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "hello.txt"
            target.write_text("ciao\nmondo\n")
            config = AgentConfig(workspace_root=Path(tmp_dir))
            memory = MemoryStore()
            handoff = FakeHandoff(
                [
                    {
                        "ok": True,
                        "model": "local",
                        "backend": "local/ollama",
                        "prompt": "x",
                        "command": "run_model local x",
                        "output": json.dumps(
                            {
                                "summary": "patch file",
                                "action": {
                                    "type": "patch_file",
                                    "path": "hello.txt",
                                    "diff": "@@ -1,2 +1,2 @@\n ciao\n-mondo\n+mondo!\n",
                                },
                            }
                        ),
                        "error": "",
                    }
                ]
            )
            executor = Executor(config=config, router=ModelRouter(), handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Patch", instruction="implement patch", validation="check")
            outcome = executor.execute_step(task="patch file", step=step, plan=[step], iteration=1, last_observation="none")
            self.assertTrue(outcome.ok)
            self.assertIn("mondo!", target.read_text())

    def test_executor_can_list_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "a.txt").write_text("x")
            (root / "b.py").write_text("print('x')\n")
            config = AgentConfig(workspace_root=root)
            memory = MemoryStore()
            handoff = FakeHandoff(
                [
                    {
                        "ok": True,
                        "model": "local",
                        "backend": "local/ollama",
                        "prompt": "x",
                        "command": "run_model local x",
                        "output": json.dumps(
                            {"summary": "list files", "action": {"type": "list_files", "pattern": "*.py"}}
                        ),
                        "error": "",
                    }
                ]
            )
            executor = Executor(config=config, router=ModelRouter(), handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="List", instruction="inspect files", validation="check")
            outcome = executor.execute_step(task="list python files", step=step, plan=[step], iteration=1, last_observation="none")
            self.assertTrue(outcome.ok)
            self.assertIn("b.py", outcome.observation)

    def test_executor_can_query_git_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root)
            git = GitTool(config)
            self.assertTrue(git.ensure_ready().ok)
            (root / "tracked.txt").write_text("tracked\n")
            self.assertTrue(git.commit_if_changed("test: tracked").ok)
            memory = MemoryStore()
            handoff = FakeHandoff(
                [
                    {
                        "ok": True,
                        "model": "local",
                        "backend": "local/ollama",
                        "prompt": "x",
                        "command": "run_model local x",
                        "output": json.dumps(
                            {"summary": "inspect git history", "action": {"type": "git_file_history", "path": "tracked.txt", "limit": 5}}
                        ),
                        "error": "",
                    }
                ]
            )
            executor = Executor(config=config, router=ModelRouter(), handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="History", instruction="inspect git history", validation="history exists")
            outcome = executor.execute_step(task="inspect history", step=step, plan=[step], iteration=1, last_observation="none")
            self.assertTrue(outcome.ok)
            self.assertIn("test: tracked", outcome.observation)

    def test_executor_can_patch_multiple_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "a.txt").write_text("hello\n")
            config = AgentConfig(workspace_root=root)
            memory = MemoryStore()
            diff = "\n".join(
                [
                    "--- a/a.txt",
                    "+++ b/a.txt",
                    "@@ -1,1 +1,1 @@",
                    "-hello",
                    "+hello world",
                    "--- /dev/null",
                    "+++ b/b.txt",
                    "@@ -0,0 +1,1 @@",
                    "+new file",
                ]
            )
            handoff = FakeHandoff(
                [
                    {
                        "ok": True,
                        "model": "local",
                        "backend": "local/ollama",
                        "prompt": "x",
                        "command": "run_model local x",
                        "output": json.dumps({"summary": "patch files", "action": {"type": "patch_files", "diff": diff}}),
                        "error": "",
                    }
                ]
            )
            executor = Executor(config=config, router=ModelRouter(), handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Patch", instruction="implement patch", validation="check")
            outcome = executor.execute_step(task="patch files", step=step, plan=[step], iteration=1, last_observation="none")
            self.assertTrue(outcome.ok)
            self.assertEqual((root / "a.txt").read_text(), "hello world\n")
            self.assertEqual((root / "b.txt").read_text(), "new file\n")

    def test_executor_persists_model_block_from_usage_limit_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir))
            memory = MemoryStore()
            router = ModelRouter()
            router.configure(enabled_models=["openai", "local"], preferred_model="openai")
            handoff = FakeHandoff(
                [
                    {
                        "ok": False,
                        "model": "openai",
                        "backend": "openai/GPT-5.4",
                        "prompt": "x",
                        "command": "run_model openai x",
                        "output": "",
                        "error": "You've hit your usage limit. Try again at 8:05 PM.",
                    },
                    {
                        "ok": True,
                        "model": "local",
                        "backend": "local/ollama",
                        "prompt": "x",
                        "command": "run_model local x",
                        "output": json.dumps({"summary": "done", "action": {"type": "complete", "message": "validation completed exit_code=0"}}),
                        "error": "",
                    },
                ]
            )
            executor = Executor(config=config, router=router, handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Analyze", instruction="analyze simple task", validation="done")
            outcome = executor.execute_step(
                task="analyze task",
                step=step,
                plan=[step],
                iteration=1,
                last_observation="none",
            )
            prefs = ModelPreferences.load(Path(tmp_dir) / ".stagewarden_models.json")
            self.assertTrue(outcome.ok)
            self.assertIn("openai", prefs.blocked_until_by_model or {})
            self.assertIsNone(prefs.preferred_model)

    def test_executor_retries_same_model_with_next_account_after_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["openai", "local"]
            prefs.preferred_model = "openai"
            prefs.add_account("openai", "work", "OPENAI_API_KEY_WORK")
            prefs.add_account("openai", "personal", "OPENAI_API_KEY_PERSONAL")
            prefs.set_active_account("openai", "work")
            prefs.save(config.model_prefs_path)
            memory = MemoryStore()
            router = ModelRouter()
            router.configure(enabled_models=["openai", "local"], preferred_model="openai")
            handoff = FakeHandoff(
                [
                    {
                        "ok": False,
                        "model": "openai",
                        "backend": "openai/GPT-5.4",
                        "prompt": "x",
                        "command": "run_model openai x",
                        "account": "work",
                        "output": "",
                        "error": "You've hit your usage limit. Try again at 8:05 PM.",
                    },
                    {
                        "ok": True,
                        "model": "openai",
                        "backend": "openai/GPT-5.4",
                        "prompt": "x",
                        "command": "run_model openai x",
                        "account": "personal",
                        "output": json.dumps({"summary": "done", "action": {"type": "complete", "message": "validation completed exit_code=0"}}),
                        "error": "",
                    },
                ]
            )
            executor = Executor(config=config, router=router, handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Analyze", instruction="debug complex traceback", validation="done")
            outcome = executor.execute_step(task="debug complex traceback", step=step, plan=[step], iteration=1, last_observation="none")
            updated = ModelPreferences.load(config.model_prefs_path)
            self.assertTrue(outcome.ok)
            self.assertIn("RUN_MODEL: openai:work", handoff.calls[0])
            self.assertIn("RUN_MODEL: openai:personal", handoff.calls[1])
            self.assertIn("openai:work", updated.blocked_until_by_account or {})

    def test_executor_rejects_dry_run_completion_as_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir))
            memory = MemoryStore()
            handoff = FakeHandoff(
                [
                    {
                        "ok": True,
                        "model": "local",
                        "backend": "local/ollama",
                        "prompt": "x",
                        "command": "run_model local x",
                        "output": json.dumps(
                            {
                                "summary": "dry-run only",
                                "action": {
                                    "type": "complete",
                                    "message": "dry-run passed but no wet-run was executed",
                                },
                            }
                        ),
                        "error": "",
                    }
                ]
            )
            executor = Executor(config=config, router=ModelRouter(), handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Validate", instruction="validate result", validation="wet-run required")
            outcome = executor.execute_step(
                task="validate task",
                step=step,
                plan=[step],
                iteration=1,
                last_observation="none",
            )
            self.assertFalse(outcome.ok)
            self.assertFalse(outcome.step_completed)
            self.assertEqual(outcome.error_type, "wet_run_required")

    def test_executor_sets_automatic_provider_variant_when_not_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir))
            memory = MemoryStore()
            handoff = FakeHandoff(
                [
                    {
                        "ok": True,
                        "model": "claude",
                        "backend": "claude/sonnet",
                        "prompt": "x",
                        "command": "run_model claude x",
                        "output": json.dumps({"summary": "done", "action": {"type": "complete", "message": "validation completed exit_code=0"}}),
                        "error": "",
                    }
                ]
            )
            router = ModelRouter()
            router.configure(enabled_models=["claude"], preferred_model="claude")
            executor = Executor(config=config, router=router, handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Analyze", instruction="debug complex traceback", validation="done")
            outcome = executor.execute_step(task="debug complex traceback in production", step=step, plan=[step], iteration=1, last_observation="none")

            self.assertTrue(outcome.ok)
            self.assertEqual(handoff.model_variant_by_model.get("claude"), "opus")

    def test_executor_keeps_pinned_provider_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["claude"]
            prefs.preferred_model = "claude"
            prefs.set_variant("claude", "sonnet")
            prefs.save(root / ".stagewarden_models.json")

            config = AgentConfig(workspace_root=root)
            memory = MemoryStore()
            handoff = FakeHandoff(
                [
                    {
                        "ok": True,
                        "model": "claude",
                        "backend": "claude/sonnet",
                        "prompt": "x",
                        "command": "run_model claude x",
                        "output": json.dumps({"summary": "done", "action": {"type": "complete", "message": "validation completed exit_code=0"}}),
                        "error": "",
                    }
                ]
            )
            router = ModelRouter()
            router.configure(enabled_models=["claude"], preferred_model="claude")
            executor = Executor(config=config, router=router, handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Analyze", instruction="debug complex traceback", validation="done")
            outcome = executor.execute_step(task="debug complex traceback in production", step=step, plan=[step], iteration=1, last_observation="none")

            self.assertTrue(outcome.ok)
            self.assertEqual(handoff.model_variant_by_model.get("claude"), "sonnet")

    def test_executor_prompt_includes_handoff_context_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir))
            memory = MemoryStore()
            project_handoff = ProjectHandoff()
            project_handoff.start_run(task="fix failing tests", plan_status="step-1:pending", git_head="abc123")
            project_handoff.begin_step(
                iteration=1,
                task="fix failing tests",
                step_id="step-1",
                step_title="1. Analyze",
                step_status="in_progress",
                git_head="abc123",
            )
            project_handoff.complete_step(
                iteration=1,
                task="fix failing tests",
                step_id="step-1",
                step_title="1. Analyze",
                step_status="completed",
                model="openai",
                action_type="git_status",
                observation="working tree clean",
                git_head="abc123",
            )
            handoff = FakeHandoff(
                [
                    {
                        "ok": True,
                        "model": "local",
                        "backend": "local/ollama",
                        "prompt": "x",
                        "command": "run_model local x",
                        "output": json.dumps({"summary": "done", "action": {"type": "complete", "message": "validation completed exit_code=0"}}),
                        "error": "",
                    }
                ]
            )
            executor = Executor(
                config=config,
                router=ModelRouter(),
                handoff=handoff,
                memory=memory,
                project_handoff=project_handoff,
            )
            step = PlanStep(id="step-2", title="Implement", instruction="implement fix", validation="done")
            outcome = executor.execute_step(task="fix failing tests", step=step, plan=[step], iteration=2, last_observation="working tree clean")

            self.assertTrue(outcome.ok)
            prompt = handoff.calls[0]
            self.assertIn("Implicit project handoff context:", prompt)
            self.assertIn("Recent handoff log:", prompt)
            self.assertIn("working tree clean", prompt)


if __name__ == "__main__":
    unittest.main()
