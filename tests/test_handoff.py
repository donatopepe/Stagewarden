from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from stagewarden.handoff import HandoffManager, format_run_model, parse_run_model_command


class HandoffTests(unittest.TestCase):
    def test_parse_and_format(self) -> None:
        command = format_run_model("local", "hello")
        model, prompt, account = parse_run_model_command(command)
        self.assertEqual(model, "local")
        self.assertEqual(prompt, "hello")
        self.assertIsNone(account)

    def test_parse_and_format_account_target(self) -> None:
        command = format_run_model("openai", "hello", account="work")
        model, prompt, account = parse_run_model_command(command)
        self.assertEqual(model, "openai")
        self.assertEqual(prompt, "hello")
        self.assertEqual(account, "work")

    def test_handoff_invokes_configured_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub = Path(tmp_dir) / "run_model_test_stub"
            stub.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import os
                    import sys
                    print(json.dumps({"summary":"ok","account":os.environ.get("STAGEWARDEN_MODEL_ACCOUNT",""),"token":os.environ.get("OPENAI_API_KEY","") or os.environ.get("CHATGPT_TOKEN",""),"action":{"type":"complete","message":"done"}}))
                    """
                )
            )
            stub.chmod(0o755)
            original = os.environ.get("RUN_MODEL_BIN")
            original_work = os.environ.get("OPENAI_API_KEY_WORK")
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            os.environ["OPENAI_API_KEY_WORK"] = "work-token"
            try:
                manager = HandoffManager(timeout_seconds=5)
                manager.account_env_by_target = {"openai:work": "OPENAI_API_KEY_WORK"}
                result = manager.execute(format_run_model("openai", "prompt", account="work"))
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original
                if original_work is None:
                    os.environ.pop("OPENAI_API_KEY_WORK", None)
                else:
                    os.environ["OPENAI_API_KEY_WORK"] = original_work
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

        self.assertTrue(result.ok)
        self.assertIn('"type": "complete"', result.output)
        self.assertIn('"account": "work"', result.output)
        self.assertIn('"token": "work-token"', result.output)

    def test_handoff_streams_output_through_callback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub = Path(tmp_dir) / "run_model_test_stub"
            stub.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import sys
                    sys.stdout.write('{"summary":"ok",')
                    sys.stdout.flush()
                    sys.stdout.write('"action":{"type":"complete","message":"done"}}')
                    sys.stdout.flush()
                    """
                )
            )
            stub.chmod(0o755)
            original = os.environ.get("RUN_MODEL_BIN")
            chunks: list[str] = []
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                manager = HandoffManager(timeout_seconds=5)
                manager.stream_callback = chunks.append
                result = manager.execute(format_run_model("local", "prompt"))
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

        self.assertTrue(result.ok, result.error)
        rendered = "".join(chunks)
        self.assertIn("[model-stream local]", rendered)
        self.assertIn('"summary":"ok"', rendered)
        self.assertIn('"message":"done"', rendered)

    def test_handoff_passes_chatgpt_token_to_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub = Path(tmp_dir) / "run_model_test_stub"
            store = Path(tmp_dir) / "secrets"
            stub.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import os
                    print(json.dumps({"account": os.environ.get("STAGEWARDEN_MODEL_ACCOUNT", ""), "token": os.environ.get("CHATGPT_TOKEN", "")}))
                    """
                )
            )
            stub.chmod(0o755)
            original_bin = os.environ.get("RUN_MODEL_BIN")
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                from stagewarden.secrets import SecretStore

                saved = SecretStore().save_token("chatgpt", "personal", "chatgpt-session-token")
                self.assertTrue(saved.ok, saved.message)
                result = HandoffManager(timeout_seconds=5).execute(format_run_model("chatgpt", "prompt", account="personal"))
            finally:
                if original_bin is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original_bin
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

        self.assertTrue(result.ok, result.error)
        self.assertIn('"account": "personal"', result.output)
        self.assertIn('"token": "chatgpt-session-token"', result.output)

    def test_handoff_loads_saved_account_token_when_env_mapping_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub = Path(tmp_dir) / "run_model_test_stub"
            store = Path(tmp_dir) / "secrets"
            stub.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import os
                    print(json.dumps({"token": os.environ.get("OPENAI_API_KEY", "")}))
                    """
                )
            )
            stub.chmod(0o755)
            original_bin = os.environ.get("RUN_MODEL_BIN")
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                from stagewarden.secrets import SecretStore

                saved = SecretStore().save_token("openai", "work", "saved-token")
                self.assertTrue(saved.ok, saved.message)
                result = HandoffManager(timeout_seconds=5).execute(format_run_model("openai", "prompt", account="work"))
            finally:
                if original_bin is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original_bin
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

        self.assertTrue(result.ok, result.error)
        self.assertIn('"token": "saved-token"', result.output)

    def test_handoff_exposes_json_auth_payload_for_openai_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub = Path(tmp_dir) / "run_model_test_stub"
            store = Path(tmp_dir) / "secrets"
            stub.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import os
                    print(json.dumps({
                        "token": os.environ.get("OPENAI_API_KEY", ""),
                        "payload": os.environ.get("STAGEWARDEN_AUTH_TOKENS_JSON", ""),
                    }))
                    """
                )
            )
            stub.chmod(0o755)
            original_bin = os.environ.get("RUN_MODEL_BIN")
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                from stagewarden.secrets import SecretStore

                payload = '{"access_token":"access-token-123","refresh_token":"refresh-token-123"}'
                saved = SecretStore().save_token("openai", "work", payload)
                self.assertTrue(saved.ok, saved.message)
                result = HandoffManager(timeout_seconds=5).execute(format_run_model("openai", "prompt", account="work"))
            finally:
                if original_bin is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original_bin
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

        self.assertTrue(result.ok, result.error)
        self.assertIn('"token": "access-token-123"', result.output)
        self.assertIn('\\"refresh_token\\":\\"refresh-token-123\\"', result.output)

    def test_handoff_maps_claude_auth_token_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub = Path(tmp_dir) / "run_model_test_stub"
            stub.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import os
                    print(json.dumps({
                        "api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
                        "auth_token": os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
                    }))
                    """
                )
            )
            stub.chmod(0o755)
            original_bin = os.environ.get("RUN_MODEL_BIN")
            original_token = os.environ.get("CLAUDE_AUTH_TOKEN_WORK")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            os.environ["CLAUDE_AUTH_TOKEN_WORK"] = "claude-auth-token"
            try:
                manager = HandoffManager(timeout_seconds=5)
                manager.account_env_by_target = {"claude:work": "CLAUDE_AUTH_TOKEN_WORK"}
                result = manager.execute(format_run_model("claude", "prompt", account="work"))
            finally:
                if original_bin is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original_bin
                if original_token is None:
                    os.environ.pop("CLAUDE_AUTH_TOKEN_WORK", None)
                else:
                    os.environ["CLAUDE_AUTH_TOKEN_WORK"] = original_token

        self.assertTrue(result.ok, result.error)
        self.assertIn('"auth_token": "claude-auth-token"', result.output)
        self.assertIn('"api_key": ""', result.output)

    def test_handoff_passes_provider_model_variant_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub = Path(tmp_dir) / "run_model_test_stub"
            stub.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import os
                    print(json.dumps({
                        "variant": os.environ.get("STAGEWARDEN_MODEL_VARIANT", ""),
                        "openai_model": os.environ.get("OPENAI_MODEL", ""),
                    }))
                    """
                )
            )
            stub.chmod(0o755)
            original_bin = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                manager = HandoffManager(timeout_seconds=5)
                manager.model_variant_by_model = {"openai": "gpt-5.4-mini"}
                result = manager.execute(format_run_model("openai", "prompt"))
            finally:
                if original_bin is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original_bin

        self.assertTrue(result.ok, result.error)
        self.assertIn('"variant": "gpt-5.4-mini"', result.output)
        self.assertIn('"openai_model": "gpt-5.4-mini"', result.output)

    def test_handoff_loads_claude_json_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub = Path(tmp_dir) / "run_model_test_stub"
            store = Path(tmp_dir) / "secrets"
            stub.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import os
                    print(json.dumps({
                        "api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
                        "auth_token": os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
                        "payload": os.environ.get("STAGEWARDEN_AUTH_TOKENS_JSON", ""),
                    }))
                    """
                )
            )
            stub.chmod(0o755)
            original_bin = os.environ.get("RUN_MODEL_BIN")
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                from stagewarden.secrets import SecretStore

                payload = '{"auth_token":"claude-subscription-token","api_key":"console-key"}'
                saved = SecretStore().save_token("claude", "work", payload)
                self.assertTrue(saved.ok, saved.message)
                result = HandoffManager(timeout_seconds=5).execute(format_run_model("claude", "prompt", account="work"))
            finally:
                if original_bin is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original_bin
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

        self.assertTrue(result.ok, result.error)
        self.assertIn('"auth_token": "claude-subscription-token"', result.output)
        self.assertIn('"api_key": "console-key"', result.output)


if __name__ == "__main__":
    unittest.main()
