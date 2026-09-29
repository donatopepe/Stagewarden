from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewarden.config import AgentConfig
from stagewarden.executor import Executor
from stagewarden.memory import MemoryStore
from stagewarden.router import ModelRouter


class DummyHandoff:
    def execute(self, command: str):  # noqa: ANN001
        raise AssertionError("not used")


class ParserTests(unittest.TestCase):
    def build_executor(self) -> Executor:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        return Executor(
            config=AgentConfig(workspace_root=Path(tmp_dir.name)),
            router=ModelRouter(),
            handoff=DummyHandoff(),
            memory=MemoryStore(),
        )

    def test_parser_accepts_fenced_json(self) -> None:
        executor = self.build_executor()
        result = executor._parse_model_json(
            '```json\n{"summary":"ok","action":{"type":"complete","message":"done"}}\n```'
        )
        self.assertTrue(result["ok"])

    def test_parser_extracts_json_from_wrapped_text(self) -> None:
        executor = self.build_executor()
        raw = 'Thoughts first\n{"summary":"ok","action":{"type":"complete","message":"done"}}\ntrailing note'
        result = executor._parse_model_json(raw)
        self.assertTrue(result["ok"])

    NON_OBJECT_PAYLOADS = ("[]", '"hello"', "42", "true", "null", "[[1,2]]")

    def test_main_parser_fails_closed_on_non_object_payload(self) -> None:
        executor = self.build_executor()
        for raw in self.NON_OBJECT_PAYLOADS:
            with self.subTest(raw=raw):
                try:
                    result = executor._parse_model_json(raw)
                except Exception as exc:  # noqa: BLE001 - the defect under test
                    self.fail(f"_parse_model_json({raw!r}) raised {type(exc).__name__}: {exc}")
                self.assertFalse(result["ok"], f"{raw!r} must fail closed")
                self.assertIn("error", result)

    def test_critic_parser_fails_closed_on_non_object_payload(self) -> None:
        executor = self.build_executor()
        for raw in self.NON_OBJECT_PAYLOADS:
            with self.subTest(raw=raw):
                try:
                    result = executor._parse_devil_advocate_json(raw)
                except Exception as exc:  # noqa: BLE001 - the defect under test
                    self.fail(
                        f"_parse_devil_advocate_json({raw!r}) raised "
                        f"{type(exc).__name__}: {exc}"
                    )
                self.assertFalse(result["ok"], f"{raw!r} must fail closed")
                self.assertIn("error", result)

    def test_parser_recovers_object_wrapped_in_a_top_level_array(self) -> None:
        """A non-object wrapper must not discard a well-formed object inside it."""
        executor = self.build_executor()
        main = executor._parse_model_json(
            '[{"summary":"ok","action":{"type":"complete","message":"done"}}]'
        )
        self.assertTrue(main["ok"], main.get("error"))
        self.assertEqual(main["action"]["type"], "complete")
        critic = executor._parse_devil_advocate_json('[{"verdict":"accept"}]')
        self.assertTrue(critic["ok"], critic.get("error"))
        self.assertEqual(critic["payload"]["verdict"], "accept")

    def test_parser_still_accepts_fenced_and_prose_wrapped_objects(self) -> None:
        executor = self.build_executor()
        payload = '{"summary":"ok","action":{"type":"complete","message":"done"}}'
        for label, raw in (
            ("fenced", f"```json\n{payload}\n```"),
            ("prose", f"Sure! Here you go:\n{payload}\nHope that helps."),
        ):
            with self.subTest(label=label):
                self.assertTrue(executor._parse_model_json(raw)["ok"])
        critic_payload = '{"verdict":"accept","summary":"fine"}'
        for label, raw in (
            ("fenced", f"```json\n{critic_payload}\n```"),
            ("prose", f"Review:\n{critic_payload}\nDone."),
        ):
            with self.subTest(label=f"critic-{label}"):
                self.assertTrue(executor._parse_devil_advocate_json(raw)["ok"])


if __name__ == "__main__":
    unittest.main()
