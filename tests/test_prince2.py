from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig
from stagewarden.prince2_benchmark import run_prince2_benchmark
from stagewarden.prince2 import Prince2AgentPolicy


class Prince2Tests(unittest.TestCase):
    def test_policy_builds_checklist(self) -> None:
        checklist = Prince2AgentPolicy().build_checklist("implement auth fix in production")
        self.assertTrue(checklist.stage_plan)
        self.assertTrue(checklist.quality_criteria)
        self.assertIn("risk", checklist.tolerances)
        self.assertIn("Adapt governance", checklist.adaptation_policy)
        self.assertIn("responsibility explicit", checklist.role_policy)
        self.assertTrue(any("Irreversible" in item for item in checklist.risks))
        self.assertIn("tolerance_profile", checklist.as_dict())
        self.assertEqual(checklist.tolerance_profile["accountable_owner"], "user")
        self.assertEqual(len(checklist.tolerance_profile["theme_scores"]), 7)
        self.assertEqual(checklist.tolerance_profile["base_margin_percent"], 25.0)

    def test_policy_requires_adaptive_governance_not_overengineering(self) -> None:
        checklist = Prince2AgentPolicy().build_checklist("change a lamp")
        rendered = checklist.render_for_prompt()
        self.assertIn("If the method feels heavier than the task", rendered)
        self.assertTrue(any("no overengineering" in item.lower() for item in checklist.stage_plan))
        self.assertTrue(any("proportionate" in item.lower() for item in checklist.quality_criteria))

    def test_policy_escalates_when_tolerance_pressure_exceeds_margin(self) -> None:
        policy = Prince2AgentPolicy()
        checklist = policy.build_checklist("implement feature")
        checklist.tolerance_profile = {
            **checklist.tolerance_profile,
            "margin_percent": 10.0,
            "pressure_percent": 40.0,
        }
        assessment = policy.assess_task("implement feature", checklist)
        self.assertTrue(assessment.allowed)
        self.assertTrue(assessment.escalation_required)
        self.assertTrue(assessment.escalation_notes)
        self.assertIn("exceeds margin", assessment.escalation_notes[0])

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

    def test_prince2_benchmark_reports_prompt_baseline(self) -> None:
        report = run_prince2_benchmark()
        self.assertEqual(report["command"], "prince2 benchmark")
        self.assertEqual(report["baseline"]["provider"], "stagewarden")
        self.assertEqual(report["overall"]["suite_count"], 2)
        self.assertEqual(report["overall"]["total_cases"], 8)
        self.assertTrue(report["overall"]["passed"])
        self.assertTrue(report["suites"]["governance"]["passed"])
        self.assertTrue(report["suites"]["assurance"]["passed"])
        self.assertIn("prompt", report["governance"]["cases"][0])


if __name__ == "__main__":
    unittest.main()
