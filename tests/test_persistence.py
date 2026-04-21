from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig
from stagewarden.memory import MemoryStore
from stagewarden.modelprefs import ModelPreferences
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
            handoff.sync_prince2_roles(
                {
                    "project_manager": {
                        "label": "Project Manager",
                        "mode": "manual",
                        "provider": "chatgpt",
                        "provider_model": "gpt-5.4",
                        "params": {"reasoning_effort": "high"},
                        "account": None,
                        "source": "unit_test",
                    }
                }
            )
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
            self.assertEqual(loaded.prince2_roles["project_manager"]["provider_model"], "gpt-5.4")

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

    def test_project_handoff_can_close_all_open_risks(self) -> None:
        handoff = ProjectHandoff(
            risk_register=[
                {"risk": "regression risk", "status": "open"},
                {"risk": "deployment risk", "status": "closed"},
            ]
        )
        handoff.close_all_open_risks(resolution="project closed with controlled completion")
        self.assertEqual(handoff.risk_register[0]["status"], "closed")
        self.assertIn("resolution", handoff.risk_register[0])
        self.assertEqual(handoff.risk_register[1]["status"], "closed")

    def test_project_handoff_can_finalize_quality_register(self) -> None:
        handoff = ProjectHandoff(
            quality_register=[
                {"step_id": "step-1", "status": "observed", "evidence": "pytest -q executed"},
                {"step_id": "step-2", "status": "accepted", "evidence": "integration tests passed"},
            ]
        )
        handoff.finalize_quality_register(resolution="project closed with controlled completion")
        self.assertEqual(handoff.quality_register[0]["status"], "accepted")
        self.assertIn("accepted_at", handoff.quality_register[0])
        self.assertIn("resolution", handoff.quality_register[0])
        self.assertEqual(handoff.quality_register[1]["status"], "accepted")

    def test_model_preferences_roundtrip_preserves_last_limit_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / ".stagewarden_models.json"
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "claude"]
            prefs.set_variant("chatgpt", "gpt-5.3-codex")
            prefs.set_model_param("chatgpt", "reasoning_effort", "high")
            prefs.set_prince2_role_assignment(
                "project_manager",
                mode="manual",
                provider="chatgpt",
                provider_model="gpt-5.3-codex",
                params={"reasoning_effort": "high"},
                source="unit_test",
            )
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.last_limit_message_by_model = {"chatgpt": "You've hit your usage limit. Try again at 8:05 PM."}
            prefs.set_model_limit_snapshot(
                "chatgpt",
                {
                    "status": "blocked",
                    "reason": "usage_limit",
                    "blocked_until": "2026-05-01T18:30",
                    "rate_limit_type": "usage_limit",
                    "utilization": 88,
                    "captured_at": "2026-05-01T17:30",
                    "raw_message": "You've hit your usage limit. Try again at 8:05 PM.",
                },
            )
            prefs.add_account("claude", "team")
            prefs.block_account("claude", "team", "2026-05-01T19:00")
            prefs.last_limit_message_by_account = {"claude:team": "Claude usage limited until 2026-05-01T19:00."}
            prefs.set_account_limit_snapshot(
                "claude",
                "team",
                {
                    "status": "blocked",
                    "reason": "usage_limit",
                    "blocked_until": "2026-05-01T19:00",
                    "primary_window": "five_hour",
                    "secondary_window": "sonnet",
                    "rate_limit_type": "five_hour_sonnet",
                    "captured_at": "2026-05-01T18:00",
                    "raw_message": "Claude usage limited until 2026-05-01T19:00.",
                },
            )
            prefs.save(path)

            loaded = ModelPreferences.load(path)
            self.assertEqual((loaded.last_limit_message_by_model or {})["chatgpt"], "You've hit your usage limit. Try again at 8:05 PM.")
            self.assertEqual((loaded.last_limit_message_by_account or {})["claude:team"], "Claude usage limited until 2026-05-01T19:00.")
            self.assertEqual((loaded.provider_limit_snapshot_by_model or {})["chatgpt"]["utilization"], 88.0)
            self.assertEqual((loaded.params_by_model or {})["chatgpt"]["reasoning_effort"], "high")
            self.assertEqual((loaded.prince2_roles or {})["project_manager"]["provider_model"], "gpt-5.3-codex")
            self.assertEqual((loaded.prince2_roles or {})["project_manager"]["params"]["reasoning_effort"], "high")
            self.assertEqual(
                (loaded.provider_limit_snapshot_by_account or {})["claude:team"]["rate_limit_type"],
                "five_hour_sonnet",
            )


if __name__ == "__main__":
    unittest.main()
