from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stagewarden.config import AgentConfig
from stagewarden.event_stream import EventStream
from stagewarden.executor import Executor
from stagewarden.handoff import HandoffManager
from stagewarden.memory import MemoryStore
from stagewarden.project_handoff import ProjectHandoff
from stagewarden.rag import DesignRag
from stagewarden.router import ModelRouter


class ExecutorEventStreamTests(unittest.TestCase):
    def test_file_chunk_and_compaction_events_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("x" * 1000, encoding="utf-8")
            config = AgentConfig(
                workspace_root=root,
                context_window_tokens=100,
                context_reserved_output_tokens=20,
                context_safety_margin_tokens=10,
                file_chunk_chars=500,
            )
            executor = Executor(
                config=config,
                router=ModelRouter(),
                handoff=HandoffManager(),
                memory=MemoryStore(),
                project_handoff=ProjectHandoff(),
                rag=DesignRag(),
            )
            executor._active_context_budget = executor._context_budget("cheap")
            executor._active_prompt_chars = 390
            result = executor._run_action(
                {"type": "read_file_chunk", "path": "source.txt", "start": 0, "size": 500},
                step_id="node.read",
            )
            self.assertTrue(result["ok"])
            events = EventStream(config.event_path).read()
            kinds = {event["event"] for event in events}
            self.assertIn("file_chunk", kinds)
            self.assertIn("context_compaction", kinds)
            self.assertTrue(all("secret-value" not in json.dumps(event) for event in events))


if __name__ == "__main__":
    unittest.main()
