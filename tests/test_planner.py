from __future__ import annotations

import unittest

from stagewarden.planner import Planner
from stagewarden.project_handoff import ProjectHandoff


class PlannerTests(unittest.TestCase):
    def test_create_plan_returns_steps_with_validation(self) -> None:
        planner = Planner()
        steps = planner.create_plan("inspect the repo and implement a fix and validate the result")
        self.assertGreaterEqual(len(steps), 3)
        for step in steps:
            self.assertTrue(step.id.startswith("step-"))
            self.assertTrue(step.instruction)
            self.assertTrue(step.validation)
            self.assertTrue(step.wet_run_required)
            self.assertEqual(step.status, "pending")

    def test_create_plan_restores_step_status_from_handoff(self) -> None:
        planner = Planner()
        handoff = ProjectHandoff(
            task="inspect the repo and implement a fix and validate the result",
            status="executing",
            current_step_id="step-2",
            current_step_title="2. Implement a fix",
            current_step_status="in_progress",
            latest_observation="found failing assertion in router tests",
            plan_status="step-1:completed,step-2:in_progress,step-3:pending",
        )
        steps = planner.create_plan(
            "inspect the repo and implement a fix and validate the result",
            project_handoff=handoff,
        )
        self.assertEqual(steps[0].status, "completed")
        self.assertEqual(steps[1].status, "in_progress")
        self.assertTrue(steps[1].title.startswith("Resume "))
        self.assertIn("continue from persisted handoff context", steps[1].instruction)
        self.assertIn("failing assertion", steps[1].instruction)


if __name__ == "__main__":
    unittest.main()
