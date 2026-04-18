from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig
from stagewarden.ljson import decode, load_file
from stagewarden.modelprefs import ModelPreferences
from stagewarden.main import run_interactive_shell


ROOT = Path(__file__).resolve().parents[1]


def run_main_in_cwd(cwd: Path, *args: str) -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        ["python3", "-m", "stagewarden.main", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.returncode


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

    def test_ljson_cli_uses_clear_default_gzip_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "records.json"
            source.write_text(json.dumps([{"id": 1, "name": "Mario"}]), encoding="utf-8")

            encoded_code = run_main_in_cwd(root, "--ljson-encode", str(source), "--ljson-gzip")
            encoded = root / "records.ljson.gz"
            self.assertEqual(encoded_code, 0)
            self.assertTrue(encoded.exists())

            decoded_code = run_main_in_cwd(root, "--ljson-decode", str(encoded))
            decoded = root / "records.json"
            self.assertEqual(decoded_code, 0)
            self.assertEqual(json.loads(decoded.read_text(encoding="utf-8")), [{"id": 1, "name": "Mario"}])

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
            self.assertIn("model use <local|cheap|chatgpt|gpt|claude>", rendered)
            self.assertIn("model block <local|cheap|chatgpt|gpt|claude> until YYYY-MM-DDTHH:MM", rendered)
            self.assertIn("Git commands:", rendered)
            self.assertIn("git history <path> [limit]", rendered)
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

    def test_interactive_shell_manages_model_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "account add gpt lavoro OPENAI_API_KEY_WORK\n"
                "account add gpt personale OPENAI_API_KEY_PERSONAL\n"
                "account use gpt personale\n"
                "account block gpt lavoro until 2026-05-01T18:30\n"
                "accounts\n"
                "models\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("gpt"), "personale")
            self.assertEqual((prefs.env_var_by_account or {}).get("gpt:lavoro"), "OPENAI_API_KEY_WORK")
            self.assertIn("gpt:lavoro", prefs.blocked_until_by_account or {})
            self.assertIn("account personale:", rendered)
            self.assertIn("active-account", rendered)
            self.assertIn("env=OPENAI_API_KEY_WORK", rendered)

    def test_interactive_shell_logs_in_account_and_saves_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            original_skip = os.environ.get("STAGEWARDEN_SKIP_BROWSER")
            original_auto = os.environ.get("STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            os.environ["STAGEWARDEN_SKIP_BROWSER"] = "1"
            os.environ["STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN"] = "gpt-browser-token"
            try:
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO("account login gpt lavoro\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                prefs = ModelPreferences.load(root / ".stagewarden_models.json")
                from stagewarden.secrets import SecretStore

                loaded = SecretStore().load_token("gpt", "lavoro")
            finally:
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store
                if original_skip is None:
                    os.environ.pop("STAGEWARDEN_SKIP_BROWSER", None)
                else:
                    os.environ["STAGEWARDEN_SKIP_BROWSER"] = original_skip
                if original_auto is None:
                    os.environ.pop("STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN", None)
                else:
                    os.environ["STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN"] = original_auto

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("gpt"), "lavoro")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertEqual(loaded.secret, "gpt-browser-token")
            self.assertIn("token=stored", rendered)

    def test_interactive_shell_logs_in_chatgpt_account_and_saves_session_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            original_skip = os.environ.get("STAGEWARDEN_SKIP_BROWSER")
            original_auto = os.environ.get("STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            os.environ["STAGEWARDEN_SKIP_BROWSER"] = "1"
            os.environ["STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN"] = "chatgpt-session-token"
            try:
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO("account login chatgpt personale\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                prefs = ModelPreferences.load(root / ".stagewarden_models.json")
                from stagewarden.secrets import SecretStore

                loaded = SecretStore().load_token("chatgpt", "personale")
            finally:
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store
                if original_skip is None:
                    os.environ.pop("STAGEWARDEN_SKIP_BROWSER", None)
                else:
                    os.environ["STAGEWARDEN_SKIP_BROWSER"] = original_skip
                if original_auto is None:
                    os.environ.pop("STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN", None)
                else:
                    os.environ["STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN"] = original_auto

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("chatgpt"), "personale")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertEqual(loaded.secret, "chatgpt-session-token")
            self.assertIn("token=stored", rendered)

    def test_interactive_shell_logs_in_claude_account_and_saves_session_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            original_skip = os.environ.get("STAGEWARDEN_SKIP_BROWSER")
            original_auto = os.environ.get("STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            os.environ["STAGEWARDEN_SKIP_BROWSER"] = "1"
            os.environ["STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN"] = "claude-session-token"
            try:
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO("account login claude lavoro\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                prefs = ModelPreferences.load(root / ".stagewarden_models.json")
                from stagewarden.secrets import SecretStore

                loaded = SecretStore().load_token("claude", "lavoro")
            finally:
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store
                if original_skip is None:
                    os.environ.pop("STAGEWARDEN_SKIP_BROWSER", None)
                else:
                    os.environ["STAGEWARDEN_SKIP_BROWSER"] = original_skip
                if original_auto is None:
                    os.environ.pop("STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN", None)
                else:
                    os.environ["STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN"] = original_auto

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("claude"), "lavoro")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertEqual(loaded.secret, "claude-session-token")
            self.assertIn("token=stored", rendered)

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

    def test_interactive_shell_status_and_mode_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("status\nmode caveman ultra\nstatus\nmode normal\nstatus\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Stagewarden status:", rendered)
            self.assertIn("mode: normal", rendered)
            self.assertIn("Caveman mode active. Level: ultra.", rendered)
            self.assertIn("mode: caveman ultra", rendered)
            self.assertIn("Caveman mode disabled.", rendered)
            self.assertFalse((root / ".stagewarden_caveman.json").exists())

    def test_interactive_shell_can_query_git_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            agent = Agent(config)
            (root / "tracked.txt").write_text("tracked\n")
            self.assertTrue(agent.git.commit_if_changed("test: tracked").ok)

            input_stream = StringIO("git status\ngit log 5\ngit history tracked.txt 5\ngit show --stat HEAD\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("test: tracked", rendered)
            self.assertIn("tracked.txt", rendered)
            self.assertIn("Session closed.", rendered)


if __name__ == "__main__":
    unittest.main()
