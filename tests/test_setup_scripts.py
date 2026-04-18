from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SetupScriptTests(unittest.TestCase):
    def test_unix_setup_script_exists_and_installs_editable(self) -> None:
        script = ROOT / "scripts" / "setup_unix.sh"
        content = script.read_text(encoding="utf-8")
        self.assertTrue(script.exists())
        self.assertIn("command -v git", content)
        self.assertIn("pip install --user -e", content)
        self.assertIn("source launcher", content)
        self.assertIn("PYTHONPATH", content)
        self.assertIn("Stagewarden installed (", content)

    def test_windows_setup_script_exists_and_updates_path(self) -> None:
        script = ROOT / "scripts" / "setup_windows.ps1"
        content = script.read_text(encoding="utf-8")
        self.assertTrue(script.exists())
        self.assertIn("Get-Command git", content)
        self.assertIn("pip install --user -e", content)
        self.assertIn("source launcher", content)
        self.assertIn("PYTHONPATH", content)
        self.assertIn("SetEnvironmentVariable", content)


if __name__ == "__main__":
    unittest.main()
