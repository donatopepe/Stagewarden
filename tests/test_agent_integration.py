from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig
from stagewarden.modelprefs import ModelPreferences
from stagewarden.project_handoff import ProjectHandoff


class AgentIntegrationTests(unittest.TestCase):
    def test_agent_completes_task_with_stub_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = "/Users/donato/run_model_stub"
            try:
                agent = Agent(
                    AgentConfig(
                        workspace_root=Path(tmp_dir),
                        max_steps=10,
                        verbose=False,
                    )
                )
                result = agent.run("create a file named hello.txt")
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            self.assertTrue(result.ok)
            self.assertTrue((Path(tmp_dir) / "hello.txt").exists())
            self.assertTrue((Path(tmp_dir) / ".git").exists())
            self.assertIn("Stage boundary:", result.message)
            self.assertIn("boundary_decision:", result.message)
            log = subprocess.run(
                ["git", "-C", tmp_dir, "log", "--oneline"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertIn("stagewarden:", log.stdout)

    def test_agent_failure_summary_contains_exception_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = "/Users/donato/run_model_stub"
            try:
                agent = Agent(
                    AgentConfig(
                        workspace_root=root,
                        max_steps=2,
                        verbose=False,
                    )
                )
                result = agent.run("create a file named hello.txt")
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            self.assertFalse(result.ok)
            self.assertIn("Stage boundary:", result.message)
            self.assertIn("exception_plan:", result.message)

    def test_agent_verbose_output_shows_handoff_runtime_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["openai", "local"]
            prefs.preferred_model = "openai"
            prefs.add_account("openai", "work", "OPENAI_API_KEY_WORK")
            prefs.set_variant("openai", "gpt-5.4-mini")
            prefs.save(root / ".stagewarden_models.json")

            original = os.environ.get("RUN_MODEL_BIN")
            original_key = os.environ.get("OPENAI_API_KEY_WORK")
            os.environ["RUN_MODEL_BIN"] = "/Users/donato/run_model_stub"
            os.environ["OPENAI_API_KEY_WORK"] = "work-token"
            try:
                output = StringIO()
                with redirect_stdout(output):
                    agent = Agent(
                        AgentConfig(
                            workspace_root=root,
                            max_steps=10,
                            verbose=True,
                        )
                    )
                    result = agent.run("create a file named hello.txt")
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original
                if original_key is None:
                    os.environ.pop("OPENAI_API_KEY_WORK", None)
                else:
                    os.environ["OPENAI_API_KEY_WORK"] = original_key

            rendered = output.getvalue()
            self.assertTrue(result.ok)
            self.assertIn("variant=gpt-5.4-mini", rendered)
            self.assertIn("account=work", rendered)
            self.assertIn("git_head_before=", rendered)
            self.assertIn("git_head_after=", rendered)

    def test_agent_closes_matching_open_issues_on_immediate_project_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = ProjectHandoff(
                task="create a file named hello.txt",
                status="exception",
                current_step_id="step-3",
                current_step_title="3. Validate the implementation",
                current_step_status="completed",
                latest_observation="validation completed",
                plan_status="step-1:completed,step-2:completed,step-3:completed",
                issue_register=[
                    {"step_id": "step-3", "severity": "medium", "summary": "validation pending", "status": "open"}
                ],
                exception_plan=["review boundary for step-3"],
            )
            handoff.save(root / ".stagewarden_handoff.json")

            agent = Agent(AgentConfig(workspace_root=root, max_steps=10, verbose=False))
            result = agent.run("create a file named hello.txt")

            self.assertTrue(result.ok)
            saved = ProjectHandoff.load(root / ".stagewarden_handoff.json")
            matching = [item for item in saved.issue_register if item.get("step_id") == "step-3"]
            self.assertTrue(matching)
            self.assertTrue(all(item.get("status") == "closed" for item in matching))
            self.assertEqual(saved.exception_plan, [])


if __name__ == "__main__":
    unittest.main()
