from __future__ import annotations

import unittest

from agent_cli.memory import MemoryStore


class MemoryTests(unittest.TestCase):
    def test_failure_tracking_and_loop_prevention(self) -> None:
        memory = MemoryStore()
        for iteration in range(1, 4):
            memory.record_attempt(
                iteration=iteration,
                step_id="step-1",
                model="local",
                action_type="shell",
                action_signature='{"type":"shell","command":"pwd"}',
                success=False,
                observation="failed",
                error_type="runtime_error",
            )
        self.assertEqual(memory.failure_count("step-1"), 3)
        self.assertTrue(memory.should_abort_step("step-1"))

    def test_summary_contains_recent_attempts(self) -> None:
        memory = MemoryStore()
        memory.record_attempt(
            iteration=1,
            step_id="step-1",
            model="local",
            action_type="complete",
            action_signature='{"type":"complete"}',
            success=True,
            observation="done",
        )
        self.assertIn("step=step-1", memory.summarize())


if __name__ == "__main__":
    unittest.main()
