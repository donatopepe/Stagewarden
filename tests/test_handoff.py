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
        command = format_run_model("gpt", "hello", account="work")
        model, prompt, account = parse_run_model_command(command)
        self.assertEqual(model, "gpt")
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
                    print(json.dumps({"summary":"ok","account":os.environ.get("STAGEWARDEN_MODEL_ACCOUNT",""),"token":os.environ.get("OPENAI_API_KEY",""),"action":{"type":"complete","message":"done"}}))
                    """
                )
            )
            stub.chmod(0o755)
            original = os.environ.get("RUN_MODEL_BIN")
            original_work = os.environ.get("OPENAI_API_KEY_WORK")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            os.environ["OPENAI_API_KEY_WORK"] = "work-token"
            try:
                manager = HandoffManager(timeout_seconds=5)
                manager.account_env_by_target = {"gpt:work": "OPENAI_API_KEY_WORK"}
                result = manager.execute(format_run_model("gpt", "prompt", account="work"))
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original
                if original_work is None:
                    os.environ.pop("OPENAI_API_KEY_WORK", None)
                else:
                    os.environ["OPENAI_API_KEY_WORK"] = original_work

        self.assertTrue(result.ok)
        self.assertIn('"type": "complete"', result.output)
        self.assertIn('"account": "work"', result.output)
        self.assertIn('"token": "work-token"', result.output)


if __name__ == "__main__":
    unittest.main()
