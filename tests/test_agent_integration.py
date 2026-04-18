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


def write_success_stub(root: Path) -> Path:
    path = root / "run_model_success_stub.py"
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import json",
                "import re",
                "import sys",
                "",
                "def extract(prompt: str, field: str) -> str:",
                '    match = re.search(rf"^{re.escape(field)}=(.+)$", prompt, re.MULTILINE)',
                "    return match.group(1).strip() if match else ''",
                "",
                "def detect_target_file(text: str) -> str | None:",
                '    match = re.search(r"file named ([A-Za-z0-9._/\\\\-]+)", text, re.IGNORECASE)',
                "    return match.group(1) if match else None",
                "",
                "def main() -> int:",
                "    if len(sys.argv) < 3:",
                "        print(json.dumps({'error': 'usage: stub <model> <prompt>'}))",
                "        return 1",
                "    prompt = sys.argv[2]",
                "    instruction = extract(prompt, 'instruction').lower()",
                "    task_match = re.search(r'Task:\\n(.+?)\\n\\nImplicit project handoff context:', prompt, re.DOTALL)",
                "    task = task_match.group(1).strip() if task_match else ''",
                "    if instruction.startswith('analyze') or instruction.startswith('inspect') or instruction.startswith('resume 1.') or instruction.startswith('resume 3.'):",
                "        action = {'type': 'complete', 'message': 'analysis validated exit_code=0'}",
                "    elif 'implement' in instruction or 'create' in instruction or 'build' in instruction or instruction.startswith('resume 2.'):",
                "        target = detect_target_file(f'{instruction} {task}') or 'stub_output.txt'",
                "        action = {'type': 'write_file', 'path': target, 'content': 'created by test stub\\n'}",
                "    else:",
                "        action = {'type': 'complete', 'message': 'validation completed exit_code=0'}",
                "    print(json.dumps({'summary': 'stub response', 'action': action}))",
                "    return 0",
                "",
                "if __name__ == '__main__':",
                "    raise SystemExit(main())",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


class AgentIntegrationTests(unittest.TestCase):
    def test_agent_completes_task_with_stub_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            stub = write_success_stub(root)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                agent = Agent(
                    AgentConfig(
                        workspace_root=root,
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
            self.assertTrue((root / "hello.txt").exists())
            self.assertTrue((root / ".git").exists())
            self.assertIn("Stage boundary:", result.message)
            self.assertIn("boundary_decision:", result.message)
            log = subprocess.run(
                ["git", "-C", str(root), "log", "--oneline"],
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
            stub = write_success_stub(root)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["openai", "local"]
            prefs.preferred_model = "openai"
            prefs.add_account("openai", "work", "OPENAI_API_KEY_WORK")
            prefs.set_variant("openai", "gpt-5.4-mini")
            prefs.save(root / ".stagewarden_models.json")

            original = os.environ.get("RUN_MODEL_BIN")
            original_key = os.environ.get("OPENAI_API_KEY_WORK")
            os.environ["RUN_MODEL_BIN"] = str(stub)
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
                risk_register=[
                    {"risk": "regression from final patch", "status": "open"},
                ],
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
            self.assertTrue(all(item.get("status") == "closed" for item in saved.risk_register))
            self.assertEqual(saved.exception_plan, [])


if __name__ == "__main__":
    unittest.main()
