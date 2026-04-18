from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig
from stagewarden.memory import MemoryStore


class PersistenceTests(unittest.TestCase):
    def test_memory_store_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "memory.json"
            store = MemoryStore()
            store.record_attempt(
                iteration=1,
                step_id="step-1",
                model="local",
                action_type="complete",
                action_signature='{"type":"complete"}',
                success=True,
                observation="done",
            )
            store.save(path)
            loaded = MemoryStore.load(path)
            self.assertEqual(len(loaded.attempts), 1)
            self.assertEqual(loaded.attempts[0].step_id, "step-1")

    def test_agent_loads_existing_memory_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            memory_path = workspace / ".stagewarden_memory.json"
            payload = {
                "attempts": [
                    {
                        "iteration": 1,
                        "step_id": "step-1",
                        "model": "local",
                        "action_type": "shell",
                        "action_signature": '{"type":"shell","command":"pwd"}',
                        "success": False,
                        "observation": "failed",
                        "error_type": "runtime_error",
                    }
                ],
                "failures_by_step": {"step-1": 1},
                "models_by_step": {"step-1": ["local"]},
            }
            memory_path.write_text(json.dumps(payload))
            agent = Agent(AgentConfig(workspace_root=workspace))
            self.assertEqual(agent.memory.failure_count("step-1"), 1)


if __name__ == "__main__":
    unittest.main()
