from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig
from stagewarden.memory import MemoryStore
from stagewarden.project_handoff import ProjectHandoff


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

    def test_project_handoff_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / ".stagewarden_handoff.json"
            handoff = ProjectHandoff()
            handoff.start_run(task="fix tests", plan_status="step-1:pending", git_head="abc123")
            handoff.begin_step(
                iteration=1,
                task="fix tests",
                step_id="step-1",
                step_title="1. Fix tests",
                step_status="in_progress",
                git_head="abc123",
            )
            handoff.record_issue(step_id="step-1", severity="medium", summary="failing test still open")
            handoff.record_quality(step_id="step-1", status="observed", evidence="pytest -q executed")
            handoff.record_lesson(step_id="step-1", lesson_type="observation", lesson="pytest exposed an unstable assertion")
            handoff.complete_step(
                iteration=1,
                task="fix tests",
                step_id="step-1",
                step_title="1. Fix tests",
                step_status="completed",
                model="openai",
                action_type="complete",
                observation="validation completed exit_code=0",
                git_head="def456",
            )
            handoff.save(path)
            loaded = ProjectHandoff.load(path)
            self.assertEqual(loaded.task, "fix tests")
            self.assertEqual(loaded.git_head, "def456")
            self.assertEqual(len(loaded.entries), 3)
            self.assertEqual(len(loaded.issue_register), 1)
            self.assertEqual(len(loaded.quality_register), 1)
            self.assertEqual(len(loaded.lessons_log), 1)

    def test_project_handoff_can_close_step_issues_and_clear_exception_plan(self) -> None:
        handoff = ProjectHandoff(
            current_step_id="step-1",
            current_step_status="completed",
            issue_register=[
                {"step_id": "step-1", "severity": "medium", "summary": "validation pending", "status": "open"},
                {"step_id": "step-2", "severity": "high", "summary": "other issue", "status": "open"},
            ],
            exception_plan=["review boundary for step-1"],
        )
        handoff.close_issues_for_step(step_id="step-1", resolution="step completed with wet-run evidence")
        self.assertEqual(handoff.issue_register[0]["status"], "closed")
        self.assertIn("resolution", handoff.issue_register[0])
        self.assertEqual(handoff.issue_register[1]["status"], "open")

        handoff.issue_register[1]["status"] = "closed"
        handoff.clear_exception_plan_if_recovered()
        self.assertEqual(handoff.exception_plan, [])


if __name__ == "__main__":
    unittest.main()
