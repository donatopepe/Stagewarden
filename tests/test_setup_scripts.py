from __future__ import annotations

import os
import subprocess
import tempfile
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

    def test_unix_setup_falls_back_to_source_launcher_when_editable_install_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            user_base = tmp / "userbase"
            fake_python = tmp / "fake-python"
            fake_python.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env sh",
                        'if [ "$1" = "-" ]; then',
                        '  cat >/dev/null',
                        '  echo "$FAKE_USER_BASE/bin"',
                        "  exit 0",
                        "fi",
                        'if [ "$1" = "-m" ] && [ "$2" = "pip" ]; then',
                        "  exit 1",
                        "fi",
                        'if [ "$1" = "-m" ] && [ "$2" = "stagewarden.main" ]; then',
                        '  echo "fake stagewarden"',
                        "  exit 0",
                        "fi",
                        "exit 0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            env = dict(os.environ)
            env["PYTHON_BIN"] = str(fake_python)
            env["FAKE_USER_BASE"] = str(user_base)
            completed = subprocess.run(
                ["sh", str(ROOT / "setup.sh")],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )

            launcher = user_base / "bin" / "stagewarden"
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(launcher.exists())
            self.assertIn("source launcher", completed.stdout)
            smoke = subprocess.run(
                [str(launcher), "--help"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(smoke.returncode, 0, smoke.stderr)
            self.assertIn("fake stagewarden", smoke.stdout)


if __name__ == "__main__":
    unittest.main()
