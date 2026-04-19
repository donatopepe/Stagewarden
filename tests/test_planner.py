from __future__ import annotations

import unittest

from stagewarden.planner import Planner
from stagewarden.project_handoff import ProjectHandoff


class PlannerTests(unittest.TestCase):
    def test_create_plan_returns_steps_with_validation(self) -> None:
        planner = Planner()
        steps = planner.create_plan("inspect the repo and implement a fix and validate the result")
        self.assertGreaterEqual(len(steps), 3)
        for index, step in enumerate(steps):
            self.assertTrue(step.id.startswith("step-"))
            self.assertTrue(step.instruction)
            self.assertTrue(step.validation)
            self.assertTrue(step.wet_run_required)
            self.assertEqual(step.status, "ready" if index == 0 else "planned")

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
        self.assertEqual(steps[2].status, "planned")
        self.assertTrue(steps[1].title.startswith("Resume "))
        self.assertIn("continue from persisted handoff context", steps[1].instruction)
        self.assertIn("failing assertion", steps[1].instruction)

    def test_create_plan_compresses_completed_prefix_from_handoff(self) -> None:
        planner = Planner()
        handoff = ProjectHandoff(
            task="inspect the repo and implement a fix and validate the result",
            status="executing",
            current_step_id="step-3",
            current_step_title="3. Validate the result",
            current_step_status="in_progress",
            latest_observation="implementation finished, validation pending",
            plan_status="step-1:completed,step-2:completed,step-3:in_progress",
        )
        steps = planner.create_plan(
            "inspect the repo and implement a fix and validate the result",
            project_handoff=handoff,
        )
        self.assertEqual(steps[0].id, "stage-archive-1")
        self.assertEqual(steps[0].status, "completed")
        self.assertIn("historical completed stages compressed", steps[0].instruction)
        self.assertEqual(steps[1].id, "step-3")
        self.assertTrue(steps[1].title.startswith("Resume "))

    def test_create_plan_includes_register_context_on_active_step(self) -> None:
        planner = Planner()
        handoff = ProjectHandoff(
            task="inspect the repo and implement a fix and validate the result",
            status="executing",
            current_step_id="step-2",
            current_step_title="2. Implement a fix",
            current_step_status="in_progress",
            latest_observation="found failing assertion in router tests",
            plan_status="step-1:completed,step-2:in_progress,step-3:planned",
            risk_register=[{"risk": "Regression from router patch", "status": "open"}],
            issue_register=[{"summary": "validation pending", "status": "open"}],
            quality_register=[{"status": "passed", "evidence": "router file updated"}],
            lessons_log=[{"lesson": "inspect git state before patching"}],
        )
        steps = planner.create_plan(
            "inspect the repo and implement a fix and validate the result",
            project_handoff=handoff,
        )
        self.assertIn("open_risks=Regression from router patch", steps[1].instruction)
        self.assertIn("open_issues=validation pending", steps[1].instruction)
        self.assertIn("quality_baseline=passed:router file updated", steps[1].instruction)
        self.assertIn("lesson=inspect git state before patching", steps[1].instruction)
        self.assertIn("PRINCE2 register context", steps[1].validation)

    def test_create_plan_includes_exception_plan_when_project_in_exception(self) -> None:
        planner = Planner()
        handoff = ProjectHandoff(
            task="inspect the repo and implement a fix and validate the result",
            status="exception",
            current_step_id="step-2",
            current_step_title="2. Implement a fix",
            current_step_status="failed",
            latest_observation="tests failed after patch",
            plan_status="step-1:completed,step-2:failed,step-3:planned",
            exception_plan=["review failing test output", "prepare corrective patch"],
        )
        steps = planner.create_plan(
            "inspect the repo and implement a fix and validate the result",
            project_handoff=handoff,
        )
        self.assertIn("exception_plan=review failing test output; prepare corrective patch", steps[1].instruction)

    def test_create_plan_promotes_first_non_completed_stage_to_ready(self) -> None:
        planner = Planner()
        handoff = ProjectHandoff(
            task="inspect the repo and implement a fix and validate the result",
            status="planned",
            plan_status="step-1:completed,step-2:planned,step-3:planned",
        )
        steps = planner.create_plan(
            "inspect the repo and implement a fix and validate the result",
            project_handoff=handoff,
        )
        self.assertEqual(steps[0].status, "completed")
        self.assertEqual(steps[1].status, "ready")
        self.assertEqual(steps[2].status, "planned")


if __name__ == "__main__":
    unittest.main()
