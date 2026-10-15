from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_handoff_alignment.py"
SPEC = importlib.util.spec_from_file_location("check_handoff_alignment", SCRIPT)
assert SPEC and SPEC.loader
check_handoff_alignment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_handoff_alignment)

SECTIONS = (
    "## Current objective",
    "## Current state",
    "## Recent changes",
    "## Important files",
    "## Technical decisions",
    "## Open issues",
    "## Next steps",
    "## Commands",
)


def _write_aligned_fixture(root: Path) -> None:
    (root / "AGENT_HANDOFF.md").write_text("# Agent Handoff\n\n" + "\n".join(SECTIONS) + "\n", encoding="utf-8")
    (root / "HANDOFF.md").write_text("# Stagewarden Handoff Summary\n\ncontent\n", encoding="utf-8")
    (root / ".stagewarden_handoff.json").write_text(
        json.dumps(
            {
                "status": "active",
                "waiting_reason": "working",
                "current_step_id": "step",
                "current_step_title": "title",
                "current_step_status": "active",
            }
        ),
        encoding="utf-8",
    )


class HandoffAlignmentTests(unittest.TestCase):
    def test_check_passes_on_aligned_fixture_and_real_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_aligned_fixture(root)
            self.assertEqual(check_handoff_alignment.check(root), [])
        real_root = Path(__file__).resolve().parents[1]
        self.assertEqual(check_handoff_alignment.check(real_root), [])

    def test_check_fails_closed_on_missing_or_malformed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_aligned_fixture(root)
            (root / "AGENT_HANDOFF.md").write_text("# Agent Handoff\n\n## Current objective\n", encoding="utf-8")
            errors = check_handoff_alignment.check(root)
            self.assertTrue(any("missing required section" in error for error in errors))
            (root / ".stagewarden_handoff.json").write_text("{not json", encoding="utf-8")
            self.assertTrue(any("not valid JSON" in error for error in check_handoff_alignment.check(root)))
            (root / ".stagewarden_handoff.json").write_text(
                json.dumps({"status": "active", "waiting_reason": "  "}), encoding="utf-8"
            )
            errors = check_handoff_alignment.check(root)
            self.assertTrue(any("missing key" in error for error in errors))
            self.assertTrue(any("waiting_reason" in error for error in errors))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(check_handoff_alignment.check(Path(tmp)))

    def test_main_returns_nonzero_on_broken_root_and_zero_on_real_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(check_handoff_alignment.main(["--root", tmp]), 1)
        real_root = Path(__file__).resolve().parents[1]
        self.assertEqual(check_handoff_alignment.main(["--root", str(real_root)]), 0)


if __name__ == "__main__":
    unittest.main()
