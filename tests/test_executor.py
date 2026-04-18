from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_cli.config import AgentConfig
from agent_cli.executor import Executor
from agent_cli.memory import MemoryStore
from agent_cli.planner import PlanStep
from agent_cli.router import ModelRouter


class FakeHandoff:
    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self.outputs = outputs
        self.calls: list[str] = []

    def execute(self, command: str):  # noqa: ANN001
        self.calls.append(command)
        payload = self.outputs.pop(0)
        return type("ModelResult", (), payload)()


class ExecutorTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
