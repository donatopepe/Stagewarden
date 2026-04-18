from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from agent_cli.handoff import HandoffManager, format_run_model, parse_run_model_command


class HandoffTests(unittest.TestCase):
    def test_parse_and_format(self) -> None:
        command = format_run_model("local", "hello")
        model, prompt = parse_run_model_command(command)
        self.assertEqual(model, "local")
        self.assertEqual(prompt, "hello")

    def test_handoff_invokes_configured_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub = Path(tmp_dir) / "run_model_test_stub"
            stub.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import sys
                    print(json.dumps({"summary":"ok","action":{"type":"complete","message":"done"}}))
                    """
                )
            )
            stub.chmod(0o755)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                manager = HandoffManager(timeout_seconds=5)
                result = manager.execute(format_run_model("local", "prompt"))
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

        self.assertTrue(result.ok)
        self.assertIn('"type": "complete"', result.output)


if __name__ == "__main__":
    unittest.main()
