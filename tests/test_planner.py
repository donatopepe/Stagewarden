from __future__ import annotations

import unittest

from stagewarden.planner import Planner


class PlannerTests(unittest.TestCase):
    def test_create_plan_returns_steps_with_validation(self) -> None:
        planner = Planner()
        steps = planner.create_plan("inspect the repo and implement a fix and validate the result")
        self.assertGreaterEqual(len(steps), 3)
        for step in steps:
            self.assertTrue(step.id.startswith("step-"))
            self.assertTrue(step.instruction)
            self.assertTrue(step.validation)
            self.assertEqual(step.status, "pending")


if __name__ == "__main__":
    unittest.main()
