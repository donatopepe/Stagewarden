from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig
from stagewarden.prince2 import Prince2AgentPolicy


class Prince2Tests(unittest.TestCase):
    def test_policy_builds_checklist(self) -> None:
        checklist = Prince2AgentPolicy().build_checklist("implement auth fix in production")
        self.assertTrue(checklist.stage_plan)
        self.assertTrue(checklist.quality_criteria)
        self.assertIn("risk", checklist.tolerances)
        self.assertTrue(any("Irreversible" in item for item in checklist.risks))

    def test_policy_rejects_vague_task(self) -> None:
        policy = Prince2AgentPolicy()
        checklist = policy.build_checklist("stuff")
        assessment = policy.assess_task("stuff", checklist)
        self.assertFalse(assessment.allowed)
        self.assertTrue(assessment.reasons)

    def test_agent_trace_contains_prince2_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            agent.run("simple task")
            payload = json.loads((root / ".stagewarden_trace.ljson").read_text(encoding="utf-8"))
            fields = payload["_fields"]
            self.assertIn("prince2_checklist", fields)

    def test_agent_rejects_task_without_prince2_basis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            result = agent.run("stuff")
            self.assertFalse(result.ok)
            self.assertIn("PRINCE2 governance gate", result.message)


if __name__ == "__main__":
    unittest.main()
