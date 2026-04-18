from __future__ import annotations

import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig
from stagewarden.ljson import decode, load_file
from stagewarden.modelprefs import ModelPreferences
from stagewarden.main import run_interactive_shell


class TraceAndCliTests(unittest.TestCase):
    def test_agent_writes_ljson_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            agent.run("simple task")
            self.assertTrue((root / ".stagewarden_trace.ljson").exists())
            payload = json.loads((root / ".stagewarden_trace.ljson").read_text())
            self.assertIn("_fields", payload)
            self.assertGreaterEqual(len(decode(payload)), 1)

    def test_load_file_roundtrip_from_dumped_ljson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sample = root / "sample.ljson"
            sample.write_text(json.dumps({"_version": 1, "_fields": ["id"], "data": [[1], [2]]}))
            self.assertEqual(load_file(sample), [{"id": 1}, {"id": 2}])

    def test_interactive_shell_handles_help_and_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=1)
            input_stream = StringIO("help\nmodels\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Stagewarden interactive shell", rendered)
            self.assertIn("Core commands:", rendered)
            self.assertIn("Model commands:", rendered)
            self.assertIn("Caveman commands:", rendered)
            self.assertIn("Examples:", rendered)
            self.assertIn("model use <local|cheap|gpt|claude>", rendered)
            self.assertIn("model block <local|cheap|gpt|claude> until YYYY-MM-DDTHH:MM", rendered)
            self.assertIn("Model configuration:", rendered)
            self.assertIn("Session closed.", rendered)

    def test_interactive_shell_executes_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = "/Users/donato/Stagewarden/run_model_stub"
            try:
                config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=6)
                input_stream = StringIO("create a file named hello.txt\nquit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp_dir) / "hello.txt").exists())

    def test_agent_resets_system_prompt_each_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            agent = Agent(AgentConfig(workspace_root=Path(tmp_dir), max_steps=1))
            base = agent.base_system_prompt
            agent.run("simple task")
            first_prompt = agent.executor.config.system_prompt
            agent.run("simple task")
            second_prompt = agent.executor.config.system_prompt
            self.assertIn("PRINCE2 agent policy", first_prompt)
            self.assertIn("PRINCE2 agent policy", second_prompt)
            self.assertEqual(second_prompt.count("PRINCE2 agent policy"), 1)
            self.assertEqual(base, agent.base_system_prompt)

    def test_interactive_shell_persists_model_preference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("model use cheap\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            self.assertEqual(code, 0)
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertEqual(prefs.preferred_model, "cheap")
            self.assertIn("cheap", prefs.enabled_models)

    def test_interactive_shell_supports_caveman_alias_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=1)
            input_stream = StringIO("caveman help\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Caveman commands:", rendered)
            self.assertIn("/caveman review", rendered)

    def test_interactive_shell_persists_model_block_until_datetime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("model block gpt until 2026-05-01T18:30\nmodels\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertEqual((prefs.blocked_until_by_model or {}).get("gpt"), "2026-05-01T18:30")
            self.assertIn("blocked-until=2026-05-01T18:30", rendered)


if __name__ == "__main__":
    unittest.main()
