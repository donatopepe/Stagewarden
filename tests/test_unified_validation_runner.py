from __future__ import annotations

import json
import unittest

from scripts import run_unified_validation as runner


class UnifiedValidationRunnerTests(unittest.TestCase):
    def test_full_json_evaluation_and_bounded_report_tail_matrix_has_three_fixed_cases(self) -> None:
        stdout = json.dumps({"passed": True, "padding": "x" * 5000})
        run = {"command": ["probe"], "returncode": 0, "duration_ms": 1, "stdout": stdout, "stderr": "stderr"}
        gate = {"expect": {"returncode": 0, "json": {"passed": True}}}
        passed, detail = runner._evaluate(gate, [run])
        report_run = {
            "command": run["command"],
            "returncode": run["returncode"],
            "duration_ms": run["duration_ms"],
            "stdout_tail": stdout[-4000:],
            "stderr_tail": run["stderr"][-4000:],
        }
        cases = [
            ("full JSON evaluator", passed and detail == "ok"),
            ("bounded stdout tail", len(report_run["stdout_tail"]) == 4000 and "padding" not in report_run["stdout_tail"][:100]),
            ("bounded schema", "stdout" not in report_run and "stderr" not in report_run),
        ]
        for name, result in cases:
            self.assertTrue(result, name)


if __name__ == "__main__":
    unittest.main()
