from __future__ import annotations

import json
import os
import re
import tempfile
import textwrap
import unittest
from pathlib import Path

from stagewarden.handoff import HandoffManager, format_run_model, parse_run_model_command
from stagewarden.provider_registry import model_token_env


class HandoffTests(unittest.TestCase):
    FIXED_OPENROUTER_MODEL = "google/gemini-3.1-pro-preview"

    def _openrouter_env_name(self) -> str:
        candidate = model_token_env().get("cheap") or "OPENROUTER_API_KEY"
        if os.environ.get(candidate):
            return candidate
        if candidate != "OPENROUTER_API_KEY" and os.environ.get("OPENROUTER_API_KEY"):
            return "OPENROUTER_API_KEY"
        self.fail("OpenRouter API key is required for this test.")

    def _write_openrouter_live_runner(self, tmp_dir: str) -> Path:
        stub = Path(tmp_dir) / "run_model_openrouter_live_stub.py"
        stub.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                from __future__ import annotations

                import json
                import os
                import sys
                import urllib.request


                def main() -> int:
                    if len(sys.argv) < 3:
                        print(json.dumps({"error": "usage: stub <model> <prompt>"}))
                        return 1

                    requested_model = sys.argv[1]
                    prompt = sys.argv[2]
                    api_key = os.environ.get("OPENROUTER_API_KEY", "")
                    if not api_key:
                        print(json.dumps({"error": "missing OPENROUTER_API_KEY"}))
                        return 1

                    payload = {
                        "model": "__FIXED_OPENROUTER_MODEL__",
                        "messages": [
                            {"role": "system", "content": "Answer with only one letter: A, B, C, or D."},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 256,
                        "temperature": 0,
                    }
                    request = urllib.request.Request(
                        "https://openrouter.ai/api/v1/chat/completions",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://stagewarden.local",
                            "X-Title": "Stagewarden tests",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=60) as response:
                        data = json.load(response)

                    choices = data.get("choices") or []
                    message = choices[0].get("message") if choices else {}
                    content = str((message or {}).get("content") or (message or {}).get("reasoning") or "").strip()
                    print(json.dumps({
                        "account": os.environ.get("STAGEWARDEN_MODEL_ACCOUNT", ""),
                        "target": os.environ.get("STAGEWARDEN_MODEL_TARGET", ""),
                        "requested_model": requested_model,
                        "routed_model": data.get("model", ""),
                        "content": content,
                        "usage": data.get("usage", {}),
                        "action": {"type": "complete", "message": content or "OpenRouter call completed."},
                    }))
                    return 0


                if __name__ == "__main__":
                    raise SystemExit(main())
                """
            ).replace("__FIXED_OPENROUTER_MODEL__", self.FIXED_OPENROUTER_MODEL),
            encoding="utf-8",
        )
        stub.chmod(0o755)
        return stub

    def _mmlu_benchmark_cases(self) -> list[tuple[str, str]]:
        return [
            (
                "\n".join(
                    [
                        "What is the embryological origin of the hyoid bone?",
                        "A. The first pharyngeal arch",
                        "B. The first and second pharyngeal arches",
                        "C. The second pharyngeal arch",
                        "D. The second and third pharyngeal arches",
                        "Answer:",
                    ]
                ),
                "D",
            ),
            (
                "\n".join(
                    [
                        "Which of these branches of the trigeminal nerve contain somatic motor processes?",
                        "A. The supraorbital nerve",
                        "B. The infraorbital nerve",
                        "C. The mental nerve",
                        "D. None of the above",
                        "Answer:",
                    ]
                ),
                "D",
            ),
            (
                "\n".join(
                    [
                        "The pleura",
                        "A. have no sensory innervation.",
                        "B. are separated by a 2 mm space.",
                        "C. extend into the neck.",
                        "D. are composed of respiratory epithelium.",
                        "Answer:",
                    ]
                ),
                "C",
            ),
        ]

    def _last_choice(self, text: str) -> str:
        matches = re.findall(r"\b([ABCD])\b", text.upper())
        self.assertTrue(matches, f"No choice letter found in response: {text!r}")
        return matches[-1]

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

    def test_handoff_runs_mmlu_benchmark_suite_against_openrouter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub = self._write_openrouter_live_runner(tmp_dir)
            original = os.environ.get("RUN_MODEL_BIN")
            openrouter_env = self._openrouter_env_name()
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                manager = HandoffManager(timeout_seconds=20)
                manager.account_env_by_target = {f"cheap:live": openrouter_env}
                for prompt, expected_answer in self._mmlu_benchmark_cases():
                    with self.subTest(expected_answer=expected_answer):
                        result = manager.execute(format_run_model("cheap", prompt, account="live"))
                        self.assertTrue(result.ok)
                        payload = json.loads(result.output)
                        self.assertEqual(payload["account"], "live")
                        self.assertEqual(payload["target"], "cheap:live")
                        self.assertEqual(payload["requested_model"], "cheap")
                        self.assertTrue(payload["routed_model"])
                        self.assertTrue(payload["content"])
                        self.assertGreater(payload["usage"]["total_tokens"], 0)
                        self.assertEqual(self._last_choice(payload["content"]), expected_answer)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

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
                manager = HandoffManager(timeout_seconds=20)
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

    def test_handoff_passes_openrouter_api_key_to_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub = self._write_openrouter_live_runner(tmp_dir)
            original_bin = os.environ.get("RUN_MODEL_BIN")
            openrouter_env = self._openrouter_env_name()
            prompt, _ = self._mmlu_benchmark_cases()[0]
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                manager = HandoffManager(timeout_seconds=5)
                manager.account_env_by_target = {f"cheap:live": openrouter_env}
                result = manager.execute(format_run_model("cheap", prompt, account="live"))
            finally:
                if original_bin is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original_bin

        self.assertTrue(result.ok, result.error)
        payload = json.loads(result.output)
        self.assertEqual(payload["account"], "live")
        self.assertEqual(payload["target"], "cheap:live")
        self.assertTrue(payload["content"])
        self.assertGreaterEqual(payload["usage"]["prompt_tokens"], 1)

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
