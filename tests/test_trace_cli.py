from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_cli.agent import Agent
from agent_cli.config import AgentConfig
from agent_cli.ljson import decode, load_file


class TraceAndCliTests(unittest.TestCase):
    def test_agent_writes_ljson_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            agent.run("simple task")
            self.assertTrue((root / ".agent_cli_trace.ljson").exists())
            payload = json.loads((root / ".agent_cli_trace.ljson").read_text())
            self.assertIn("_fields", payload)
            self.assertGreaterEqual(len(decode(payload)), 1)

    def test_load_file_roundtrip_from_dumped_ljson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sample = root / "sample.ljson"
            sample.write_text(json.dumps({"_version": 1, "_fields": ["id"], "data": [[1], [2]]}))
            self.assertEqual(load_file(sample), [{"id": 1}, {"id": 2}])


if __name__ == "__main__":
    unittest.main()
