from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_cli.config import AgentConfig
from agent_cli.executor import Executor
from agent_cli.memory import MemoryStore
from agent_cli.router import ModelRouter


class DummyHandoff:
    def execute(self, command: str):  # noqa: ANN001
        raise AssertionError("not used")


class ParserTests(unittest.TestCase):
    def build_executor(self) -> Executor:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        return Executor(
            config=AgentConfig(workspace_root=Path(tmp_dir.name)),
            router=ModelRouter(),
            handoff=DummyHandoff(),
            memory=MemoryStore(),
        )

    def test_parser_accepts_fenced_json(self) -> None:
        executor = self.build_executor()
        result = executor._parse_model_json(
            '```json\n{"summary":"ok","action":{"type":"complete","message":"done"}}\n```'
        )
        self.assertTrue(result["ok"])

    def test_parser_extracts_json_from_wrapped_text(self) -> None:
        executor = self.build_executor()
        raw = 'Thoughts first\n{"summary":"ok","action":{"type":"complete","message":"done"}}\ntrailing note'
        result = executor._parse_model_json(raw)
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
