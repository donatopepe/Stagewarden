from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.caveman import CavemanManager
from stagewarden.config import AgentConfig


class CavemanTests(unittest.TestCase):
    def test_parse_mention_activation_and_level(self) -> None:
        directive = CavemanManager().parse("@caveman ultra fix login bug")
        self.assertTrue(directive.active)
        self.assertEqual(directive.level, "ultra")
        self.assertIn("fix login bug", directive.stripped_task)

    def test_help_trigger(self) -> None:
        directive = CavemanManager().parse("/caveman help")
        self.assertEqual(directive.command, "help")

    def test_compress_file_preserves_code(self) -> None:
        manager = CavemanManager()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "notes.md"
            target.write_text("# Title\nYou should always make sure to run tests.\n```py\nprint('x')\n```\n")
            message = manager.compress_file("notes.md", AgentConfig(workspace_root=root))
            self.assertIn("Compressed notes.md", message)
            self.assertIn("print('x')", target.read_text())
            self.assertTrue((root / "notes.original.md").exists())

    def test_agent_help_command(self) -> None:
        result = Agent(AgentConfig(workspace_root=Path.cwd())).run("/caveman help")
        self.assertTrue(result.ok)
        self.assertIn("Caveman commands", result.message)

    def test_caveman_state_persists_between_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root))
            result = agent.run("/caveman ultra")
            self.assertTrue(result.ok)
            state = json.loads((root / ".stagewarden_caveman.json").read_text())
            self.assertTrue(state["active"])
            self.assertEqual(state["level"], "ultra")

            second = Agent(AgentConfig(workspace_root=root))
            directive = second._merge_caveman_state(CavemanManager().parse("fix bug"), "fix bug")
            self.assertTrue(directive.active)
            self.assertEqual(directive.level, "ultra")

    def test_stop_caveman_clears_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root))
            agent.run("/caveman lite")
            result = agent.run("stop caveman")
            self.assertTrue(result.ok)
            self.assertFalse((root / ".stagewarden_caveman.json").exists())

    def test_compress_validation_rejects_non_natural_language_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "config.json"
            target.write_text('{"x":1}\n')
            with self.assertRaises(ValueError):
                CavemanManager().compress_file("config.json", AgentConfig(workspace_root=root))

    def test_compress_command_does_not_persist_active_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "notes.md").write_text("You should run tests.\n")
            agent = Agent(AgentConfig(workspace_root=root))
            result = agent.run("/caveman compress notes.md")
            self.assertTrue(result.ok)
            self.assertFalse((root / ".stagewarden_caveman.json").exists())


if __name__ == "__main__":
    unittest.main()
