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
from stagewarden.memory import MemoryStore
from stagewarden.modelprefs import ModelPreferences
from stagewarden.main import _render_boundary, _render_handoff, run_interactive_shell


ROOT = Path(__file__).resolve().parents[1]


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
                '    match = re.search(r\"file named ([A-Za-z0-9._/\\\\-]+)\", text, re.IGNORECASE)',
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
                "    if instruction.startswith('analyze') or instruction.startswith('inspect'):",
                "        action = {'type': 'complete', 'message': 'analysis validated exit_code=0'}",
                "    elif 'implement' in instruction or 'create' in instruction or 'build' in instruction or 'continue from persisted handoff context' in instruction:",
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


def run_main_capture(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        ["python3", "-m", "stagewarden.main", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


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
            self.assertIn("Use `help <topic>`", rendered)
            self.assertIn("Topics:", rendered)
            self.assertIn("help models", rendered)
            self.assertIn("help accounts", rendered)
            self.assertIn("help permissions", rendered)
            self.assertIn("Fast examples:", rendered)
            self.assertIn("Model configuration:", rendered)
            self.assertIn("Session closed.", rendered)

    def test_doctor_cli_reports_prerequisites_without_initializing_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "doctor")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Stagewarden doctor:", completed.stdout)
            self.assertIn("- Python: OK", completed.stdout)
            self.assertIn("- Git: OK", completed.stdout)
            self.assertIn("- PATH launcher:", completed.stdout)
            self.assertIn("Provider capabilities:", completed.stdout)
            self.assertIn("- chatgpt: auth=chatgpt_plan_oauth", completed.stdout)
            self.assertIn("- openai: auth=openai_api_key", completed.stdout)
            self.assertIn("- claude: auth=anthropic_api_key_or_claude_code_credentials", completed.stdout)
            self.assertIn("no prerequisites are installed silently", completed.stdout)
            self.assertFalse((root / ".git").exists())

    def test_doctor_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "doctor", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "doctor")
            self.assertEqual(payload["python"]["status"], "OK")
            self.assertTrue(payload["git"]["ok"])
            self.assertIn("silent_install", payload["policy"])
            self.assertFalse(payload["policy"]["silent_install"])
            providers = {entry["provider"]: entry for entry in payload["providers"]}
            self.assertIn("chatgpt", providers)
            self.assertEqual(providers["chatgpt"]["auth"], "chatgpt_plan_oauth")
            self.assertIn("default_model", providers["openai"])
            self.assertFalse((root / ".git").exists())

    def test_models_usage_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="step-1",
                model="local",
                action_type="complete",
                action_signature="a",
                success=True,
                observation="ok",
            )
            memory.record_attempt(
                iteration=2,
                step_id="step-2",
                model="cheap",
                action_type="complete",
                action_signature="b",
                success=False,
                observation="quota",
                error_type="api_failure",
            )
            memory.save(root / ".stagewarden_memory.json")
            completed = run_main_capture(root, "models usage", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "models usage")
            self.assertEqual(payload["report"]["totals"]["calls"], 2)
            self.assertEqual(payload["report"]["totals"]["failures"], 1)
            self.assertEqual(payload["report"]["totals"]["escalation_path"], "local -> cheap")
            self.assertIn("routing_budget", payload["policy"])

    def test_interactive_shell_doctor_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=1)
            input_stream = StringIO("doctor\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Stagewarden doctor:", rendered)
            self.assertIn("- Python: OK", rendered)
            self.assertIn("- Git: OK", rendered)
            self.assertIn("Provider capabilities:", rendered)

    def test_interactive_shell_supports_category_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=1)
            input_stream = StringIO(
                "help models\n"
                "help accounts\n"
                "help permissions\n"
                "help handoff\n"
                "help git\n"
                "help ljson\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Model commands", rendered)
            self.assertIn("model variant <provider> <variant>", rendered)
            self.assertIn("Account commands", rendered)
            self.assertIn("account login-device <chatgpt|openai> <name>", rendered)
            self.assertIn("Permission commands", rendered)
            self.assertIn("permission session allow <rule>", rendered)
            self.assertIn("Handoff and PRINCE2 commands", rendered)
            self.assertIn("handoff export | handoff md", rendered)
            self.assertIn("Git commands", rendered)
            self.assertIn("git history <path> [limit]", rendered)
            self.assertIn("LJSON commands", rendered)
            self.assertIn("--ljson-benchmark", rendered)

    def test_interactive_shell_executes_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = "/Users/donato/Stagewarden/run_model_stub"
            try:
                config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=6)
                input_stream = StringIO("create a file named hello.txt\ntranscript\nquit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp_dir) / "hello.txt").exists())
            rendered = output_stream.getvalue()
            self.assertIn("Tool transcript:", rendered)
            self.assertIn("tool=files", rendered)
            self.assertIn("action=write_file", rendered)

    def test_interactive_shell_permission_ask_can_be_approved_for_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = "/Users/donato/Stagewarden/run_model_stub"
            try:
                config = AgentConfig(workspace_root=root, max_steps=6)
                input_stream = StringIO(
                    "permission ask file:hello.txt\n"
                    "create a file named hello.txt\n"
                    "session\n"
                    "permissions\n"
                    "quit\n"
                )
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertTrue((root / "hello.txt").exists())
            self.assertIn("Permission approval required:", rendered)
            self.assertIn("Permission approved for this session: file:hello.txt", rendered)
            self.assertIn("session allow: file:hello.txt", rendered)
            payload = json.loads((root / ".stagewarden_settings.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["permissions"]["ask"], ["file:hello.txt"])
            self.assertEqual(payload["permissions"]["allow"], [])

    def test_interactive_shell_permission_ask_can_be_persisted_as_always_allow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = "/Users/donato/Stagewarden/run_model_stub"
            try:
                config = AgentConfig(workspace_root=root, max_steps=6)
                input_stream = StringIO(
                    "permission ask file:hello.txt\n"
                    "create a file named hello.txt\n"
                    "always\n"
                    "permissions\n"
                    "quit\n"
                )
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertTrue((root / "hello.txt").exists())
            self.assertIn("Permission persisted as allow rule: file:hello.txt", rendered)
            self.assertIn("workspace allow: file:hello.txt", rendered)
            payload = json.loads((root / ".stagewarden_settings.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["permissions"]["allow"], ["file:hello.txt"])
            self.assertEqual(payload["permissions"]["ask"], [])

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
            self.assertIn("Auth: anthropic_api_key_or_claude_code_credentials", rendered)
            self.assertIn("Browser login: no", rendered)
            self.assertIn("Login hint: Use ANTHROPIC_API_KEY", rendered)
            self.assertIn("opusplan", rendered)
            self.assertIn("variant=opus", rendered)

    def test_interactive_shell_model_list_uses_provider_registry_for_login_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("model list chatgpt\nmodel list openai\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Auth: chatgpt_plan_oauth", rendered)
            self.assertIn("API key: no", rendered)
            self.assertIn("Use account login chatgpt <profile>", rendered)
            self.assertIn("Auth: openai_api_key", rendered)
            self.assertIn("API key: yes", rendered)
            self.assertIn("Prefer OPENAI_API_KEY", rendered)

    def test_interactive_shell_manages_persistent_shell_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "sessions\n"
                "session create\n"
                "session list\n"
                "session send last pwd\n"
                "session close last\n"
                "session list\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("No active shell sessions.", rendered)
            self.assertIn("shell_session_created id=", rendered)
            self.assertIn("state=running", rendered)
            self.assertIn("session_id=", rendered)
            self.assertIn("exit_code=0", rendered)
            self.assertIn(str(root), rendered)
            self.assertIn("shell_session_closed id=", rendered)

    def test_interactive_shell_enforces_permission_inside_shell_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "permission session mode plan\n"
                "session create\n"
                "session send last python3 -c \"open('out.txt','w').write('x')\"\n"
                "session close last\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Session permission mode set to plan.", rendered)
            self.assertIn("Plan mode allows analysis only.", rendered)
            self.assertFalse((root / "out.txt").exists())

    def test_interactive_shell_previews_patch_file_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "target.txt").write_text("before\n", encoding="utf-8")
            (root / "changes.diff").write_text(
                "\n".join(
                    [
                        "--- a/target.txt",
                        "+++ b/target.txt",
                        "@@ -1,1 +1,1 @@",
                        "-before",
                        "+after",
                    ]
                ),
                encoding="utf-8",
            )
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("permission session mode plan\npatch preview changes.diff\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Patch preview:", rendered)
            self.assertIn("update target.txt", rendered)
            self.assertEqual((root / "target.txt").read_text(encoding="utf-8"), "before\n")

    def test_interactive_shell_renders_model_usage_and_cost_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="step-1",
                model="local",
                action_type="read_file",
                action_signature='{"type":"read_file"}',
                success=True,
                observation="ok",
            )
            memory.record_attempt(
                iteration=2,
                step_id="step-2",
                model="claude",
                action_type="complete",
                action_signature='{"type":"complete"}',
                success=False,
                observation="failed",
                error_type="api_failure",
            )
            memory.save(config.memory_path)
            input_stream = StringIO("models usage\ncost\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("local: calls=1 failures=0", rendered)
            self.assertIn("claude: calls=1 failures=1", rendered)
            self.assertIn("totals: calls=2 failures=1 steps=2 failure_rate=50.00%", rendered)
            self.assertIn("routing: last_model=claude highest_tier=high/fallback highest_model=claude escalation_path=local -> claude", rendered)
            self.assertGreaterEqual(rendered.count("Model usage:"), 2)

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
            self.assertIn("Use ANTHROPIC_API_KEY", rendered)

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

    def test_interactive_shell_caveman_help_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=1)
            input_stream = StringIO("help caveman\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Caveman commands:", rendered)
            self.assertIn("/caveman [lite|full|ultra|wenyan-lite|wenyan|wenyan-ultra]", rendered)
            self.assertIn("$caveman ...", rendered)
            self.assertIn("@caveman ...", rendered)
            self.assertIn("/caveman help", rendered)
            self.assertIn("/caveman commit", rendered)
            self.assertIn("/caveman review", rendered)
            self.assertIn("/caveman compress <file>", rendered)
            self.assertIn("stop caveman", rendered)
            self.assertIn("talk like caveman", rendered)

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
                "risk_register": [{"risk": "Regression from patch execution", "status": "open"}],
                "issue_register": [{"step_id": "step-3", "severity": "medium", "summary": "validation pending"}],
                "quality_register": [{"step_id": "step-2", "status": "passed", "evidence": "file updated"}],
                "lessons_log": [{"step_id": "step-2", "type": "success", "lesson": "file update pattern is reusable"}],
                "exception_plan": ["review boundary for step-3", "prepare corrective action"],
                "implementation_backlog": [
                    {"step_id": "step-1", "title": "Inspect tests", "status": "completed", "validation": "Real command output captured."},
                    {"step_id": "step-2", "title": "Patch implementation", "status": "completed", "validation": "Files changed and verified."},
                    {"step_id": "step-3", "title": "Validate result", "status": "in_progress", "validation": "Wet-run tests pass."},
                ],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "status\nhandoff\ntodo\nboundary\nrisks\nissues\nquality\nexception\nlessons\n"
                "mode caveman ultra\nstatus\nmode normal\nstatus\nexit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Stagewarden status:", rendered)
            self.assertIn("mode: normal", rendered)
            self.assertIn("Permission settings:", rendered)
            self.assertIn("workspace mode: default", rendered)
            self.assertIn("effective mode: default", rendered)
            self.assertIn("handoff: .stagewarden_handoff.json", rendered)
            self.assertIn("Handoff summary:", rendered)
            self.assertIn("Operational posture:", rendered)
            self.assertIn("governance=residual", rendered)
            self.assertIn("stage_health: at_risk", rendered)
            self.assertIn("recovery_state: none", rendered)
            self.assertIn("next_action: continue step-3", rendered)
            self.assertIn("active_stage: step-3 [in_progress]", rendered)
            self.assertIn("implementation_backlog_open: 1", rendered)
            self.assertIn("implementation_backlog_blocked: 0", rendered)
            self.assertIn("git_boundary: baseline=abc123 current=def456", rendered)
            self.assertIn("boundary_decision: continue_current_stage", rendered)
            self.assertIn("Project handoff:", rendered)
            self.assertIn("Stage view:", rendered)
            self.assertIn("Implementation backlog:", rendered)
            self.assertIn("closed_stages: step-1, step-2", rendered)
            self.assertIn("active_stage: step-3 [in_progress]", rendered)
            self.assertIn("git_boundary: baseline=abc123 current=def456", rendered)
            self.assertIn("pid_boundary: project_status=executing", rendered)
            self.assertIn("stage_health: at_risk", rendered)
            self.assertIn("recovery_state: none", rendered)
            self.assertIn("boundary_decision: continue_current_stage", rendered)
            self.assertIn("next_action: continue step-3", rendered)
            self.assertIn("registers: risks=1 issues=1 quality=1 lessons=1 backlog=3", rendered)
            self.assertIn("register_status: risks_open=1 risks_closed=0 issues_open=1 issues_closed=0 quality_open=1 quality_accepted=0", rendered)
            self.assertIn("backlog_status: ready=0 planned=0 in_progress=1 blocked=0 done=2", rendered)
            self.assertIn("[done] step-1 :: Inspect tests | validation=Real command output captured.", rendered)
            self.assertIn("[done] step-2 :: Patch implementation | validation=Files changed and verified.", rendered)
            self.assertIn("[in_progress] step-3 :: Validate result | validation=Wet-run tests pass.", rendered)
            self.assertIn("Boundary recommendation:", rendered)
            self.assertIn("Risk register:", rendered)
            self.assertIn("Issue register:", rendered)
            self.assertIn("Quality register:", rendered)
            self.assertIn("Exception plan:", rendered)
            self.assertIn("Lessons log:", rendered)
            self.assertIn("Regression from patch execution", rendered)
            self.assertIn("validation pending", rendered)
            self.assertIn("file updated", rendered)
            self.assertIn("review boundary for step-3", rendered)
            self.assertIn("file update pattern is reusable", rendered)
            self.assertIn("Caveman mode active. Level: ultra.", rendered)
            self.assertIn("mode: caveman ultra", rendered)
            self.assertIn("Caveman mode disabled.", rendered)
            self.assertFalse((root / ".stagewarden_caveman.json").exists())

    def test_interactive_shell_resume_show_uses_current_handoff_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-7",
                "current_step_title": "Validate",
                "current_step_status": "in_progress",
                "latest_observation": "wet-run pending",
                "plan_status": "step-7:in_progress",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("resume --show\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Resume target:", rendered)
            self.assertIn("- task: fix failing tests", rendered)
            self.assertIn("- current_step: step-7", rendered)
            self.assertIn("active_stage: step-7 [in_progress]", rendered)

    def test_interactive_shell_resume_clear_archives_handoff_without_git_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-7",
                "current_step_status": "in_progress",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("resume --clear\nhandoff\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            archives = list(root.glob(".stagewarden_handoff.archive.*.json"))

            self.assertEqual(code, 0)
            self.assertEqual(len(archives), 1)
            self.assertIn("Archived handoff", rendered)
            self.assertIn("No active handoff context.", rendered)
            archived = json.loads(archives[0].read_text(encoding="utf-8"))
            self.assertEqual(archived.get("current_step_id"), "step-7")

    def test_interactive_shell_resume_executes_wet_run_from_persisted_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            stub = write_success_stub(root)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "create a file named resumed.txt",
                "status": "executing",
                "current_step_id": "step-2",
                "current_step_title": "2. Implement create a file named resumed.txt",
                "current_step_status": "in_progress",
                "latest_observation": "inspection completed, implementation pending",
                "plan_status": "step-1:completed,step-2:in_progress,step-3:planned",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                config = AgentConfig(workspace_root=root, max_steps=10)
                input_stream = StringIO("resume\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            rendered = output_stream.getvalue()
            updated = json.loads((root / ".stagewarden_handoff.json").read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertTrue((root / "resumed.txt").exists())
            self.assertIn("Resumed from handoff step step-2.", rendered)
            self.assertIn("Agent run completed.", rendered)
            self.assertIn("Cost and budget:", rendered)
            self.assertEqual(updated.get("status"), "closed")

    def test_interactive_shell_exports_runtime_handoff_markdown_with_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "HANDOFF.md").write_text("# Stagewarden Handoff\n\nManual roadmap stays.\n", encoding="utf-8")
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-2",
                "current_step_title": "2. Implement fix",
                "current_step_status": "in_progress",
                "latest_observation": "access_token=secret-token-123 should not leak",
                "plan_status": "step-1:completed,step-2:in_progress,step-3:planned",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "implementation_backlog": [
                    {"step_id": "step-1", "title": "Inspect", "status": "done", "validation": "checked"},
                    {"step_id": "step-2", "title": "Implement", "status": "in_progress", "validation": "wet-run"},
                ],
                "issue_register": [{"step_id": "step-2", "severity": "medium", "summary": "Bearer abcdefghijklmnopqrstuvwxyz123456 should be redacted", "status": "open"}],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("handoff export\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Exported runtime handoff to HANDOFF.md.", rendered)
            exported = (root / "HANDOFF.md").read_text(encoding="utf-8")
            self.assertIn("Manual roadmap stays.", exported)
            self.assertIn("<!-- STAGEWARDEN_RUNTIME_HANDOFF_START -->", exported)
            self.assertIn("## Runtime Handoff Export", exported)
            self.assertIn("- task: fix failing tests", exported)
            self.assertIn("- recovery_state: none", exported)
            self.assertIn("Implementation backlog:", exported)
            self.assertNotIn("secret-token-123", exported)
            self.assertNotIn("abcdefghijklmnopqrstuvwxyz123456", exported)
            self.assertIn("Bearer [REDACTED]", exported)

    def test_interactive_shell_manages_permission_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "permission mode plan\n"
                "permission allow shell:git status\n"
                "permission ask file:secret.txt\n"
                "permission deny shell:rm\n"
                "permissions\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Permission mode set to plan.", rendered)
            self.assertIn("Added allow rule: shell:git status", rendered)
            self.assertIn("Added ask rule: file:secret.txt", rendered)
            self.assertIn("Added deny rule: shell:rm", rendered)
            self.assertIn("workspace mode: plan", rendered)
            self.assertIn("workspace allow: shell:git status", rendered)
            self.assertIn("workspace ask: file:secret.txt", rendered)
            self.assertIn("workspace deny: shell:rm", rendered)
            self.assertIn("effective mode: plan", rendered)
            payload = json.loads((root / ".stagewarden_settings.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["permissions"]["defaultMode"], "plan")

    def test_interactive_shell_mode_aliases_manage_permission_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "mode plan\n"
                "status\n"
                "mode auto\n"
                "mode accept-edits\n"
                "mode dont-ask\n"
                "mode default\n"
                "permissions\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Permission mode set to plan.", rendered)
            self.assertIn("Permission mode set to auto.", rendered)
            self.assertIn("Permission mode set to accept_edits.", rendered)
            self.assertIn("Permission mode set to dont_ask.", rendered)
            self.assertIn("Permission mode set to default.", rendered)
            self.assertIn("effective mode: plan", rendered)
            self.assertIn("Permission settings:", rendered)
            self.assertIn("workspace mode: default", rendered)
            self.assertIn("effective mode: default", rendered)
            payload = json.loads((root / ".stagewarden_settings.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["permissions"]["defaultMode"], "default")

    def test_interactive_shell_manages_session_permission_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "permission session mode plan\n"
                "permission session allow shell:git status\n"
                "permissions\n"
                "permission session reset\n"
                "permissions\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Session permission mode set to plan.", rendered)
            self.assertIn("Added session allow rule: shell:git status", rendered)
            self.assertIn("session mode: plan", rendered)
            self.assertIn("session allow: shell:git status", rendered)
            self.assertIn("effective mode: plan", rendered)
            self.assertIn("Session permission settings reset.", rendered)
            self.assertIn("session mode: none", rendered)
            self.assertIn("effective mode: default", rendered)
            self.assertFalse((root / ".stagewarden_settings.json").exists())

    def test_boundary_uses_exception_plan_when_project_is_in_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "exception",
                "current_step_id": "step-2",
                "current_step_title": "Resume 2. Implement fix",
                "current_step_status": "exception",
                "latest_observation": "tests still failing after patch",
                "plan_status": "step-1:completed,step-2:exception,step-3:pending",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "issue_register": [{"step_id": "step-2", "severity": "high", "summary": "tests still failing", "status": "open"}],
                "exception_plan": ["review failing tests", "prepare corrective patch"],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            rendered = _render_boundary(config)
            self.assertIn("stage_health: exception", rendered)
            self.assertIn("recovery_state: exception_active", rendered)
            self.assertIn("next_action: execute exception plan and re-baseline the current stage", rendered)
            self.assertIn("review_boundary:exception_plan", rendered)

    def test_handoff_marks_backlog_as_blocked_when_high_severity_issue_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-2",
                "current_step_title": "Resume 2. Implement fix",
                "current_step_status": "failed",
                "latest_observation": "test environment still blocked",
                "plan_status": "step-1:completed,step-2:failed,step-3:pending",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "issue_register": [{"step_id": "step-2", "severity": "high", "summary": "critical blocker remains", "status": "open"}],
                "implementation_backlog": [
                    {"step_id": "step-1", "title": "Inspect tests", "status": "done", "validation": "Real command output captured."},
                    {"step_id": "step-2", "title": "Patch implementation", "status": "blocked", "validation": "Blocking issue resolved and wet-run passes."},
                    {"step_id": "step-3", "title": "Validate result", "status": "planned", "validation": "Wet-run tests pass."},
                ],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            rendered = _render_handoff(config)
            self.assertIn("stage_health: exception", rendered)
            self.assertIn("recovery_state: exception_active", rendered)
            self.assertIn("next_action: execute exception plan and re-baseline the current stage", rendered)
            self.assertIn("implementation_backlog_blocked: 1", rendered)
            self.assertIn("backlog_status: ready=0 planned=1 in_progress=0 blocked=1 done=1", rendered)
            self.assertIn("[blocked] step-2 :: Patch implementation | validation=Blocking issue resolved and wet-run passes.", rendered)

    def test_boundary_marks_recovery_lane_as_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "exception",
                "current_step_id": "recovery-step-1",
                "current_step_title": "Recovery 1. Review failing tests",
                "current_step_status": "in_progress",
                "latest_observation": "reviewing corrective action",
                "plan_status": "step-1:completed,step-2:failed,recovery-step-1:in_progress,recovery-step-2:planned,step-3:planned",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "exception_plan": ["review failing tests", "prepare corrective patch"],
                "implementation_backlog": [
                    {"step_id": "step-1", "title": "Inspect tests", "status": "done", "validation": "Real command output captured."},
                    {"step_id": "step-2", "title": "Patch implementation", "status": "blocked", "validation": "Blocking issue resolved."},
                    {"step_id": "recovery-step-1", "title": "Recovery 1", "status": "in_progress", "validation": "Wet-run confirms recovery."},
                    {"step_id": "recovery-step-2", "title": "Recovery 2", "status": "planned", "validation": "Wet-run confirms recovery."},
                    {"step_id": "step-3", "title": "Validate result", "status": "planned", "validation": "Wet-run tests pass."},
                ],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            rendered = _render_boundary(config)
            self.assertIn("recovery_state: recovery_active", rendered)
            self.assertIn("next_action: execute recovery lane and confirm wet-run before re-baseline", rendered)

    def test_boundary_marks_recovery_lane_as_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "recovery-step-2",
                "current_step_title": "Recovery 2. Prepare corrective patch",
                "current_step_status": "completed",
                "latest_observation": "recovery wet-run completed",
                "plan_status": "step-1:completed,step-2:failed,recovery-step-1:completed,recovery-step-2:completed,step-3:ready",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "implementation_backlog": [
                    {"step_id": "step-1", "title": "Inspect tests", "status": "done", "validation": "Real command output captured."},
                    {"step_id": "step-2", "title": "Patch implementation", "status": "blocked", "validation": "Blocking issue resolved."},
                    {"step_id": "recovery-step-1", "title": "Recovery 1", "status": "done", "validation": "Wet-run confirms recovery."},
                    {"step_id": "recovery-step-2", "title": "Recovery 2", "status": "done", "validation": "Wet-run confirms recovery."},
                    {"step_id": "step-3", "title": "Validate result", "status": "ready", "validation": "Wet-run tests pass."},
                ],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            rendered = _render_boundary(config)
            self.assertIn("recovery_state: recovery_cleared", rendered)
            self.assertIn("next_action: clear exception controls and resume planned stages", rendered)

    def test_boundary_blocks_project_close_when_open_issues_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "closed",
                "current_step_id": "step-3",
                "current_step_title": "3. Validate",
                "current_step_status": "completed",
                "latest_observation": "tests passed but one release issue remains open",
                "plan_status": "step-1:completed,step-2:completed,step-3:completed",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "issue_register": [{"step_id": "step-3", "severity": "medium", "summary": "release note missing", "status": "open"}],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            rendered = _render_boundary(config)
            self.assertIn("review_boundary:open_issues", rendered)
            self.assertIn("issues_open=1 issues_closed=0", rendered)

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
