from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewarden.memory import MemoryStore


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

    def test_model_usage_summary_counts_calls_failures_and_cost_tiers(self) -> None:
        memory = MemoryStore()
        memory.record_attempt(
            iteration=1,
            step_id="step-1",
            model="local",
            action_type="shell",
            action_signature='{"type":"shell"}',
            success=True,
            observation="ok",
        )
        memory.record_attempt(
            iteration=2,
            step_id="step-1",
            model="openai",
            action_type="shell",
            action_signature='{"type":"shell"}',
            success=False,
            observation="quota",
            error_type="api_failure",
        )

        rendered = memory.model_usage_summary()

        self.assertIn("Model usage:", rendered)
        self.assertIn("local: calls=1 failures=0 steps=1 cost_tier=free/local", rendered)
        self.assertIn("openai: calls=1 failures=1 steps=1 cost_tier=high", rendered)
        self.assertIn("Budget policy: prefer local", rendered)

    def test_tool_transcript_is_persisted_and_rendered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / ".stagewarden_memory.json"
            memory = MemoryStore()
            memory.record_tool_transcript(
                iteration=1,
                step_id="step-1",
                tool="shell",
                action_type="shell",
                success=True,
                summary="python3 -m unittest",
                detail="exit_code=0",
                duration_ms=12,
            )
            memory.save(path)
            loaded = MemoryStore.load(path)
            rendered = loaded.transcript_summary()
            self.assertIn("Tool transcript:", rendered)
            self.assertIn("tool=shell", rendered)
            self.assertIn("summary=python3 -m unittest", rendered)
            self.assertIn("detail=exit_code=0", rendered)


if __name__ == "__main__":
    unittest.main()
