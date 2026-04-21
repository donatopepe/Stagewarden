from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from stagewarden.config import AgentConfig
from stagewarden.executor import Executor
from stagewarden.memory import MemoryStore
from stagewarden.modelprefs import ModelPreferences, classify_limit_reason, extract_blocked_until
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
        self.model_params_by_model: dict[str, dict[str, str]] = {}

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

    def test_classifies_usage_limit_reason(self) -> None:
        reason = classify_limit_reason("You've hit your usage limit. Try again at 8:05 PM.")
        self.assertEqual(reason, "usage_limit")

    def test_classifies_credits_exhausted_reason(self) -> None:
        reason = classify_limit_reason(
            "Upgrade to Pro, purchase more credits or try again at 8:05 PM."
        )
        self.assertEqual(reason, "credits_exhausted")

    def test_classifies_rate_limit_reason(self) -> None:
        reason = classify_limit_reason("Rate limit exceeded. Too many requests.")
        self.assertEqual(reason, "rate_limit")

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
            self.assertTrue(memory.tool_transcript)
            self.assertEqual(memory.tool_transcript[-1].tool, "files")
            self.assertEqual(memory.tool_transcript[-1].action_type, "write_file")
            self.assertIn("hello.txt", memory.tool_transcript[-1].summary)

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

    def test_executor_accepts_strict_model_result_schema(self) -> None:
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
                                "summary": "complete with validation",
                                "confidence": 0.9,
                                "risks": ["none"],
                                "validation": "wet-run evidence included",
                                "action": {
                                    "type": "complete",
                                    "message": "validation completed exit_code=0",
                                },
                            }
                        ),
                        "error": "",
                    }
                ]
            )
            executor = Executor(config=config, router=ModelRouter(), handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Validate", instruction="validate", validation="done")
            outcome = executor.execute_step(task="validate", step=step, plan=[step], iteration=1, last_observation="none")

            self.assertTrue(outcome.ok)
            self.assertTrue(outcome.step_completed)

    def test_executor_rejects_invalid_model_result_schema(self) -> None:
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
                                "summary": "bad confidence",
                                "confidence": "high",
                                "risks": [],
                                "validation": "none",
                                "action": {"type": "complete", "message": "validation completed exit_code=0"},
                            }
                        ),
                        "error": "",
                    }
                ]
            )
            executor = Executor(config=config, router=ModelRouter(), handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Validate", instruction="validate", validation="done")
            outcome = executor.execute_step(task="validate", step=step, plan=[step], iteration=1, last_observation="none")

            self.assertFalse(outcome.ok)
            self.assertEqual(outcome.action_type, "invalid_output")
            self.assertIn("confidence", outcome.observation)
            self.assertEqual(memory.failure_count("step-1"), 1)

    def test_executor_denies_unknown_destructive_model_action(self) -> None:
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
                                "summary": "bad action",
                                "action": {"type": "delete_workspace", "path": "."},
                            }
                        ),
                        "error": "",
                    }
                ]
            )
            executor = Executor(config=config, router=ModelRouter(), handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Validate", instruction="validate", validation="done")
            outcome = executor.execute_step(task="validate", step=step, plan=[step], iteration=1, last_observation="none")

            self.assertFalse(outcome.ok)
            self.assertEqual(outcome.action_type, "invalid_output")
            self.assertIn("Unknown destructive action denied", outcome.observation)

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

    def test_executor_can_preview_patch_multiple_files_without_writing(self) -> None:
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
                        "output": json.dumps(
                            {"summary": "preview patch files", "action": {"type": "preview_patch_files", "diff": diff}}
                        ),
                        "error": "",
                    }
                ]
            )
            executor = Executor(config=config, router=ModelRouter(), handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Preview", instruction="inspect patch", validation="check")
            outcome = executor.execute_step(task="preview patch files", step=step, plan=[step], iteration=1, last_observation="none")

            self.assertTrue(outcome.ok)
            self.assertIn("Patch preview", outcome.observation)
            self.assertIn("update a.txt", outcome.observation)
            self.assertEqual((root / "a.txt").read_text(), "hello\n")
            self.assertEqual(memory.tool_transcript[-1].action_type, "preview_patch_files")

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
            self.assertIn("openai", prefs.last_limit_message_by_model or {})
            self.assertIn("usage limit", (prefs.last_limit_message_by_model or {})["openai"].lower())
            snapshot = (prefs.provider_limit_snapshot_by_model or {})["openai"]
            self.assertEqual(snapshot["status"], "blocked")
            self.assertEqual(snapshot["reason"], "usage_limit")
            self.assertEqual(snapshot["blocked_until"], (prefs.blocked_until_by_model or {})["openai"])
            self.assertIn("usage limit", str(snapshot["raw_message"]).lower())
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
            self.assertIn("openai:work", updated.last_limit_message_by_account or {})
            account_snapshot = (updated.provider_limit_snapshot_by_account or {})["openai:work"]
            self.assertEqual(account_snapshot["status"], "blocked")
            self.assertEqual(account_snapshot["reason"], "usage_limit")

    def test_executor_prompts_rate_limit_decision_when_no_provider_alternative_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            decisions: list[tuple[str, str | None, list[str]]] = []
            config = AgentConfig(
                workspace_root=root,
                rate_limit_decider=lambda provider, until, alternatives: decisions.append((provider, until, alternatives)) or "wait",
            )
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["openai"]
            prefs.preferred_model = "openai"
            prefs.save(config.model_prefs_path)
            memory = MemoryStore()
            router = ModelRouter()
            router.configure(enabled_models=["openai"], preferred_model="openai")
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
                ]
            )
            executor = Executor(config=config, router=router, handoff=handoff, memory=memory)
            step = PlanStep(id="step-1", title="Analyze", instruction="debug complex traceback", validation="done")
            outcome = executor.execute_step(task="debug complex traceback", step=step, plan=[step], iteration=1, last_observation="none")
            updated = ModelPreferences.load(config.model_prefs_path)

            self.assertFalse(outcome.ok)
            self.assertEqual(outcome.error_type, "rate_limit_wait")
            self.assertEqual(decisions[0][0], "openai")
            self.assertEqual(decisions[0][2], [])
            self.assertIn("openai", updated.blocked_until_by_model or {})
            self.assertEqual(len(handoff.calls), 1)

    def test_executor_retries_all_available_accounts_on_same_model_until_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["openai", "local"]
            prefs.preferred_model = "openai"
            prefs.add_account("openai", "work", "OPENAI_API_KEY_WORK")
            prefs.add_account("openai", "personal", "OPENAI_API_KEY_PERSONAL")
            prefs.add_account("openai", "backup", "OPENAI_API_KEY_BACKUP")
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
                        "ok": False,
                        "model": "openai",
                        "backend": "openai/GPT-5.4",
                        "prompt": "x",
                        "command": "run_model openai x",
                        "account": "personal",
                        "output": "",
                        "error": "You've hit your usage limit. Try again at 8:05 PM.",
                    },
                    {
                        "ok": True,
                        "model": "openai",
                        "backend": "openai/GPT-5.4",
                        "prompt": "x",
                        "command": "run_model openai x",
                        "account": "backup",
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
            self.assertIn("RUN_MODEL: openai:backup", handoff.calls[2])
            self.assertIn("openai:work", updated.blocked_until_by_account or {})
            self.assertIn("openai:personal", updated.blocked_until_by_account or {})

    def test_executor_routes_step_through_configured_prince2_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["local", "openai"]
            prefs.set_prince2_role_assignment(
                "team_manager",
                mode="manual",
                provider="openai",
                provider_model="gpt-5.4-mini",
                params={"reasoning_effort": "low"},
                source="unit_test",
            )
            prefs.save(config.model_prefs_path)
            memory = MemoryStore()
            router = ModelRouter()
            router.configure(enabled_models=["local", "openai"])
            project_handoff = ProjectHandoff(task="implement feature")
            project_handoff.sync_prince2_roles(dict(prefs.prince2_roles or {}))
            project_handoff.risk_register = [{"risk": "business risk outside team domain", "status": "open"}]
            project_handoff.exception_plan = ["change authority only"]
            handoff = FakeHandoff(
                [
                    {
                        "ok": True,
                        "model": "openai",
                        "backend": "openai/GPT-5.4",
                        "prompt": "x",
                        "command": "run_model openai x",
                        "output": json.dumps({"summary": "done", "action": {"type": "complete", "message": "validation completed exit_code=0"}}),
                        "error": "",
                    },
                ]
            )
            executor = Executor(config=config, router=router, handoff=handoff, memory=memory, project_handoff=project_handoff)
            step = PlanStep(id="step-2", title="Implement feature", instruction="implement requested code change", validation="validate")
            outcome = executor.execute_step(task="implement feature", step=step, plan=[step], iteration=1, last_observation="none")

            self.assertTrue(outcome.ok)
            self.assertEqual(outcome.model, "openai")
            self.assertEqual(outcome.variant, "gpt-5.4-mini")
            self.assertEqual(outcome.prince2_role, "team_manager")
            self.assertEqual(handoff.model_params_by_model["openai"]["reasoning_effort"], "low")
            self.assertIn("RUN_MODEL: openai", handoff.calls[0])
            self.assertIn("active_role: team_manager", handoff.calls[0])
            self.assertIn("context_scope: current work package, product delivery, quality criteria, and implementation lessons only", handoff.calls[0])
            self.assertIn("active_role_route: provider=openai provider_model=gpt-5.4-mini", handoff.calls[0])
            self.assertIn("Risks:\nOmitted by PRINCE2 role scope.", handoff.calls[0])
            self.assertIn("Exception plan:\nOmitted by PRINCE2 role scope.", handoff.calls[0])
            self.assertNotIn("business risk outside team domain", handoff.calls[0])

    def test_executor_retries_fallback_model_with_next_account_after_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["openai", "chatgpt", "local"]
            prefs.preferred_model = "openai"
            prefs.add_account("openai", "primary", "OPENAI_API_KEY_PRIMARY")
            prefs.set_active_account("openai", "primary")
            prefs.add_account("chatgpt", "work", "CHATGPT_TOKEN_WORK")
            prefs.add_account("chatgpt", "backup", "CHATGPT_TOKEN_BACKUP")
            prefs.set_active_account("chatgpt", "work")
            prefs.save(config.model_prefs_path)
            memory = MemoryStore()
            router = ModelRouter()
            router.configure(enabled_models=["openai", "chatgpt", "local"], preferred_model="openai")
            handoff = FakeHandoff(
                [
                    {
                        "ok": False,
                        "model": "openai",
                        "backend": "openai/GPT-5.4",
                        "prompt": "x",
                        "command": "run_model openai x",
                        "account": "primary",
                        "output": "",
                        "error": "You've hit your usage limit. Try again at 8:05 PM.",
                    },
                    {
                        "ok": False,
                        "model": "chatgpt",
                        "backend": "chatgpt/GPT-5",
                        "prompt": "x",
                        "command": "run_model chatgpt x",
                        "account": "work",
                        "output": "",
                        "error": "You've hit your usage limit. Try again at 8:05 PM.",
                    },
                    {
                        "ok": True,
                        "model": "chatgpt",
                        "backend": "chatgpt/GPT-5",
                        "prompt": "x",
                        "command": "run_model chatgpt x",
                        "account": "backup",
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
            self.assertIn("RUN_MODEL: openai:primary", handoff.calls[0])
            self.assertIn("RUN_MODEL: chatgpt:work", handoff.calls[1])
            self.assertIn("RUN_MODEL: chatgpt:backup", handoff.calls[2])
            self.assertIn("openai:primary", updated.blocked_until_by_account or {})
            self.assertIn("chatgpt:work", updated.blocked_until_by_account or {})

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
            memory.record_attempt(
                iteration=1,
                step_id="step-1",
                model="openai",
                action_type="git_status",
                action_signature='{"type":"git_status"}',
                success=True,
                observation="working tree clean",
            )
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
            project_handoff.record_issue(
                step_id="step-1",
                severity="medium",
                summary="validation pending",
            )
            project_handoff.record_quality(
                step_id="step-1",
                status="passed",
                evidence="working tree clean",
            )
            project_handoff.record_lesson(
                step_id="step-1",
                lesson_type="success",
                lesson="git inspection should precede file edits",
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
            self.assertIn("Model context files:", prompt)
            self.assertIn("handoff_file: .stagewarden_handoff.json", prompt)
            self.assertIn("memory_file: .stagewarden_memory.json", prompt)
            self.assertIn("trace_file: .stagewarden_trace.ljson", prompt)
            self.assertIn("recovery_state:", prompt)
            self.assertIn("backlog_status:", prompt)
            self.assertIn("git_boundary:", prompt)
            self.assertIn("git_dirty_state:", prompt)
            self.assertIn("Implicit project handoff context:", prompt)
            self.assertIn("Stage boundary view:", prompt)
            self.assertIn("PRINCE2 registers:", prompt)
            self.assertIn("Risks:", prompt)
            self.assertIn("Issues:", prompt)
            self.assertIn("Quality:", prompt)
            self.assertIn("Lessons:", prompt)
            self.assertIn("Exception plan:", prompt)
            self.assertIn("active_role: team_manager", prompt)
            self.assertIn("Issues:\nOmitted by PRINCE2 role scope.", prompt)
            self.assertNotIn("validation pending", prompt)
            self.assertIn("git inspection should precede file edits", prompt)
            self.assertIn("Recent handoff log:", prompt)
            self.assertIn("Recent execution log:", prompt)
            self.assertIn("Omitted by PRINCE2 role scope.", prompt)
            self.assertIn("working tree clean", prompt)
            self.assertIn("boundary_decision: continue_current_stage", prompt)

    def test_executor_prompt_context_sections_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir))
            memory = MemoryStore()
            project_handoff = ProjectHandoff()
            for index in range(120):
                project_handoff.risk_register.append(
                    {"risk": f"risk-{index} " + ("x" * 120), "status": "open"}
                )
            executor = Executor(
                config=config,
                router=ModelRouter(),
                handoff=FakeHandoff([]),
                memory=memory,
                project_handoff=project_handoff,
            )
            step = PlanStep(id="step-1", title="Plan", instruction="plan controlled delivery", validation="done")

            prompt = executor._build_prompt(task="large context", step=step, plan=[step], last_observation="none")

            self.assertIn("[truncated risk_register:", prompt)
            self.assertLess(len(prompt), 40000)


if __name__ == "__main__":
    unittest.main()
