from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_simulation_matrix.py"


class SimulationMatrixTests(unittest.TestCase):
    def run_matrix(self, *args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        completed = subprocess.run(
            [sys.executable, str(RUNNER), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertTrue(completed.stdout, completed.stderr)
        return completed, json.loads(completed.stdout)

    def test_matrix_is_complete_and_listable(self) -> None:
        completed, report = self.run_matrix("--list")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(report["coverage"], {"scenario_count": 29, "category_count": 6})
        self.assertEqual(len(report["scenarios"]), 29)

    def test_total_run_is_wet_and_fail_closed(self) -> None:
        completed, report = self.run_matrix()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(report["passed"])
        self.assertEqual(report["selection"]["mode"], "total")
        self.assertEqual(report["coverage"]["selected"], 29)
        self.assertEqual(report["coverage"]["passed"], 29)
        self.assertEqual(report["coverage"]["failed"], 0)
        self.assertEqual(report["execution"]["battery_total"], 29)

    def test_granular_scenario_run(self) -> None:
        completed, report = self.run_matrix("--scenario", "executor_write_file")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(report["passed"])
        self.assertEqual(report["selection"]["scenario_ids"], ["executor_write_file"])
        self.assertEqual(report["coverage"]["selected"], 1)
        self.assertEqual(report["execution"]["battery_total"], 1)

    def test_granular_category_run(self) -> None:
        completed, report = self.run_matrix("--category", "role-runtime")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(report["passed"])
        self.assertEqual(report["selection"]["mode"], "category")
        self.assertEqual(report["coverage"]["selected"], 10)
        self.assertEqual(report["execution"]["battery_total"], 10)

    def test_unknown_selection_fails(self) -> None:
        completed, report = self.run_matrix("--scenario", "missing")
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(report["passed"])
        self.assertIn("unknown scenario", report["error"])


if __name__ == "__main__":
    unittest.main()
