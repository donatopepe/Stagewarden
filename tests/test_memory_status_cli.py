from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class MemoryStatusCliTests(unittest.TestCase):
    def test_memory_status_json_reports_disabled_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [sys.executable, "-m", "stagewarden.main", "memory status", "--json"],
                cwd=tmp,
                env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "memory status")
            self.assertFalse(payload["enabled"])
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["schema"]["name"], "stagewarden.memory_status")

if __name__ == "__main__":
    unittest.main()
