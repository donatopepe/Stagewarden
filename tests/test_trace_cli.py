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
            self.assertTrue((root / ".stagewarden_handoff.json").exists())
            payload = json.loads((root / ".stagewarden_trace.ljson").read_text())
            self.assertIn("_fields", payload)
            self.assertGreaterEqual(len(decode(payload)), 1)
            handoff_payload = json.loads((root / ".stagewarden_handoff.json").read_text())
            self.assertEqual(handoff_payload.get("_format"), "stagewarden_project_handoff")
            self.assertIn("entries", handoff_payload)

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
            self.assertIn("- handoff", rendered)
            self.assertIn("model use <local|cheap|chatgpt|openai|claude>", rendered)
            self.assertIn("model list <local|cheap|chatgpt|openai|claude>", rendered)
            self.assertIn("model variant <local|cheap|chatgpt|openai|claude> <variant>", rendered)
            self.assertIn("model block <local|cheap|chatgpt|openai|claude> until YYYY-MM-DDTHH:MM", rendered)
            self.assertIn("account login-device <chatgpt|openai> <name>", rendered)
            self.assertIn("account import <model> <name> [PATH]", rendered)
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

    def test_interactive_shell_persists_provider_model_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("model variant claude opus\nmodel list claude\nmodels\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")

            self.assertEqual(code, 0)
            self.assertEqual((prefs.variant_by_model or {}).get("claude"), "opus")
            self.assertIn("Available variants for claude:", rendered)
            self.assertIn("opusplan", rendered)
            self.assertIn("variant=opus", rendered)

    def test_interactive_shell_manages_model_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "account add openai lavoro OPENAI_API_KEY_WORK\n"
                "account add openai personale OPENAI_API_KEY_PERSONAL\n"
                "account use openai personale\n"
                "account block openai lavoro until 2026-05-01T18:30\n"
                "accounts\n"
                "models\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("openai"), "personale")
            self.assertEqual((prefs.env_var_by_account or {}).get("openai:lavoro"), "OPENAI_API_KEY_WORK")
            self.assertIn("openai:lavoro", prefs.blocked_until_by_account or {})
            self.assertIn("account personale:", rendered)
            self.assertIn("active-account", rendered)
            self.assertIn("env=OPENAI_API_KEY_WORK", rendered)

    def test_interactive_shell_logs_in_account_and_saves_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                import stagewarden.main as main_module

                original_run = main_module.OpenAIDeviceCodeFlow.run

                def fake_run(self):  # noqa: ANN001
                    from stagewarden.auth import AuthResult

                    return AuthResult(
                        True,
                        "Device code login completed.",
                        token="access-token-123",
                        secret_payload='{"access_token":"access-token-123","refresh_token":"refresh-token-123"}',
                    )

                main_module.OpenAIDeviceCodeFlow.run = fake_run
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO("account login openai lavoro\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                prefs = ModelPreferences.load(root / ".stagewarden_models.json")
                from stagewarden.secrets import SecretStore

                loaded = SecretStore().load_token("openai", "lavoro")
            finally:
                main_module.OpenAIDeviceCodeFlow.run = original_run
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("openai"), "lavoro")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertIn('"refresh_token":"refresh-token-123"', loaded.secret)
            self.assertIn("Device code login completed.", rendered)
            self.assertIn("token=stored", rendered)

    def test_interactive_shell_logs_in_chatgpt_account_and_saves_session_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                import stagewarden.main as main_module

                original_run = main_module.OpenAIDeviceCodeFlow.run

                def fake_run(self):  # noqa: ANN001
                    from stagewarden.auth import AuthResult

                    return AuthResult(
                        True,
                        "Device code login completed.",
                        token="access-token-123",
                        secret_payload='{"access_token":"access-token-123","refresh_token":"refresh-token-123","id_token":"id-token-123"}',
                    )

                main_module.OpenAIDeviceCodeFlow.run = fake_run
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO("account login chatgpt personale\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                prefs = ModelPreferences.load(root / ".stagewarden_models.json")
                from stagewarden.secrets import SecretStore

                loaded = SecretStore().load_token("chatgpt", "personale")
            finally:
                main_module.OpenAIDeviceCodeFlow.run = original_run
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("chatgpt"), "personale")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertIn('"id_token":"id-token-123"', loaded.secret)
            self.assertIn("Device code login completed.", rendered)
            self.assertIn("token=stored", rendered)

    def test_interactive_shell_logs_in_openai_account_with_device_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            original_client = os.environ.get("STAGEWARDEN_OPENAI_CLIENT_ID")
            original_browser = os.environ.get("STAGEWARDEN_SKIP_BROWSER")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            os.environ["STAGEWARDEN_OPENAI_CLIENT_ID"] = "client-id"
            os.environ["STAGEWARDEN_SKIP_BROWSER"] = "1"
            try:
                import stagewarden.main as main_module

                original_run = main_module.OpenAIDeviceCodeFlow.run

                def fake_run(self):  # noqa: ANN001
                    from stagewarden.auth import AuthResult

                    return AuthResult(
                        True,
                        "Device code login completed.",
                        token="access-token-123",
                        secret_payload='{"access_token":"access-token-123","refresh_token":"refresh-token-123"}',
                    )

                main_module.OpenAIDeviceCodeFlow.run = fake_run
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO("account login-device openai lavoro\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                prefs = ModelPreferences.load(root / ".stagewarden_models.json")
                from stagewarden.secrets import SecretStore

                loaded = SecretStore().load_token("openai", "lavoro")
            finally:
                main_module.OpenAIDeviceCodeFlow.run = original_run
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store
                if original_client is None:
                    os.environ.pop("STAGEWARDEN_OPENAI_CLIENT_ID", None)
                else:
                    os.environ["STAGEWARDEN_OPENAI_CLIENT_ID"] = original_client
                if original_browser is None:
                    os.environ.pop("STAGEWARDEN_SKIP_BROWSER", None)
                else:
                    os.environ["STAGEWARDEN_SKIP_BROWSER"] = original_browser

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("openai"), "lavoro")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertIn('"refresh_token":"refresh-token-123"', loaded.secret)
            self.assertIn("Device code login completed.", rendered)

    def test_interactive_shell_rejects_interactive_claude_login(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("account login claude lavoro\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Interactive login is not supported for model 'claude'.", rendered)

    def test_interactive_shell_can_import_claude_credentials_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            credentials = root / ".credentials.json"
            credentials.write_text('{"auth_token":"claude-subscription-token","api_key":"console-key"}', encoding="utf-8")
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO(f"account import claude lavoro {credentials}\naccounts\nexit\n")
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

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("claude"), "lavoro")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertIn('"auth_token":"claude-subscription-token"', loaded.secret)
            self.assertIn("Imported credentials for claude:lavoro", rendered)

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
            input_stream = StringIO("model block openai until 2026-05-01T18:30\nmodels\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertEqual((prefs.blocked_until_by_model or {}).get("openai"), "2026-05-01T18:30")
            self.assertIn("blocked-until=2026-05-01T18:30", rendered)

    def test_interactive_shell_status_and_mode_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-3",
                "current_step_title": "Resume 3. Validate result",
                "current_step_status": "in_progress",
                "latest_observation": "implementation completed, wet-run pending",
                "plan_status": "step-1:completed,step-2:completed,step-3:in_progress",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("status\nhandoff\nmode caveman ultra\nstatus\nmode normal\nstatus\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Stagewarden status:", rendered)
            self.assertIn("mode: normal", rendered)
            self.assertIn("handoff: .stagewarden_handoff.json", rendered)
            self.assertIn("Handoff summary:", rendered)
            self.assertIn("Project handoff:", rendered)
            self.assertIn("Stage view:", rendered)
            self.assertIn("closed_stages: step-1, step-2", rendered)
            self.assertIn("active_stage: step-3 [in_progress]", rendered)
            self.assertIn("git_boundary: baseline=abc123 current=def456", rendered)
            self.assertIn("pid_boundary: project_status=executing", rendered)
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
