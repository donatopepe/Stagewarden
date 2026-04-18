from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig


class AgentIntegrationTests(unittest.TestCase):
    def test_agent_completes_task_with_stub_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = "/Users/donato/run_model_stub"
            try:
                agent = Agent(
                    AgentConfig(
                        workspace_root=Path(tmp_dir),
                        max_steps=6,
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


if __name__ == "__main__":
    unittest.main()
