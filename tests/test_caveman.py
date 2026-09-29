from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.caveman import CavemanManager
from stagewarden.config import AgentConfig


class CavemanTests(unittest.TestCase):
    NON_OBJECT_STATE = {
        "top-level list": "[1, 2]",
        "top-level string": '"a string"',
        "top-level number": "42",
        "null": "null",
    }

    def test_non_object_caveman_state_never_breaks_agent_construction(self) -> None:
        """Agent.__init__ loads caveman state, so a wrong-shaped file crashed it.

        CavemanManager.load_state already caught OSError/ValueError/TypeError and
        JSONDecodeError, so malformed JSON failed closed, but a persisted root that
        parsed to a list, string, number or null raised AttributeError past it.
        """
        for label, body in self.NON_OBJECT_STATE.items():
            with self.subTest(state=label):
                with tempfile.TemporaryDirectory() as tmp:
                    config = AgentConfig(workspace_root=Path(tmp))
                    config.caveman_state_path.parent.mkdir(parents=True, exist_ok=True)
                    config.caveman_state_path.write_text(body, encoding="utf-8")
                    try:
                        agent = Agent(config)
                    except Exception as exc:  # noqa: BLE001 - the defect under test
                        self.fail(f"Agent() with {label} raised {type(exc).__name__}: {exc}")
                    self.assertFalse(agent.caveman_state.active)
                    self.assertEqual(agent.caveman_state.level, "full")

    def test_caveman_state_already_failing_closed_stays_that_way(self) -> None:
        """Controls: shapes load_state already handled, and a real round-trip."""
        tolerated = {
            "not json": "this is not json",
            "truncated": '{"active":',
            "empty file": "",
        }
        for label, body in tolerated.items():
            with self.subTest(state=label):
                with tempfile.TemporaryDirectory() as tmp:
                    config = AgentConfig(workspace_root=Path(tmp))
                    config.caveman_state_path.parent.mkdir(parents=True, exist_ok=True)
                    config.caveman_state_path.write_text(body, encoding="utf-8")
                    self.assertFalse(Agent(config).caveman_state.active)
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(workspace_root=Path(tmp))
            manager = CavemanManager()
            state = manager.parse("@caveman ultra fix login bug")
            self.assertTrue(state.active)
            manager.save_state(config, state)
            loaded = manager.load_state(config)
            self.assertTrue(loaded.active)
            self.assertEqual(loaded.level, state.level)
            self.assertFalse(CavemanManager().load_state(
                AgentConfig(workspace_root=Path(tmp) / "elsewhere")
            ).active)

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
