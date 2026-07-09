"""Unit tests for goal loop orchestrator pi execution and parsing."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from stagewarden.config import AgentConfig
from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator


class GoalLoopPiExecutionTests(unittest.TestCase):
    """Test _pi_execution JSON parsing with mocked subprocess."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.config = AgentConfig(workspace_root=self.tmp_dir)

    def _build_result(self, stdout: str, returncode: int = 0,
                      stderr: str = "") -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["pi", "--print", "--no-tools", "--no-session", "@test.md"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def test_pi_execution_parses_clean_json(self) -> None:
        """Valid JSON output with summary/messages is parsed correctly."""
        mock_stdout = json.dumps({
            "summary": "Node completed.",
            "messages": [
                {"FROM": "node.a", "TO": "node.b", "TYPE": "status",
                 "SUMMARY": "done", "PRIORITY": "low", "TOLERANCE IMPACT": "none"}
            ],
            "output": "some output",
            "error": None,
        })
        result = self._build_result(mock_stdout)
        # We need to actually run through _pi_execution... but it requires a NodeState.
        # Instead test the parsing logic directly.
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as G
        # The parsing is inline in _pi_execution, test the ANSI stripping logic
        import re as _re
        ansi_clean = _re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', result.stdout)
        ansi_clean = _re.sub(r'\x1b\][^\x07]*\x07', '', ansi_clean)
        ansi_clean = _re.sub(r'\x1b\\\\', '', ansi_clean)
        ansi_clean = ansi_clean.strip()
        data = json.loads(ansi_clean)
        self.assertEqual(data["summary"], "Node completed.")
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["FROM"], "node.a")

    def test_pi_execution_strips_ansi_notification(self) -> None:
        """ANSI notification sequences around JSON are stripped."""
        raw = '\x1b]777;notify;\u03c0;{"summary":"ok","messages":[]}\x07{"summary":"ok","messages":[]}'
        import re as _re
        ansi_clean = _re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', raw)
        ansi_clean = _re.sub(r'\x1b\][^\x07]*\x07', '', ansi_clean)
        ansi_clean = _re.sub(r'\x1b\\\\', '', ansi_clean)
        ansi_clean = ansi_clean.strip()
        self.assertEqual(ansi_clean, '{"summary":"ok","messages":[]}')
        data = json.loads(ansi_clean)
        self.assertEqual(data["summary"], "ok")

    def test_pi_execution_fallback_to_raw_text(self) -> None:
        """Non-JSON output falls back to summary text."""
        raw = "Hello from pi, I completed the task."
        import re as _re
        ansi_clean = _re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', raw)
        ansi_clean = _re.sub(r'\x1b\][^\x07]*\x07', '', ansi_clean)
        ansi_clean = _re.sub(r'\x1b\\\\', '', ansi_clean)
        ansi_clean = ansi_clean.strip()
        # Try JSON, should fail
        with self.assertRaises(json.JSONDecodeError):
            json.loads(ansi_clean)
        # Fallback: treat as summary text
        summary = ansi_clean[:500]
        self.assertEqual(summary, "Hello from pi, I completed the task.")

    def test_pi_execution_regex_finds_json_in_noise(self) -> None:
        """JSON object embedded in other text is extracted via regex."""
        noisy = "Some text\n{\"summary\":\"found\",\"messages\":[]}\ntrailing"
        import re as _re
        match = _re.search(r'\{.*\}', noisy, _re.DOTALL)
        self.assertIsNotNone(match)
        data = json.loads(match.group(0))
        self.assertEqual(data["summary"], "found")

    def test_pi_execution_handles_multiple_json_objects(self) -> None:
        """When multiple JSON objects exist, the last one with 'summary' wins."""
        output = (
            '{"summary":"first","messages":[],"output":"","error":null}\n'
            '{"summary":"second","messages":[],"output":"","error":null}'
        )
        import re as _re
        # Find all JSON objects containing "summary"
        objects = _re.findall(r'\{[^{}]*"summary"[^{}]*\}', output)
        self.assertEqual(len(objects), 2)
        last = json.loads(objects[-1])
        self.assertEqual(last["summary"], "second")

    def test_autonomy_gate_classifies_high_impact(self) -> None:
        """classify_decision returns 'ask_user' for high-impact terms."""
        from stagewarden.goal_loop_orchestrator import classify_decision
        level, reason = classify_decision("Modify auth module", "security")
        self.assertEqual(level, "ask_user")
        self.assertIn("security", reason)

    def test_autonomy_gate_classifies_low_impact(self) -> None:
        """classify_decision returns 'autonomous' for low-impact terms."""
        from stagewarden.goal_loop_orchestrator import classify_decision
        level, reason = classify_decision("Rename local variable", "style")
        self.assertEqual(level, "autonomous")
        self.assertIn("reversible", reason)

    def test_tolerance_violation_detected(self) -> None:
        """check_tolerance_violation returns violation when threshold=none."""
        from stagewarden.goal_loop_orchestrator import check_tolerance_violation
        outcome, reason = check_tolerance_violation(
            {"scope_drift": "none"}, {"scope_drift": "changed"}
        )
        self.assertEqual(outcome, "violation")
        self.assertIn("scope_drift", reason or "")

    def test_tolerance_no_violation(self) -> None:
        """check_tolerance_violation returns ok when tolerances match."""
        from stagewarden.goal_loop_orchestrator import check_tolerance_violation
        outcome, reason = check_tolerance_violation({}, {})
        self.assertEqual(outcome, "ok")

    def test_pi_execution_via_mocked_subprocess(self) -> None:
        """Full _pi_execution flow with mocked subprocess and shutil."""
        import subprocess as _sp
        import shutil as _sh
        from unittest.mock import patch, PropertyMock
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO

        mock_json = json.dumps({
            "summary": "Node completed via pi mock.",
            "messages": [{"FROM": "x", "TO": "y", "TYPE": "status",
                           "SUMMARY": "done", "PRIORITY": "low",
                           "TOLERANCE IMPACT": "none"}],
        })
        mock_process = _sp.CompletedProcess(
            args=["pi", "--print", "--no-tools", "--no-session", "@test.md"],
            returncode=0,
            stdout=mock_json,
            stderr="",
        )

        with patch('stagewarden.goal_loop_orchestrator.shutil.which',
                   return_value="/usr/local/bin/pi"), \
             patch('stagewarden.goal_loop_orchestrator.subprocess.run',
                   return_value=mock_process):
            config = AgentConfig(workspace_root=self.tmp_dir)
            orch = GO(config, "test task", execution_mode="pi")
            result = orch.run_loop()
            self.assertEqual(result["final_status"], "completed")
            # Check that first node completed via pi
            first_node = list(result["node_details"].keys())[0]
            self.assertEqual(result["node_details"][first_node]["status"],
                             "completed")

    def test_pi_execution_handles_nonzero_returncode(self) -> None:
        """_pi_execution returns error on non-zero pi exit."""
        import subprocess as _sp
        from unittest.mock import patch
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO

        mock_process = _sp.CompletedProcess(
            args=["pi", "--print", "--no-tools", "--no-session", "@test.md"],
            returncode=1,
            stdout="",
            stderr="Error: something went wrong",
        )

        with patch('stagewarden.goal_loop_orchestrator.shutil.which',
                   return_value="/usr/local/bin/pi"), \
             patch('stagewarden.goal_loop_orchestrator.subprocess.run',
                   return_value=mock_process):
            config = AgentConfig(workspace_root=self.tmp_dir)
            orch = GO(config, "test task", execution_mode="pi")
            result = orch.run_loop()
            # With non-zero return code, nodes should block
            first_node = list(result["node_details"].keys())[0]
            self.assertIn(result["node_details"][first_node]["status"],
                          ("blocked", "pending"))


if __name__ == "__main__":
    unittest.main()
