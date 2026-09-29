from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewarden.modelprefs import ModelPreferences


class ModelSelectionPolicyTests(unittest.TestCase):
    def test_malformed_prefs_file_never_breaks_a_model_execution_cycle(self) -> None:
        """execute_step loads preferences on EVERY cycle, so it must never raise.

        _configure_handoff_accounts catches OSError only, and ModelPreferences.load
        raised JSONDecodeError for malformed JSON, so a corrupt prefs file aborted
        the agent's main loop. The tolerance belongs in the loader, which now
        treats every unusable payload exactly like a missing file.
        """
        from stagewarden.config import AgentConfig
        from stagewarden.executor import Executor
        from stagewarden.handoff import HandoffManager
        from stagewarden.memory import MemoryStore
        from stagewarden.planner import PlanStep
        from stagewarden.project_handoff import ProjectHandoff
        from stagewarden.rag import DesignRag
        from stagewarden.router import ModelRouter

        corrupt = {
            "not json": "this is not json",
            "truncated": '{"enabled_models": [',
            "empty file": "",
            "top-level list": "[1, 2]",
            "null": "null",
        }
        for label, body in corrupt.items():
            with self.subTest(prefs=label):
                with tempfile.TemporaryDirectory() as tmp:
                    config = AgentConfig(workspace_root=Path(tmp))
                    config.model_prefs_path.parent.mkdir(parents=True, exist_ok=True)
                    config.model_prefs_path.write_text(body, encoding="utf-8")
                    executor = Executor(
                        config=config,
                        router=ModelRouter(),
                        handoff=HandoffManager(),
                        memory=MemoryStore(),
                        project_handoff=ProjectHandoff(),
                        rag=DesignRag(),
                    )
                    try:
                        step = PlanStep(
                            id="s1", title="T", instruction="do it", validation="ok"
                        )
                        # The model handoff is a real HandoffManager here; we only
                        # assert that reaching configuration never raises, so the
                        # probe stops at the first sign of model work.
                        try:
                            executor._configure_handoff_accounts()
                        finally:
                            executor.knowledge.close()
                    except Exception as exc:  # noqa: BLE001 - the defect under test
                        self.fail(
                            f"_configure_handoff_accounts with {label} raised "
                            f"{type(exc).__name__}: {exc}"
                        )
                    self.assertEqual(
                        ModelPreferences.load(config.model_prefs_path),
                        ModelPreferences.default(),
                    )

    NON_OBJECT_PREFS = {
        "top-level list": "[1, 2]",
        "top-level string": '"a string"',
        "top-level number": "42",
        "null": "null",
    }

    def test_non_object_prefs_file_never_breaks_agent_construction(self) -> None:
        """Agent.__init__ loads model preferences, so a wrong-shaped file crashed it.

        A measurement across the three agent.py loaders found this the only
        reachable one: memory and rag already fail closed, and malformed JSON was
        already tolerated by the caller, but a root that parses to a list, string,
        number or null raised AttributeError past the caller's except tuple.
        """
        from stagewarden.agent import Agent
        from stagewarden.config import AgentConfig

        for label in self.NON_OBJECT_PREFS:
            with self.subTest(prefs=label):
                with tempfile.TemporaryDirectory() as tmp:
                    config = AgentConfig(workspace_root=Path(tmp))
                    config.model_prefs_path.parent.mkdir(parents=True, exist_ok=True)
                    config.model_prefs_path.write_text(
                        self.NON_OBJECT_PREFS[label], encoding="utf-8"
                    )
                    try:
                        Agent(config)
                    except Exception as exc:  # noqa: BLE001 - the defect under test
                        self.fail(f"Agent() with {label} raised {type(exc).__name__}: {exc}")
                    self.assertEqual(
                        ModelPreferences.load(config.model_prefs_path),
                        ModelPreferences.default(),
                    )

    def test_corrupt_prefs_never_breaks_agent_and_non_object_loads_defaults(self) -> None:
        """Every corrupt prefs shape must leave Agent usable.

        Non-object roots are additionally asserted to return default() from load
        itself, matching the missing-file contract. Malformed JSON is asserted
        only at the Agent level, because _apply_workspace_model_preferences is the
        component that already tolerates decode errors.
        """
        from stagewarden.agent import Agent
        from stagewarden.config import AgentConfig

        malformed = {
            "not json": "this is not json",
            "truncated": '{"enabled_models": [',
            "empty file": "",
        }
        for label, body in malformed.items():
            with self.subTest(prefs=label):
                with tempfile.TemporaryDirectory() as tmp:
                    config = AgentConfig(workspace_root=Path(tmp))
                    config.model_prefs_path.parent.mkdir(parents=True, exist_ok=True)
                    config.model_prefs_path.write_text(body, encoding="utf-8")
                    self.assertIsNotNone(Agent(config))

        for label, body in self.NON_OBJECT_PREFS.items():
            with self.subTest(prefs=label):
                with tempfile.TemporaryDirectory() as tmp:
                    config = AgentConfig(workspace_root=Path(tmp))
                    config.model_prefs_path.parent.mkdir(parents=True, exist_ok=True)
                    config.model_prefs_path.write_text(body, encoding="utf-8")
                    self.assertEqual(
                        ModelPreferences.load(config.model_prefs_path),
                        ModelPreferences.default(),
                    )
                    self.assertIsNotNone(Agent(config))

        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(workspace_root=Path(tmp))
            self.assertEqual(
                ModelPreferences.load(config.model_prefs_path), ModelPreferences.default()
            )
            self.assertIsNotNone(Agent(config))
            prefs = ModelPreferences.default()
            prefs.preferred_model = "local"
            prefs.save(config.model_prefs_path)
            self.assertEqual(
                ModelPreferences.load(config.model_prefs_path).preferred_model, "local"
            )

    def test_manual_selection_and_fallback_policy_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.json"
            prefs = ModelPreferences.default()
            self.assertEqual(prefs.selection_mode, "manual")
            self.assertFalse(prefs.allow_provider_fallback)
            prefs.selection_mode = "auto"
            prefs.allow_provider_fallback = True
            prefs.allow_paid_provider = True
            prefs.save(path)
            loaded = ModelPreferences.load(path)
            self.assertEqual(loaded.selection_mode, "auto")
            self.assertTrue(loaded.allow_provider_fallback)
            self.assertTrue(loaded.allow_paid_provider)

    def test_invalid_selection_mode_fails_to_manual(self) -> None:
        prefs = ModelPreferences.default()
        prefs.selection_mode = "silent"
        prefs.normalize()
        self.assertEqual(prefs.selection_mode, "manual")

    def test_manual_policy_defaults_to_no_provider_fallback(self) -> None:
        prefs = ModelPreferences.default()
        self.assertEqual(prefs.selection_mode, "manual")
        self.assertFalse(prefs.allow_provider_fallback)
        self.assertFalse(prefs.allow_paid_provider)

    def test_manual_policy_round_trip_preserves_explicit_fallback_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.json"
            prefs = ModelPreferences.default()
            prefs.preferred_model = "cheap"
            prefs.allow_provider_fallback = True
            prefs.save(path)
            loaded = ModelPreferences.load(path)
            self.assertEqual(loaded.selection_mode, "manual")
            self.assertTrue(loaded.allow_provider_fallback)


if __name__ == "__main__":
    unittest.main()
