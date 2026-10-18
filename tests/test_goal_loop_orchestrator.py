"""Unit tests for goal loop orchestrator pi execution and parsing."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from stagewarden.config import AgentConfig
from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator, NodeState
from stagewarden.goal_loop_views import build_goal_loop_report
from stagewarden.node_knowledge import NodeKnowledgeStore


class GoalLoopPiExecutionTests(unittest.TestCase):
    """Test _pi_execution JSON parsing with mocked subprocess."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.config = AgentConfig(workspace_root=self.tmp_dir)

    def _build_result(self, stdout: str, returncode: int = 0,
                      stderr: str = "") -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["pi", "--print", "--no-tools", "--no-session", "@test.md"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def _pi_exec(self, stdout: str, task: str = "pi probe", returncode: int = 0,
                 stderr: str = ""):
        """Call the REAL GoalLoopOrchestrator._pi_execution with a mocked pi process.

        Tests must exercise the production parser, not a copy of it: the earlier
        test_pi_execution_* cases re-implemented the ANSI regex and json.loads
        inline, so a real uncaught crash in _pi_execution went unnoticed for 150+
        cycles.
        """
        orchestrator = GoalLoopOrchestrator(
            AgentConfig(workspace_root=self.tmp_dir / task.replace(" ", "_")),
            task,
            execution_mode="pi",
            json_mode=True,
        )
        self.addCleanup(lambda: orchestrator.knowledge.close())
        node = orchestrator.nodes["root.scope"]
        completed = self._build_result(stdout, returncode=returncode, stderr=stderr)
        with patch("stagewarden.goal_loop_orchestrator.subprocess.run", return_value=completed), \
                patch("stagewarden.goal_loop_orchestrator.shutil.which", return_value="/usr/bin/pi"):
            return orchestrator._pi_execution(node)

    def test_token_budget_environment_unset_uses_defaults(self) -> None:
        keys = (
            "STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS",
            "STAGEWARDEN_GOAL_LOOP_OUTPUT_TOKENS",
            "STAGEWARDEN_GOAL_LOOP_OUTPUT_RESERVE",
            "STAGEWARDEN_GOAL_LOOP_CONTEXT_MARGIN",
        )
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=False):
            for key in keys:
                os.environ.pop(key, None)
            orchestrator = GoalLoopOrchestrator(
                AgentConfig(workspace_root=Path(tmp)), "default token budgets",
                execution_mode="mock", json_mode=True,
            )
            self.addCleanup(lambda: orchestrator.knowledge.close())
            self.assertEqual(orchestrator.nodes["root.scope"].context_budget["reserved_output"], 2048)
            self.assertEqual(orchestrator.nodes["root.scope"].context_budget["safety_margin"], 512)

    def test_budget_metadata_labels_counter_on_both_prompt_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {
                "STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "10000",
                "STAGEWARDEN_GOAL_LOOP_OUTPUT_RESERVE": "256",
                "STAGEWARDEN_GOAL_LOOP_CONTEXT_MARGIN": "128",
            }):
                orchestrator = GoalLoopOrchestrator(
                    AgentConfig(workspace_root=Path(tmp)), "counter metadata",
                    execution_mode="mock", json_mode=True,
                )
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            self.assertEqual(node.context_budget["token_counter"], "utf8_byte_upper_bound_v1")
            self.assertEqual(node.context_budget["accounting_unit"], "utf8_bytes_upper_bound_not_provider_tokens")
            self.assertGreater(node.context_budget["available_input"], 0)
            packet = orchestrator._build_work_packet(node)
            self.assertEqual(packet["context_budget"]["token_counter"], "utf8_byte_upper_bound_v1")
            self.assertEqual(packet["context_budget"]["accounting_unit"], "utf8_bytes_upper_bound_not_provider_tokens")
            self.assertEqual(packet["context_budget"]["available_input"], node.context_budget["available_input"])
            self.assertEqual(
                orchestrator._estimate_tokens("é🙂"),
                len("é🙂".encode("utf-8")),
            )

    def test_invalid_token_budget_environment_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for key, value in (
                ("STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS", "0"),
                ("STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS", " "),
                ("STAGEWARDEN_GOAL_LOOP_OUTPUT_TOKENS", "-1"),
                ("STAGEWARDEN_GOAL_LOOP_OUTPUT_TOKENS", ""),
                ("STAGEWARDEN_GOAL_LOOP_OUTPUT_RESERVE", "not-number"),
                ("STAGEWARDEN_GOAL_LOOP_OUTPUT_RESERVE", "   "),
                ("STAGEWARDEN_GOAL_LOOP_CONTEXT_MARGIN", "2048.0"),
                ("STAGEWARDEN_GOAL_LOOP_CONTEXT_MARGIN", ""),
            ):
                with self.subTest(key=key, value=value), patch.dict(os.environ, {key: value}):
                    with self.assertRaisesRegex(ValueError, key):
                        GoalLoopOrchestrator(
                            AgentConfig(workspace_root=Path(tmp) / key),
                            "invalid budget", execution_mode="mock", json_mode=True,
                        )

    def test_final_prompt_budget_includes_assigned_skills_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills = root / ".stagewarden" / "skills"
            skills.mkdir(parents=True)
            (skills / "large" / "SKILL.md").parent.mkdir(parents=True)
            (skills / "large" / "SKILL.md").write_text(
                "---\nname: large\ndescription: oversized skill\n---\n" + "skill requirement " * 3500,
                encoding="utf-8",
            )
            (root / ".stagewarden" / "goal_loop_skills.json").write_text(
                json.dumps({"root.scope": ["large"]}), encoding="utf-8"
            )
            from stagewarden.goal_loop_views import load_node_skill_assignments, resolve_node_skills
            self.assertEqual(load_node_skill_assignments(root), {"root.scope": ["large"]})
            self.assertEqual(len(resolve_node_skills(["large"], [skills])[0][0]["content"]), 63_049)
            with patch.dict(os.environ, {
                "STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "5000",
                "STAGEWARDEN_GOAL_LOOP_OUTPUT_RESERVE": "256",
                "STAGEWARDEN_GOAL_LOOP_CONTEXT_MARGIN": "128",
            }, clear=False):
                with self.assertRaisesRegex(ValueError, "including custom instructions/skills"):
                    GoalLoopOrchestrator(
                        AgentConfig(workspace_root=root), "budget test",
                        execution_mode="mock", json_mode=True,
                    )

    def test_node_prompt_char_cap_ignores_invalid_available_input(self) -> None:
        orchestrator = GoalLoopOrchestrator(self.config, "node prompt cap", execution_mode="mock", json_mode=True)
        self.addCleanup(lambda: orchestrator.knowledge.close())
        node = orchestrator.nodes["root.scope"]
        for value in (-1, True, 1.5, "64", None):
            node.context_budget = {"available_input": value}
            self.assertEqual(orchestrator._node_prompt_char_cap(node), 12000)
        node.context_budget = {"available_input": 64}
        self.assertEqual(orchestrator._node_prompt_char_cap(node), 64)

    def test_unknown_budget_records_node_context_omission(self) -> None:
        """Without a known input budget the node context is omitted; the omission must be auditable."""
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "unknown budget omission", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS", None)
                prompt = orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            self.assertNotIn("Node-local compacted context (untrusted data", prompt)
            events = orchestrator.events.read(event="node_context_omitted_unknown_budget")
            self.assertEqual(len(events), 1)
            detail = events[0]["details"]
            self.assertEqual(detail["stored_utf8_bytes"], len(original.encode("utf-8")))
            self.assertEqual(detail["section"], "node_prompt_budget")

    def test_unknown_budget_without_context_records_no_omission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "unknown budget empty", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS", None)
                orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            self.assertEqual(orchestrator.events.read(event="node_context_omitted_unknown_budget"), [])

    def test_known_budget_records_no_unknown_omission(self) -> None:
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "known budget injected", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "10000"}):
                prompt = orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            self.assertIn("Node-local compacted context (untrusted data", prompt)
            self.assertEqual(orchestrator.events.read(event="node_context_omitted_unknown_budget"), [])

    def test_prompt_carries_node_context_exactly_once(self) -> None:
        """The WorkPacket JSON must not duplicate the framed node-local context section."""
        context = "[execution] " + "x" * 150
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "prompt dedup", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = context
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "10000"}):
                prompt = orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            self.assertEqual(prompt.count(context), 1)
            self.assertIn("Node-local compacted context (untrusted data", prompt)
            self.assertEqual(orchestrator._build_work_packet(node)["compacted_context"], node.compacted_context)

    def test_prompt_dedup_frees_node_context_budget(self) -> None:
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "prompt dedup budget", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "10000"}):
                prompt = orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            marker = "Node-local compacted context (untrusted data"
            start = prompt.index(marker)
            body = prompt[start:].split("\n\nNode UUID:", 1)[0]
            section = body.split("\n", 1)[1] if "\n" in body else ""
            self.assertGreaterEqual(len(section.encode("utf-8")), 135)

    def test_semantic_compaction_rejects_duplicate_labels_from_mutating_mapping(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic classifier mutation", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class MutatingClassifier:
            backend = "test"
            def classify(self, request):
                request.labels = ("section_0", "section_0")
                return DecisionResult("section_0", 1.0, "test", "generic", {"section_0": 1.0})

        orchestrator._decision_classifier = MutatingClassifier()
        expected = GoalLoopOrchestrator._compact_node_text(text, 100)
        self.assertEqual(orchestrator._semantic_compact_node_text(text, 100), expected)

    def test_semantic_compaction_preserves_original_keyboard_interrupt_from_classifier(self) -> None:
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic classifier original interrupt", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class InterruptingClassifier:
            backend = "test"
            def classify(self, request):
                raise KeyboardInterrupt("classifier interrupt")

        class InterruptingFallback(GoalLoopOrchestrator):
            @staticmethod
            def _compact_node_text(text, max_tokens):
                raise KeyboardInterrupt("fallback interrupt")

        interrupting = InterruptingFallback(self.config, "semantic classifier original interrupt", execution_mode="mock", json_mode=True)
        self.addCleanup(interrupting.knowledge.close)
        interrupting._decision_classifier = InterruptingClassifier()
        with self.assertRaisesRegex(KeyboardInterrupt, "classifier interrupt"):
            interrupting._semantic_compact_node_text(text, 100)

    def test_semantic_compaction_does_not_swallow_keyboard_interrupt_from_fallback(self) -> None:
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic fallback keyboard interrupt", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class InterruptingClassifier:
            backend = "test"
            def classify(self, request):
                raise RuntimeError("classifier unavailable")

        orchestrator._decision_classifier = InterruptingClassifier()
        with patch.object(GoalLoopOrchestrator, "_compact_node_text", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                orchestrator._semantic_compact_node_text(text, 100)

    def test_semantic_compaction_propagates_generator_exit_from_classifier(self) -> None:
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic classifier generator exit", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class ExitingClassifier:
            backend = "test"
            def classify(self, request):
                raise GeneratorExit()

        orchestrator._decision_classifier = ExitingClassifier()
        with self.assertRaises(GeneratorExit):
            orchestrator._semantic_compact_node_text(text, 100)

    def test_semantic_compaction_propagates_keyboard_interrupt_from_classifier(self) -> None:
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic classifier keyboard interrupt", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class InterruptingClassifier:
            backend = "test"
            def classify(self, request):
                raise KeyboardInterrupt()

        orchestrator._decision_classifier = InterruptingClassifier()
        with self.assertRaises(KeyboardInterrupt):
            orchestrator._semantic_compact_node_text(text, 100)

    def test_semantic_compaction_propagates_system_exit_from_classifier(self) -> None:
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic classifier system exit", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class ExitingClassifier:
            backend = "test"
            def classify(self, request):
                raise SystemExit("backend requested process exit")

        orchestrator._decision_classifier = ExitingClassifier()
        with self.assertRaisesRegex(SystemExit, "backend requested process exit"):
            orchestrator._semantic_compact_node_text(text, 100)

    def test_semantic_compaction_falls_back_if_classifier_returns_none(self) -> None:
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic classifier none", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class EmptyClassifier:
            backend = "test"
            def classify(self, request):
                return None

        orchestrator._decision_classifier = EmptyClassifier()
        expected = GoalLoopOrchestrator._compact_node_text(text, 100)
        self.assertEqual(orchestrator._semantic_compact_node_text(text, 100), expected)

    def test_semantic_compaction_falls_back_if_classifier_omits_required_fields(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic missing fields", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class PartialResult:
            label = "section_0"

        class Fake:
            backend = "test"
            def classify(self, request):
                return PartialResult()

        orchestrator._decision_classifier = Fake()
        expected = GoalLoopOrchestrator._compact_node_text(text, 100)
        self.assertEqual(orchestrator._semantic_compact_node_text(text, 100), expected)

    def test_semantic_compaction_rejects_classifier_result_with_wrong_container_type(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic distribution container", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class Fake:
            backend = "test"
            def classify(self, request):
                return DecisionResult("section_0", 1.0, "test", "generic", [("section_0", 1.0)])

        orchestrator._decision_classifier = Fake()
        expected = GoalLoopOrchestrator._compact_node_text(text, 100)
        self.assertEqual(orchestrator._semantic_compact_node_text(text, 100), expected)

    def test_semantic_compaction_fallbacks_on_distribution_mutating_itself_during_sum(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic distribution sum mutation", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class MutatingFloat(float):
            def __new__(cls, value, mapping):
                obj = super().__new__(cls, value)
                obj.mapping = mapping
                return obj
            def __add__(self, other):
                self.mapping.clear()
                return super().__add__(other)

        class Fake:
            backend = "test"
            def classify(self, request):
                distribution = {"section_0": 0.8, "section_1": 0.2}
                distribution["section_0"] = MutatingFloat(0.8, distribution)
                return DecisionResult("section_0", 1.0, "test", "generic", distribution)

        orchestrator._decision_classifier = Fake()
        expected = GoalLoopOrchestrator._compact_node_text(text, 100)
        self.assertEqual(orchestrator._semantic_compact_node_text(text, 100), expected)

    def test_semantic_compaction_rejects_dict_mutation_during_validation(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "[invariant] Preserve node boundaries.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic mapping mutation", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class MutatingDict(dict):
            def values(self):
                self.clear()
                return [1.0, 0.0]

        class Fake:
            backend = "test"
            def classify(self, request):
                return DecisionResult("section_0", 1.0, "test", "generic", MutatingDict({"section_0": 1.0, "section_1": 0.0}))

        orchestrator._decision_classifier = Fake()
        expected = GoalLoopOrchestrator._compact_node_text(text, 100)
        self.assertEqual(orchestrator._semantic_compact_node_text(text, 100), expected)

    def test_semantic_compaction_rejects_distribution_dict_subclass(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "[invariant] Keep node boundary.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic distribution mapping", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class OddDict(dict):
            def values(self):
                return [1.0, 0.0]
            def get(self, key, default=None):
                return 1.0

        class Fake:
            backend = "test"
            def classify(self, request):
                return DecisionResult("section_0", 1.0, "test", "generic", OddDict({"section_0": 0.5, "section_1": 0.5}))

        orchestrator._decision_classifier = Fake()
        expected = GoalLoopOrchestrator._compact_node_text(text, 100)
        self.assertEqual(orchestrator._semantic_compact_node_text(text, 100), expected)

    def test_semantic_compaction_rejects_float_subclass_with_nan_coercion(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "History.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic float subclass", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class WeirdFloat(float):
            def __float__(self):
                return float("nan")

        class Fake:
            backend = "test"
            def classify(self, request):
                return DecisionResult("section_0", 1.0, "test", "generic", {
                    "section_0": WeirdFloat(1.0), "section_1": 0.0,
                })

        orchestrator._decision_classifier = Fake()
        expected = GoalLoopOrchestrator._compact_node_text(text, 100)
        self.assertEqual(orchestrator._semantic_compact_node_text(text, 100), expected)

    def test_semantic_compaction_rejects_custom_integer_subclasses_in_distribution(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "[invariant] Preserve node scope.\nUseful detail.\n" + "Historical note.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic numeric subclass", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class StrangeInt(int):
            def __float__(self):
                return 0.0

        class Fake:
            backend = "test"
            def classify(self, request):
                return DecisionResult("section_0", 1.0, "test", "generic", {
                    "section_0": StrangeInt(1), "section_1": 0,
                })

        orchestrator._decision_classifier = Fake()
        expected = GoalLoopOrchestrator._compact_node_text(text, 100)
        self.assertEqual(orchestrator._semantic_compact_node_text(text, 100), expected)

    def test_semantic_compaction_uses_generic_classifier_and_preserves_required_sections(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "[invariant] Never change provider routing.\n[acceptance_criteria] Keep v3 serial.\nRelevant: preserve node UUID.\n" + "Obsolete historical detail. " * 30
        orchestrator = GoalLoopOrchestrator(self.config, "semantic compact", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class KeepRequired:
            backend = "test"
            def classify(self, request):
                self.request = request
                return DecisionResult("section_0", 1.0, "test", "generic", {"section_0": 1.0, "section_1": 0.0})

        classifier = KeepRequired()
        orchestrator._decision_classifier = classifier
        compacted = orchestrator._semantic_compact_node_text(text, 220)
        self.assertIn("[invariant] Never change provider routing.", compacted)
        self.assertIn("[acceptance_criteria] Keep v3 serial.", compacted)
        self.assertIn("Relevant: preserve node UUID.", compacted)
        self.assertNotIn("Obsolete historical detail.", compacted)
        self.assertEqual(classifier.request.labels, ("section_0", "section_1"))
        self.assertLessEqual(len(compacted.encode("utf-8")), 220)

    def test_semantic_compaction_allows_float_rounding_but_rejects_material_sum_error(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "[invariant] Keep node scope.\nFirst optional.\nSecond optional.\n" + "Historical detail.\n" * 10
        orchestrator = GoalLoopOrchestrator(self.config, "semantic distribution precision", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class Distribution:
            backend = "test"
            def __init__(self, values, label="section_0"): self.values, self.label = values, label
            def classify(self, request):
                self.request = request
                return DecisionResult(self.label, 0.8, "test", "generic", self.values)

        original = GoalLoopOrchestrator._compact_node_text(text, 120)
        classifier = Distribution({"section_0": 0.8, "section_1": 0.19999999999999998}, label="section_0")
        orchestrator._decision_classifier = classifier
        accepted = orchestrator._semantic_compact_node_text(text, 120)
        self.assertTrue(hasattr(classifier, "request"))
        classifier = Distribution({"section_0": 0.8, "section_1": 0.199})
        orchestrator._decision_classifier = classifier
        rejected = orchestrator._semantic_compact_node_text(text, 120)
        self.assertEqual(rejected, original)
        self.assertTrue(hasattr(classifier, "request"))
        self.assertEqual(classifier.request.labels, tuple(f"section_{index}" for index in range(12)))

    def test_semantic_compaction_never_offers_indented_structural_lines_as_optional(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "  [invariant] Keep node UUID.\nOptional detail.\n" + "Historical note.\n" * 11
        orchestrator = GoalLoopOrchestrator(self.config, "semantic structural filtering", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class Capture:
            backend = "test"
            def classify(self, request):
                self.request = request
                distribution = {label: (1.0 if label == "section_0" else 0.0) for label in request.labels}
                return DecisionResult("section_0", 1.0, "test", "generic", distribution)

        classifier = Capture()
        orchestrator._decision_classifier = classifier
        compacted = orchestrator._semantic_compact_node_text(text, 220)
        offered = json.loads(classifier.request.text)["node_context_sections"]
        self.assertEqual(offered, ["Optional detail."] + ["Historical note."] * 11)
        self.assertTrue(any(line.lstrip().startswith("[invariant]") for line in compacted.splitlines()))

    def test_semantic_compaction_rejects_low_confidence_and_malformed_distribution(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        text = "[invariant] Keep node scope.\nUseful note.\n" + "Historical detail. " * 30
        orchestrator = GoalLoopOrchestrator(self.config, "semantic confidence", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class Ambiguous:
            backend = "test"
            def __init__(self, confidence, distribution):
                self.confidence, self.distribution = confidence, distribution
            def classify(self, request):
                return DecisionResult("section_0", self.confidence, "test", "generic", self.distribution)

        baseline = GoalLoopOrchestrator._compact_node_text(text, 120)
        for fake in (Ambiguous(0.51, {"section_0": 0.51, "section_1": 0.49}),
                     Ambiguous(0.99, {"section_0": 0.6, "section_1": 0.4}),
                     Ambiguous(0.99, {"section_0": 1.0}),
                     Ambiguous(float("nan"), {"section_0": 1.0, "section_1": 0.0}),
                     Ambiguous(0.99, {"section_0": float("nan"), "section_1": 0.0}),
                     Ambiguous(True, {"section_0": 1.0, "section_1": 0.0}),
                     Ambiguous(1.0, {"section_0": True, "section_1": False}),
                     Ambiguous("0.99", {"section_0": 1.0, "section_1": 0.0}),
                     Ambiguous(0.99, {"section_0": "1.0", "section_1": 0.0}),
                     Ambiguous(10**10000, {"section_0": 1.0, "section_1": 0.0}),
                     Ambiguous(0.99, {"section_0": 10**10000, "section_1": 0.0})):
            with self.subTest(confidence=fake.confidence, distribution=fake.distribution):
                orchestrator._decision_classifier = fake
                self.assertEqual(orchestrator._semantic_compact_node_text(text, 120), baseline)

    def test_semantic_compaction_falls_back_on_invalid_classifier_output(self) -> None:
        text = "[invariant] Preserve node boundary.\n" + "ordinary detail. " * 30
        orchestrator = GoalLoopOrchestrator(self.config, "semantic fallback", execution_mode="mock", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)

        class Invalid:
            backend = "test"
            def classify(self, request):
                raise ValueError("invalid output")

        orchestrator._decision_classifier = Invalid()
        result = orchestrator._semantic_compact_node_text(text, 100)
        self.assertEqual(result, GoalLoopOrchestrator._compact_node_text(text, 100))
        self.assertLessEqual(len(result.encode("utf-8")), 100)

    def test_compaction_routes_structural_body_into_excerpt_budget(self) -> None:
        """An over-long structural line must not collapse the whole snapshot to its label."""
        text = "[execution] " + "x" * 4000
        compacted = GoalLoopOrchestrator._compact_node_text(text, 1000)
        self.assertIn("[execution]", compacted)
        self.assertIn("context auto-compacted", compacted)
        self.assertLessEqual(len(compacted.encode("utf-8")), 1000)
        self.assertGreaterEqual(len(compacted.encode("utf-8")), 800)

    def test_compaction_utilisation_scales_with_cap(self) -> None:
        text = "[execution] " + "x" * 4000
        for cap, floor in ((1000, 800), (4000, 3200)):
            with self.subTest(cap=cap):
                compacted = GoalLoopOrchestrator._compact_node_text(text, cap)
                self.assertLessEqual(len(compacted.encode("utf-8")), cap)
                self.assertGreaterEqual(len(compacted.encode("utf-8")), floor)

    def test_compaction_keeps_structural_labels_while_using_excerpts(self) -> None:
        text = "[execution] " + "y" * 3000 + "\n\nordinary prose " * 20 + "\n[acceptance_criteria] keep me"
        compacted = GoalLoopOrchestrator._compact_node_text(text, 1000)
        self.assertIn("[execution]", compacted)
        self.assertIn("[acceptance_criteria]", compacted)
        self.assertLessEqual(len(compacted.encode("utf-8")), 1000)
        only = GoalLoopOrchestrator._compact_node_text("[acceptance_criteria] " + "z" * 3000, 800)
        self.assertIn("[acceptance_criteria]", only)
        self.assertLessEqual(len(only.encode("utf-8")), 800)
        self.assertGreaterEqual(len(only.encode("utf-8")), 600)

    def test_budget_estimator_uses_utf8_bytes_and_compaction_respects_byte_cap(self) -> None:
        orchestrator = GoalLoopOrchestrator(self.config, "budget estimator", execution_mode="mock", json_mode=True)
        self.addCleanup(lambda: orchestrator.knowledge.close())
        self.assertEqual(orchestrator._estimate_tokens("aé🙂"), len("aé🙂".encode("utf-8")))
        compacted = GoalLoopOrchestrator._compact_node_text("🙂" * 1000, 300)
        self.assertLessEqual(len(compacted.encode("utf-8")), 300)
        self.assertIn("context auto-compacted", compacted)
        self.assertEqual(
            orchestrator._estimate_tokens(compacted),
            len(compacted.encode("utf-8")),
        )
        for byte_cap in (1, 8, 10, 100, 300):
            with self.subTest(byte_cap=byte_cap):
                compacted = GoalLoopOrchestrator._compact_node_text("🙂é\\n" * 100, byte_cap)
                self.assertLessEqual(len(compacted.encode("utf-8")), byte_cap)
        # For caps just above marker size, output must remain bounded and retain marker when possible.
        for byte_cap in range(75, 100):
            compacted = GoalLoopOrchestrator._compact_node_text("a" * 1000, byte_cap)
            self.assertLessEqual(len(compacted.encode("utf-8")), byte_cap)
            self.assertIn("context auto-compacted", compacted)
        # Structural lines survive bounded compaction instead of being clipped by head/tail slicing.
        required = "[execution] keep task invariant\n" + ("x" * 1000) + "\n[acceptance_criteria] verify output"
        required_compacted = GoalLoopOrchestrator._compact_node_text(required, 300)
        self.assertLessEqual(len(required_compacted.encode("utf-8")), 300)
        self.assertIn("[execution] keep task invariant", required_compacted)
        self.assertIn("[acceptance_criteria] verify output", required_compacted)
        self.assertIn("context auto-compacted", required_compacted)
        self.assertTrue("xxxx" in required_compacted or "output" in required_compacted)
        too_small = GoalLoopOrchestrator._compact_node_text(
            "[execution] " + ("x" * 1000) + "\n[acceptance_criteria] required", 100,
        )
        self.assertLessEqual(len(too_small.encode("utf-8")), 100)
        self.assertIn("[execution]", too_small)
        self.assertIn("context auto-compacted", too_small)
        # Under marker size, preserve available input prefix instead of dropping all context.
        tiny = GoalLoopOrchestrator._compact_node_text("🙂abcdef", 4)
        self.assertEqual(tiny, "🙂")
        # Exercise every sub-marker cap: result must never exceed byte ceiling.
        mixed = "🙂é\\n" * 100
        for byte_cap in range(1, 80):
            compacted = GoalLoopOrchestrator._compact_node_text(mixed, byte_cap)
            self.assertLessEqual(len(compacted.encode("utf-8")), byte_cap)

    def test_token_counter_is_pluggable_and_unknown_specs_fail_closed(self) -> None:
        spec = "stagewarden.memory_context:character_counter"
        with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_TOKEN_COUNTER": spec}):
            plugged = GoalLoopOrchestrator(self.config, "plugged counter", execution_mode="mock", json_mode=True)
        self.addCleanup(lambda: plugged.knowledge.close())
        self.assertEqual(plugged._token_counter_name, spec)
        self.assertEqual(plugged._accounting_unit, "external_token_counter_not_provider_verified")
        self.assertEqual(plugged._estimate_tokens("ééé"), 3)
        self.assertEqual(plugged.nodes["root.scope"].context_budget["token_counter"], spec)
        self.assertEqual(
            plugged.nodes["root.scope"].context_budget["accounting_unit"],
            "external_token_counter_not_provider_verified",
        )
        for bad in ("bogus", "does.not.exist:counter", "stagewarden.memory_context:missing_attribute"):
            with self.subTest(spec=bad), patch.dict(
                os.environ, {"STAGEWARDEN_GOAL_LOOP_TOKEN_COUNTER": bad}
            ), self.assertRaises(ValueError):
                GoalLoopOrchestrator(self.config, "bad counter", execution_mode="mock", json_mode=True)

    def test_node_context_codemode_is_uuid_scoped_and_compacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "context test", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            root = orchestrator.nodes["root.scope"]
            other = orchestrator.nodes[next(node_id for node_id in orchestrator.nodes if node_id != "root.scope")]
            first = orchestrator.codemode_context(root.node_id, "append", text="private root fact", expected_revision=0)
            self.assertTrue(first["ok"])
            self.assertEqual(first["node_uuid"], root.node_uuid)
            stale = orchestrator.codemode_context(root.node_id, "append", text="stale write", expected_revision=0)
            self.assertFalse(stale["ok"])
            self.assertEqual(stale["error"], "context revision conflict")
            self.assertEqual(stale["current_revision"], root.context_revision)
            self.assertNotIn("stale write", root.compacted_context)
            self.assertFalse(orchestrator.codemode_context(root.node_id, "append", text="bad revision", expected_revision=True)["ok"])
            self.assertFalse(orchestrator.codemode_context(root.node_id, "append", text=None)["ok"])
            self.assertFalse(orchestrator.codemode_context(root.node_id, None)["ok"])
            revision_before_oversize = root.context_revision
            root.context_budget["available_input"] = 128
            oversize = orchestrator.codemode_context(
                root.node_id, "append", text="x" * 129, expected_revision=revision_before_oversize,
            )
            self.assertFalse(oversize["ok"])
            self.assertEqual(oversize["error"], "context append exceeds node byte budget")
            self.assertEqual(root.context_revision, revision_before_oversize)
            root.context_budget["available_input"] = 0
            zero_budget = orchestrator.codemode_context(
                root.node_id, "append", text="x", expected_revision=revision_before_oversize,
            )
            self.assertFalse(zero_budget["ok"])
            self.assertEqual(zero_budget["max_append_bytes"], 0)
            self.assertEqual(root.context_revision, revision_before_oversize)
            surrogate = orchestrator.codemode_context(
                root.node_id, "append", text="\ud800", expected_revision=revision_before_oversize,
            )
            self.assertFalse(surrogate["ok"])
            self.assertEqual(surrogate["error"], "context append must contain valid UTF-8 text")
            self.assertEqual(root.context_revision, revision_before_oversize)
            root.context_budget["available_input"] = True
            boolean_budget = orchestrator.codemode_context(
                root.node_id, "append", text="b" * 12001, expected_revision=revision_before_oversize,
            )
            self.assertFalse(boolean_budget["ok"])
            self.assertEqual(boolean_budget["max_append_bytes"], 12000)
            root.context_budget["available_input"] = -1
            negative_budget = orchestrator.codemode_context(
                root.node_id, "append", text="n" * 12001, expected_revision=revision_before_oversize,
            )
            self.assertFalse(negative_budget["ok"])
            self.assertEqual(negative_budget["max_append_bytes"], 12000)
            root.context_budget["available_input"] = True
            root.compacted_context = "a" * 127
            compacted_boolean_budget = orchestrator._append_node_context(root, "test", "b" * 2)
            self.assertLessEqual(len(compacted_boolean_budget.encode("utf-8")), 12000)
            root.context_budget["available_input"] = None
            root.compacted_context = "private root fact"
            root.context_revision = first["revision"]
            self.assertIn("private root fact", orchestrator.codemode_context(root.node_id, "read")["context"])
            stale_read = orchestrator.codemode_context(root.node_id, "read", expected_revision=0)
            self.assertFalse(stale_read["ok"])
            self.assertEqual(stale_read["current_revision"], root.context_revision)
            current_read = orchestrator.codemode_context(root.node_id, "read", expected_revision=first["revision"])
            self.assertTrue(current_read["ok"])
            saved = orchestrator.knowledge.search("private root fact", node_id=root.node_id, namespace="context")
            self.assertTrue(saved)
            self.assertNotIn("private root fact", orchestrator.codemode_context(other.node_id, "read")["context"])
            before = root.context_revision
            orchestrator._append_node_context(root, "test", "long " * 10000)
            self.assertGreater(root.context_revision, before)
            self.assertNotIn("private root fact", other.compacted_context)
            self.assertFalse(orchestrator.codemode_context(root.node_id, "eval", text="__import__('os').system('true')")["ok"])

    def test_node_context_audit_failure_after_commit_keeps_memory_aligned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "audit failure", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            original_append = orchestrator.events.append
            def fail_updated_event(event, **kwargs):
                if event == "node_context_updated":
                    raise OSError("audit disk failure")
                return original_append(event, **kwargs)
            orchestrator.events.append = fail_updated_event
            result = orchestrator.codemode_context(node.node_id, "append", text="durable note", expected_revision=0)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "context persisted but audit failed: OSError")
            self.assertEqual(result["revision"], 1)
            self.assertEqual(node.context_revision, 1)
            durable = orchestrator.knowledge.get_context_revision(
                tree_id="goal-loop", node_id=node.node_id, node_uuid=node.node_uuid, revision=1,
            )
            self.assertEqual(node.compacted_context, durable)
            self.assertIn("durable note", node.compacted_context)
            self.assertTrue(orchestrator.knowledge.has_context_revision(
                tree_id="goal-loop", node_id=node.node_id, node_uuid=node.node_uuid, revision=1,
            ))

    def test_node_context_compaction_event_emitted_only_after_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "compact persistence", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.context_budget["available_input"] = 128
            original_record = orchestrator.knowledge.record_context
            def fail_record(**kwargs):
                raise OSError("disk failure")
            orchestrator.knowledge.record_context = fail_record
            result = orchestrator.codemode_context(node.node_id, "append", text="x" * 120, expected_revision=0)
            self.assertFalse(result["ok"])
            self.assertEqual(node.context_revision, 0)
            self.assertEqual(node.compacted_context, "")
            self.assertEqual(orchestrator.events.read(event="node_context_compacted"), [])
            self.assertEqual(orchestrator.events.read(event="node_context_updated"), [])
            orchestrator.knowledge.record_context = original_record

    def test_node_context_entries_use_real_newline_separators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "context separator", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            first = orchestrator._append_node_context(node, "test", "payload")
            self.assertEqual(first, "[test] payload")
            self.assertNotIn("\\n", first)
            second = orchestrator._append_node_context(node, "note", "second")
            self.assertEqual(second, "[test] payload\n\n[note] second")
            self.assertNotIn("\\n", second)
            self.assertEqual(second.split("\n"), ["[test] payload", "", "[note] second"])
            node.context_budget["available_input"] = 200
            orchestrator._append_node_context(node, "execution", "x" * 4000)
            self.assertNotIn("\\n", node.compacted_context)
            self.assertLessEqual(len(node.compacted_context.encode("utf-8")), 200)
            self.assertIn("[context auto-compacted", node.compacted_context)

    def test_codemode_read_reports_byte_size_cap_and_compaction_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "codemode read bytes", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            fresh = orchestrator.codemode_context(node.node_id, "read")
            self.assertTrue(fresh["ok"])
            self.assertEqual(fresh["context_utf8_bytes"], 0)
            self.assertIs(fresh["compacted"], False)
            self.assertEqual(fresh["max_bytes"], 12000)
            node.context_budget["available_input"] = 128
            orchestrator._append_node_context(node, "execution", "x" * 400)
            compacted = orchestrator.codemode_context(node.node_id, "read")
            self.assertIs(compacted["compacted"], True)
            self.assertEqual(compacted["max_bytes"], 128)
            self.assertEqual(compacted["context_utf8_bytes"], len(compacted["context"].encode("utf-8")))
            self.assertLessEqual(compacted["context_utf8_bytes"], 128)

    def test_codemode_read_reports_compaction_below_marker_size(self) -> None:
        """Compaction must be detectable even when the marker cannot fit inside the cap.

        Below the 73-byte marker the snapshot is truncated without a marker, so the
        persisted node flag (not content sniffing alone) carries the signal.
        """
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "codemode read small cap", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.context_budget["available_input"] = 64
            orchestrator._append_node_context(node, "execution", "x" * 400)
            read = orchestrator.codemode_context(node.node_id, "read")
            self.assertIs(read["compacted"], True)
            self.assertEqual(read["max_bytes"], 64)
            self.assertEqual(read["context_utf8_bytes"], 64)
            self.assertEqual(read["context_utf8_bytes"], len(read["context"].encode("utf-8")))

    def test_codemode_compaction_flag_survives_controlled_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=root), "codemode reopen", execution_mode="mock", json_mode=True)
            node = orchestrator.nodes["root.scope"]
            node.context_budget["available_input"] = 64
            orchestrator._append_node_context(node, "execution", "x" * 400)
            orchestrator._persist_node_capsule(node)
            node_uuid = node.node_uuid
            orchestrator.knowledge.close()
            reopened = GoalLoopOrchestrator(AgentConfig(workspace_root=root), "codemode reopen", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: reopened.knowledge.close())
            restored = reopened.nodes["root.scope"]
            self.assertEqual(restored.node_uuid, node_uuid)
            read = reopened.codemode_context(restored.node_id, "read")
            self.assertIs(read["compacted"], True)
            self.assertEqual(read["context_utf8_bytes"], len(read["context"].encode("utf-8")))

    def test_codemode_read_reports_omitted_bytes_for_compacted_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "omitted bytes", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            fresh = orchestrator.codemode_context(node.node_id, "read")
            self.assertEqual(fresh["omitted_utf8_bytes"], 0)
            node.context_budget["available_input"] = 64
            entry = "[execution] " + "x" * 400
            orchestrator._append_node_context(node, "execution", "x" * 400)
            read = orchestrator.codemode_context(node.node_id, "read")
            expected = len(entry.encode("utf-8")) - len(node.compacted_context.encode("utf-8"))
            self.assertGreater(expected, 0)
            self.assertEqual(read["omitted_utf8_bytes"], expected)

    def test_codemode_omitted_bytes_accumulate_and_survive_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=root), "omitted bytes reopen", execution_mode="mock", json_mode=True)
            node = orchestrator.nodes["root.scope"]
            node.context_budget["available_input"] = 64
            orchestrator._append_node_context(node, "execution", "x" * 400)
            first = orchestrator.codemode_context(node.node_id, "read")["omitted_utf8_bytes"]
            orchestrator._append_node_context(node, "execution", "y" * 400)
            second = orchestrator.codemode_context(node.node_id, "read")["omitted_utf8_bytes"]
            self.assertGreater(first, 0)
            self.assertGreater(second, first)
            orchestrator._persist_node_capsule(node)
            orchestrator.knowledge.close()
            reopened = GoalLoopOrchestrator(AgentConfig(workspace_root=root), "omitted bytes reopen", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: reopened.knowledge.close())
            read = reopened.codemode_context(reopened.nodes["root.scope"].node_id, "read")
            self.assertEqual(read["omitted_utf8_bytes"], second)

    def test_codemode_append_reports_compaction_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "append projection", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.context_budget["available_input"] = 64
            orchestrator.codemode_context(node.node_id, "append", text="a" * 20, expected_revision=0)
            appended = orchestrator.codemode_context(node.node_id, "append", text="b" * 30, expected_revision=1)
            self.assertTrue(appended["ok"])
            self.assertIs(appended["compacted"], True)
            self.assertGreater(appended["omitted_utf8_bytes"], 0)
            self.assertEqual(appended["max_bytes"], 64)
            self.assertEqual(appended["context_utf8_bytes"], len(node.compacted_context.encode("utf-8")))
            read = orchestrator.codemode_context(node.node_id, "read")
            self.assertEqual(appended["omitted_utf8_bytes"], read["omitted_utf8_bytes"])

    def test_codemode_append_over_cap_fails_closed_before_compaction(self) -> None:
        """A single append larger than the node cap is rejected; compaction only sees what fits."""
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "append over cap", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.context_budget["available_input"] = 64
            rejected = orchestrator.codemode_context(node.node_id, "append", text="y" * 400, expected_revision=0)
            self.assertFalse(rejected["ok"])
            self.assertEqual(rejected["error"], "context append exceeds node byte budget")
            self.assertEqual(rejected["max_append_bytes"], 64)
            self.assertEqual(rejected["provided_bytes"], 400)
            self.assertEqual(node.compacted_context, "")
            self.assertIs(node.context_compacted, False)
            self.assertEqual(node.context_omitted_bytes, 0)

    def test_codemode_append_without_compaction_reports_no_loss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "append no loss", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            appended = orchestrator.codemode_context(node.node_id, "append", text="plain note", expected_revision=0)
            self.assertIs(appended["compacted"], False)
            self.assertEqual(appended["omitted_utf8_bytes"], 0)
            self.assertEqual(appended["max_bytes"], 12000)
            self.assertEqual(appended["context_utf8_bytes"], len(node.compacted_context.encode("utf-8")))

    def test_prompt_path_compaction_is_accounted(self) -> None:
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "prompt compaction", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "6000"}):
                orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            expected = len(original.encode("utf-8")) - len(node.compacted_context.encode("utf-8"))
            self.assertGreater(expected, 0)
            self.assertIs(node.context_compacted, True)
            self.assertEqual(node.context_omitted_bytes, expected)
            events = [item for item in orchestrator.events.read(event="node_context_compacted") if item.get("details", {}).get("section") == "node_prompt_budget"]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["details"]["omitted_utf8_bytes"], expected)
            self.assertEqual(events[0]["details"]["original_utf8_bytes"] - events[0]["details"]["compacted_utf8_bytes"], expected)

    def test_prompt_path_without_compaction_leaves_accounting_untouched(self) -> None:
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "prompt no compaction", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "12000"}):
                orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            self.assertIs(node.context_compacted, False)
            self.assertEqual(node.context_omitted_bytes, 0)
            self.assertEqual(node.compacted_context, original)
            self.assertEqual([item for item in orchestrator.events.read(event="node_context_compacted") if item.get("details", {}).get("section") == "node_prompt_budget"], [])

    def test_read_projection_reflects_prompt_path_compaction(self) -> None:
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "prompt compaction read", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "6000"}):
                orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            read = orchestrator.codemode_context(node.node_id, "read")
            expected = len(original.encode("utf-8")) - len(node.compacted_context.encode("utf-8"))
            self.assertIs(read["compacted"], True)
            self.assertEqual(read["omitted_utf8_bytes"], expected)
            self.assertEqual(read["context_utf8_bytes"], len(read["context"].encode("utf-8")))

    def test_prompt_path_compaction_persists_context_revision(self) -> None:
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "prompt persist", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "6000"}):
                orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            self.assertGreater(node.context_revision, 0)
            stored = orchestrator.knowledge.get_context_revision(
                tree_id="goal-loop", node_id=node.node_id, node_uuid=node.node_uuid, revision=node.context_revision,
            )
            self.assertEqual(stored, node.compacted_context)
            self.assertTrue(orchestrator.knowledge.has_context_revision(
                tree_id="goal-loop", node_id=node.node_id, node_uuid=node.node_uuid, revision=node.context_revision,
            ))
            events = [item for item in orchestrator.events.read(event="node_context_compacted") if item.get("details", {}).get("section") == "node_prompt_budget"]
            self.assertEqual(len(events), 1)
            self.assertIs(events[0]["details"]["persisted"], True)

    def test_prompt_path_without_compaction_persists_nothing(self) -> None:
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "prompt no persist", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "12000"}):
                orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            self.assertEqual(node.context_revision, 0)
            self.assertEqual(node.compacted_context, original)
            self.assertFalse(orchestrator.knowledge.has_context_revision(
                tree_id="goal-loop", node_id=node.node_id, node_uuid=node.node_uuid, revision=0,
            ))
            self.assertEqual([item for item in orchestrator.events.read(event="node_context_compacted") if item.get("details", {}).get("section") == "node_prompt_budget"], [])

    def test_reopen_restores_prompt_path_compacted_context(self) -> None:
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=root), "prompt persist reopen", execution_mode="mock", json_mode=True)
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "6000"}):
                orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            orchestrator._persist_node_capsule(node)
            orchestrator.knowledge.close()
            reopened = GoalLoopOrchestrator(AgentConfig(workspace_root=root), "prompt persist reopen", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: reopened.knowledge.close())
            restored = reopened.nodes["root.scope"]
            stored = reopened.knowledge.get_context_revision(
                tree_id="goal-loop", node_id=restored.node_id, node_uuid=restored.node_uuid, revision=restored.context_revision,
            )
            self.assertIsNotNone(stored)
            self.assertEqual(restored.compacted_context, stored)

    def test_prompt_path_persist_failure_is_recorded_without_breaking_prompt(self) -> None:
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "prompt persist failure", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.object(orchestrator.knowledge, "record_context", side_effect=OSError("disk failure")):
                with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "6000"}):
                    prompt = orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            self.assertTrue(prompt)
            self.assertIs(node.context_compacted, True)
            self.assertEqual(node.context_revision, 0)
            events = [item for item in orchestrator.events.read(event="node_context_compacted") if item.get("details", {}).get("section") == "node_prompt_budget"]
            self.assertEqual(len(events), 1)
            self.assertIs(events[0]["details"]["persisted"], False)
            self.assertEqual(events[0]["details"]["persist_error"], "OSError")

    def test_append_context_snapshot_matches_its_durable_record(self) -> None:
        """The knowledge store strips content, so node state must be normalized the same way."""
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "append store parity", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.context_budget["available_input"] = 128
            orchestrator._append_node_context(node, "execution", "x" * 400)
            stored = orchestrator.knowledge.get_context_revision(
                tree_id="goal-loop", node_id=node.node_id, node_uuid=node.node_uuid, revision=node.context_revision,
            )
            self.assertIsNotNone(stored)
            self.assertEqual(node.compacted_context, stored)

    def test_prompt_assembly_truncation_is_recorded(self) -> None:
        """The model may receive less context than the durable record; that loss must be auditable."""
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "prompt assembly truncation", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "10000", "STAGEWARDEN_GOAL_LOOP_CONTEXT_MARGIN": "1500"}):
                orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            events = orchestrator.events.read(event="node_context_prompt_truncated")
            self.assertEqual(len(events), 1)
            detail = events[0]["details"]
            self.assertEqual(detail["section"], "node_prompt_assembly")
            self.assertEqual(detail["stored_utf8_bytes"], len(original.encode("utf-8")))
            self.assertLess(detail["prompt_utf8_bytes"], detail["stored_utf8_bytes"])
            self.assertEqual(detail["omitted_utf8_bytes"], detail["stored_utf8_bytes"] - detail["prompt_utf8_bytes"])

    def test_prompt_assembly_without_truncation_records_nothing(self) -> None:
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "prompt assembly intact", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "14000"}):
                prompt = orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            self.assertIn(original, prompt)
            self.assertEqual(orchestrator.events.read(event="node_context_prompt_truncated"), [])

    def test_prompt_assembly_truncation_leaves_durable_record_untouched(self) -> None:
        original = "[execution] " + "x" * 4000
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "prompt assembly ephemeral", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.compacted_context = original
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "10000", "STAGEWARDEN_GOAL_LOOP_CONTEXT_MARGIN": "1500"}):
                orchestrator._generate_node_prompt(orchestrator.blueprint["child_prompts"][0])
            read = orchestrator.codemode_context(node.node_id, "read")
            self.assertEqual(node.compacted_context, original)
            self.assertEqual(node.context_revision, 0)
            self.assertEqual(read["context_utf8_bytes"], len(original.encode("utf-8")))
            self.assertEqual(read["omitted_utf8_bytes"], 0)

    def test_codemode_read_reports_uncompacted_byte_size_as_chars_for_ascii(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "codemode read ascii", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            appended = orchestrator.codemode_context(node.node_id, "append", text="plain note", expected_revision=0)
            self.assertTrue(appended["ok"])
            read = orchestrator.codemode_context(node.node_id, "read")
            self.assertIs(read["compacted"], False)
            self.assertEqual(read["context_utf8_bytes"], len(read["context"].encode("utf-8")))
            self.assertEqual(read["context_utf8_bytes"], appended["context_utf8_bytes"])

    def test_codemode_append_reports_byte_exact_size_alongside_char_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "codemode append bytes", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            result = orchestrator.codemode_context(node.node_id, "append", text="àè" * 20, expected_revision=0)
            self.assertTrue(result["ok"])
            self.assertEqual(result["context_chars"], len(node.compacted_context))
            self.assertEqual(result["context_utf8_bytes"], len(node.compacted_context.encode("utf-8")))
            self.assertGreater(result["context_utf8_bytes"], result["context_chars"])

    def test_invalid_budget_compaction_event_reports_validated_fallback_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "invalid compact cap", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            for value in (-1, True, 1.5, "128"):
                node.context_budget["available_input"] = value
                node.compacted_context = ""
                orchestrator._append_node_context(node, "execution", "x" * 13000)
                events = orchestrator.events.read(event="node_context_compacted", node_id=node.node_id)
                self.assertTrue(events)
                self.assertEqual(events[-1]["details"]["cap_utf8_bytes"], 12000)

    def test_compaction_observability_reports_section_bytes_and_accounting_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "compact observability", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.context_budget["available_input"] = 128
            combined = orchestrator._append_node_context(node, "execution", "àè" * 60)
            self.assertTrue(combined)
            compacted = orchestrator.events.read(event="node_context_compacted")
            self.assertTrue(compacted)
            event = compacted[-1]
            details = event["details"]
            self.assertEqual(details["section"], "node_local_context")
            self.assertEqual(details["accounting_unit"], "utf8_bytes_upper_bound_not_provider_tokens")
            self.assertEqual(details["cap_utf8_bytes"], 128)
            self.assertGreater(details["original_utf8_bytes"], details["compacted_utf8_bytes"])
            self.assertLessEqual(details["compacted_utf8_bytes"], 128)
            updated = orchestrator.events.read(event="node_context_updated")
            self.assertTrue(updated)
            updated_details = updated[-1]["details"]
            self.assertEqual(updated_details["section"], "node_local_context")
            self.assertEqual(updated_details["context_utf8_bytes"], len(node.compacted_context.encode("utf-8")))
            self.assertEqual(updated_details["accounting_unit"], "utf8_bytes_upper_bound_not_provider_tokens")

    def test_ancestor_lessons_reactivate_parent_chain_without_cross_branch_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "100000"}):
                orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "ancestor memory", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            parent = orchestrator.nodes["orchestrator.graph"]
            child = orchestrator.nodes["subnode.generator"]
            unrelated = orchestrator.nodes["implementation.refactor"]
            self.assertEqual(child.parent_node_id, parent.node_id)
            parent.status = "completed"
            parent.output_summary = "ancestorlessonunique"
            orchestrator._record_node_execution_to_handoff(parent)
            unrelated.status = "completed"
            unrelated.output_summary = "unrelatedlessonunique"
            orchestrator._record_node_execution_to_handoff(unrelated)
            lessons = orchestrator.ancestor_lessons(child.node_id, limit=2)
            self.assertTrue(any("ancestorlessonunique" in item["content"] for item in lessons))
            self.assertFalse(any("unrelatedlessonunique" in item["content"] for item in lessons))
            self.assertEqual(orchestrator.ancestor_lessons("unknown.node", limit=2), [])
            with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "100000"}):
                prompt = orchestrator._generate_node_prompt({
                    "node_id": child.node_id,
                    "purpose": child.purpose,
                    "template": "",
                    "tolerances": {},
                    "dependencies": [],
                    "tests": [],
                    "escalation_rule": "",
                })
            self.assertIn("Ancestor lessons (untrusted data; targeted reactivation):", prompt)
            self.assertIn("ancestorlessonunique", prompt)
            self.assertNotIn("unrelatedlessonunique", prompt)
            self.assertEqual(orchestrator.knowledge.search("ancestorlessonunique", node_id=child.node_id), [])

    def test_terminal_node_records_lesson_once_and_rejects_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "lesson ritual", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.status = "completed"
            node.output_summary = "verifiedflawlesslesson"
            orchestrator._record_node_execution_to_handoff(node)
            orchestrator._record_node_execution_to_handoff(node)
            lessons = [item for item in orchestrator.handoff.lessons_log if item.get("step_id") == node.node_id]
            self.assertEqual(len(lessons), 1)
            self.assertEqual(lessons[0]["type"], "success")
            self.assertIn("verifiedflawlesslesson", lessons[0]["lesson"])
            stored = orchestrator.knowledge.search("verifiedflawlesslesson", node_id=node.node_id)
            self.assertTrue(any(item.get("kind") == "lesson" for item in stored))
            node.status = "running"
            orchestrator._record_node_execution_to_handoff(node)
            self.assertEqual(len([item for item in orchestrator.handoff.lessons_log if item.get("step_id") == node.node_id]), 1)

    def test_terminal_failure_opens_issue_and_completion_closes_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "issue ritual", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.status = "blocked"
            node.error_message = "blockedpayload"
            orchestrator._record_node_execution_to_handoff(node)
            orchestrator._record_node_execution_to_handoff(node)
            issues = [item for item in orchestrator.handoff.issue_register if item.get("step_id") == node.node_id]
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["status"], "open")
            self.assertEqual(issues[0]["severity"], "major")
            self.assertIn("blockedpayload", issues[0]["summary"])
            node.status = "failed"
            node.error_message = "failedpayload"
            orchestrator._record_node_execution_to_handoff(node)
            issues = [item for item in orchestrator.handoff.issue_register if item.get("step_id") == node.node_id]
            self.assertEqual([item["severity"] for item in issues], ["major", "critical"])
            node.status = "completed"
            orchestrator._record_node_execution_to_handoff(node)
            self.assertTrue(all(item["status"] == "closed" for item in issues))
            self.assertTrue(all(item.get("resolution") for item in issues))

    def test_terminal_failure_opens_node_risk_and_completion_closes_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "risk ritual", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            orchestrator.handoff.risk_register.append({"risk": "projectseedrisk", "status": "open", "recorded_at": "seed"})
            node = orchestrator.nodes["root.scope"]
            node.status = "blocked"
            node.error_message = "blockedriskpayload"
            orchestrator._record_node_execution_to_handoff(node)
            orchestrator._record_node_execution_to_handoff(node)
            scoped = [item for item in orchestrator.handoff.risk_register if item.get("step_id") == node.node_id]
            self.assertEqual(len(scoped), 1)
            self.assertEqual(scoped[0]["status"], "open")
            self.assertIn("blockedriskpayload", scoped[0]["risk"])
            node.status = "failed"
            node.error_message = "failedriskpayload"
            orchestrator._record_node_execution_to_handoff(node)
            scoped = [item for item in orchestrator.handoff.risk_register if item.get("step_id") == node.node_id]
            self.assertEqual(len(scoped), 2)
            node.status = "completed"
            orchestrator._record_node_execution_to_handoff(node)
            self.assertTrue(all(item["status"] == "closed" for item in scoped))
            seeds = [item for item in orchestrator.handoff.risk_register if item.get("risk") == "projectseedrisk"]
            self.assertEqual(seeds[0]["status"], "open")

    def test_terminal_node_quality_register_is_evidence_aware_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "quality register", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            node.status = "completed"
            node.output_summary = "qualityevidencepayload"
            orchestrator._record_node_execution_to_handoff(node)
            orchestrator._record_node_execution_to_handoff(node)
            entries = [item for item in orchestrator.handoff.quality_register if item.get("step_id") == node.node_id]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["status"], "passed")
            self.assertIn("qualityevidencepayload", entries[0]["evidence"])
            empty = orchestrator.nodes["subnode.generator"]
            empty.status = "completed"
            empty.output_summary = ""
            empty.error_message = None
            empty.pi_stdout = ""
            orchestrator._record_node_execution_to_handoff(empty)
            empty_entries = [item for item in orchestrator.handoff.quality_register if item.get("step_id") == empty.node_id]
            self.assertEqual(len(empty_entries), 1)
            self.assertEqual(empty_entries[0]["status"], "insufficient_evidence")
            node.status = "failed"
            node.error_message = "failedqualitypayload"
            orchestrator._record_node_execution_to_handoff(node)
            statuses = [item["status"] for item in orchestrator.handoff.quality_register if item.get("step_id") == node.node_id]
            self.assertEqual(statuses, ["passed", "failed"])

    def test_node_event_primary_audit_failure_attempts_secondary_handoff_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "primary audit failure", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            original_append = orchestrator.events.append
            original_handoff = type(orchestrator.handoff).record_action
            events_attempted = []
            handoff_attempts = []
            def fail_primary(event, **kwargs):
                events_attempted.append(event)
                raise OSError("event log unavailable")
            def track_handoff(_self, **kwargs):
                handoff_attempts.append(kwargs)
            orchestrator.events.append = fail_primary
            type(orchestrator.handoff).record_action = track_handoff
            orchestrator._emit_node_event(node, "node_checkpoint", "checkpoint")
            self.assertEqual(events_attempted, ["node_checkpoint"])
            self.assertEqual(len(handoff_attempts), 1)
            self.assertEqual(handoff_attempts[0]["phase"], "goal_loop_node_event_persist_failure_node_checkpoint")
            orchestrator.events.append = original_append
            type(orchestrator.handoff).record_action = original_handoff

    def test_node_event_survives_stderr_failure(self) -> None:
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "stderr failure", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                stderr.write = lambda _value: (_ for _ in ()).throw(OSError("closed stderr"))
                orchestrator._emit_node_event(node, "node_checkpoint", "checkpoint")
            self.assertEqual(len(orchestrator.events.read(event="node_checkpoint")), 1)

    def test_node_event_survives_handoff_and_secondary_audit_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "handoff failure", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            original_record = type(orchestrator.handoff).record_action
            original_event_append = orchestrator.events.append
            def fail_handoff(_self, **kwargs):
                raise OSError("handoff storage unavailable")
            def fail_secondary(event, **kwargs):
                if event == "node_handoff_persist_failure":
                    raise OSError("secondary audit unavailable")
                return original_event_append(event, **kwargs)
            type(orchestrator.handoff).record_action = fail_handoff
            orchestrator.events.append = fail_secondary
            orchestrator._emit_node_event(node, "node_checkpoint", "checkpoint")
            self.assertEqual(len(orchestrator.events.read(event="node_checkpoint")), 1)
            type(orchestrator.handoff).record_action = original_record

    def test_node_event_survives_capsule_persistence_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "capsule failure", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            original_persist = orchestrator._persist_node_capsule
            def fail_capsule(_node):
                raise OSError("capsule storage unavailable")
            orchestrator._persist_node_capsule = fail_capsule
            orchestrator._emit_node_event(node, "node_checkpoint", "checkpoint")
            events = orchestrator.events.read(event="node_checkpoint")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["details"]["capsule_entry_id"], None)
            self.assertEqual(events[0]["details"]["capsule_persist_error"], "OSError")
            orchestrator._persist_node_capsule = original_persist

    def test_node_context_append_persistence_error_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "persistence failure", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            original_record = orchestrator.knowledge.record_context
            def fail_record(**kwargs):
                raise OSError("simulated disk failure")
            orchestrator.knowledge.record_context = fail_record
            before_revision = node.context_revision
            result = orchestrator.codemode_context(node.node_id, "append", text="not durable", expected_revision=before_revision)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "context persistence failed: OSError")
            self.assertEqual(node.context_revision, before_revision)
            self.assertEqual(node.compacted_context, "")
            orchestrator.knowledge.record_context = original_record
            def mismatched_record(**kwargs):
                original_record(**kwargs)
                orchestrator.knowledge.connection.execute(
                    "UPDATE knowledge SET content = 'tampered' WHERE entry_id = ?",
                    (kwargs["entry_id"],),
                )
                orchestrator.knowledge.connection.commit()
            orchestrator.knowledge.record_context = mismatched_record
            mismatch = orchestrator.codemode_context(node.node_id, "append", text="integrity", expected_revision=before_revision)
            self.assertFalse(mismatch["ok"])
            self.assertEqual(mismatch["error"], "context persistence verification failed: content mismatch")
            self.assertEqual(node.context_revision, before_revision)
            orchestrator.knowledge.connection.execute("DELETE FROM knowledge WHERE node_id = ?", (node.node_id,))
            orchestrator.knowledge.connection.commit()
            orchestrator.knowledge.record_context = original_record
            def silent_record(**kwargs):
                return "not-persisted"
            orchestrator.knowledge.record_context = silent_record
            silent = orchestrator.codemode_context(node.node_id, "append", text="silent failure", expected_revision=before_revision)
            self.assertFalse(silent["ok"])
            self.assertEqual(silent["error"], "context persistence verification failed: missing revision")
            self.assertEqual(node.context_revision, before_revision)
            self.assertEqual(node.compacted_context, "")
            orchestrator.knowledge.record_context = original_record

    def test_node_context_expected_revision_serializes_concurrent_appends(self) -> None:
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "CAS test", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            node = orchestrator.nodes["root.scope"]
            barrier = threading.Barrier(3)
            results = []
            def append(text: str) -> None:
                barrier.wait()
                results.append(orchestrator.codemode_context(node.node_id, "append", text=text, expected_revision=0))
            workers = [threading.Thread(target=append, args=(f"note-{idx}",)) for idx in range(2)]
            for worker in workers:
                worker.start()
            barrier.wait()
            for worker in workers:
                worker.join(timeout=5)
            self.assertTrue(all(not worker.is_alive() for worker in workers))
            self.assertEqual(sum(result["ok"] for result in results), 1)
            self.assertEqual(sum(result.get("error") == "context revision conflict" for result in results), 1)
            self.assertEqual(node.context_revision, 1)

    def test_node_context_restores_from_persisted_revision_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_path = Path(tmp)
            first = GoalLoopOrchestrator(AgentConfig(workspace_root=root_path), "restore context", execution_mode="mock", json_mode=True)
            node = first.nodes["root.scope"]
            first.codemode_context(node.node_id, "append", text="durable node-local recovery fact")
            expected_revision = node.context_revision
            expected_uuid = node.node_uuid
            first.knowledge.save_node_execution_capsule(
                tree_id="goal-loop", node_id=node.node_id,
                parent_node_id=node.parent_node_id, purpose=node.purpose,
                capsule={"node_uuid": expected_uuid, "status": "pending", "context_revision": expected_revision},
            )
            first.knowledge.close()

            resumed = GoalLoopOrchestrator(AgentConfig(workspace_root=root_path), "restore context", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: resumed.knowledge.close())
            restored = resumed.nodes[node.node_id]
            self.assertEqual(restored.node_uuid, expected_uuid)
            self.assertEqual(restored.context_revision, expected_revision)
            self.assertIn("durable node-local recovery fact", restored.compacted_context)

    def test_newer_context_snapshot_wins_over_stale_capsule_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_path = Path(tmp)
            first = GoalLoopOrchestrator(AgentConfig(workspace_root=root_path), "snapshot precedence", execution_mode="mock", json_mode=True)
            node = first.nodes["root.scope"]
            first._append_node_context(node, "note", "newest persisted context value")
            revision = node.context_revision
            first.knowledge.save_node_execution_capsule(
                tree_id="goal-loop", node_id=node.node_id,
                parent_node_id=node.parent_node_id, purpose=node.purpose,
                capsule={
                    "node_uuid": node.node_uuid, "status": "pending",
                    "context_revision": max(0, revision - 1), "compacted_context": "stale capsule value",
                },
            )
            first.knowledge.close()

            resumed = GoalLoopOrchestrator(AgentConfig(workspace_root=root_path), "snapshot precedence", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: resumed.knowledge.close())
            restored = resumed.nodes[node.node_id]
            self.assertEqual(restored.context_revision, revision)
            self.assertIn("newest persisted context value", restored.compacted_context)
            self.assertNotIn("stale capsule value", restored.compacted_context)

    def test_mock_run_loop_emits_events_and_persists_completed_capsules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(
                AgentConfig(workspace_root=Path(tmp)), "wet mock verification",
                execution_mode="mock", json_mode=True,
            )
            report = orchestrator.run_loop()
            self.assertEqual(report["final_status"], "completed")
            self.assertTrue(all(node["status"] == "completed" for node in report["node_details"].values()))
            events = orchestrator.events.read()
            self.assertTrue(any(event.get("event") == "node_context_updated" for event in events))
            self.assertTrue(any(event.get("event") == "tree_end" for event in events))
            capsules = NodeKnowledgeStore(Path(tmp) / ".stagewarden" / "node-knowledge.sqlite")
            for node in orchestrator.nodes.values():
                restored = capsules.load_node_execution_capsule(
                    "goal-loop", node.node_id, node_uuid=node.node_uuid
                )["capsule"]
                self.assertEqual(restored["status"], "completed")
                self.assertEqual(restored["node_uuid"], node.node_uuid)
            capsules.close()
            orchestrator.knowledge.close()
            resumed = GoalLoopOrchestrator(
                AgentConfig(workspace_root=Path(tmp)), "wet mock verification",
                execution_mode="mock", json_mode=True,
            )
            self.addCleanup(lambda: resumed.knowledge.close())
            resumed_statuses = {node.node_id: node.status for node in resumed.nodes.values()}
            self.assertTrue(resumed_statuses)
            self.assertTrue(all(status == "completed" for status in resumed_statuses.values()))

    def test_execution_mode_serial_gate_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            default = GoalLoopOrchestrator(AgentConfig(workspace_root=root / "default"), "default", json_mode=True)
            self.assertEqual(default.execution_mode, "auto")
            self.assertEqual(default._get_ready_nodes()[0].node_id, "root.scope")
            default.knowledge.close()
            mock = GoalLoopOrchestrator(AgentConfig(workspace_root=root / "mock"), "mock", execution_mode="mock", json_mode=True)
            self.assertEqual(mock.execution_mode, "mock")
            self.assertEqual(mock._get_ready_nodes()[0].node_id, "root.scope")
            mock.knowledge.close()
            for unsupported in ("parallel", "bogus"):
                with self.assertRaises(ValueError):
                    GoalLoopOrchestrator(AgentConfig(workspace_root=root / unsupported), unsupported, execution_mode=unsupported, json_mode=True)

    def test_terminal_purpose_banner_matrix_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(
                AgentConfig(workspace_root=Path(tmp)),
                "purpose banner",
                execution_mode="mock",
                json_mode=True,
            )
            node = orchestrator.nodes["root.scope"]
            stderr = StringIO()
            with redirect_stderr(stderr):
                orchestrator._emit_node_event(node, "purpose_probe", "observe purpose")
            event = orchestrator.events.read(node_id="root.scope", event="purpose_probe")[0]
            capsule = orchestrator.knowledge.load_node_execution_capsule("goal-loop", "root.scope")["capsule"]
            # 1. Terminal banner repeats node purpose.
            self.assertIn(f"purpose={node.purpose}", stderr.getvalue())
            # 2. JSONL keeps node identity and purpose.
            self.assertEqual(event["node_id"], "root.scope")
            self.assertEqual(event["purpose"], node.purpose)
            # 3. Persisted capsule keeps same purpose.
            self.assertEqual(capsule["purpose"], node.purpose)
            orchestrator.knowledge.close()

    def test_pause_resume_checkpoint_safety_matrix_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(workspace_root=Path(tmp))
            # Capsule reopen boundary.
            orchestrator = GoalLoopOrchestrator(config, "recovery matrix", execution_mode="mock", json_mode=True)
            node = next(iter(orchestrator.nodes.values()))
            orchestrator.current_iteration = 1
            node.status = "running"
            node.cycle_id = 1
            node.cycle_phase = "verify"
            orchestrator._emit_node_event(node, "node_cycle_checkpoint", "checkpoint")
            saved = orchestrator.knowledge.load_node_execution_capsule("goal-loop", node.node_id)
            self.assertEqual(saved["capsule"]["cycle_phase"], "verify")
            orchestrator.knowledge.close()
            resumed = GoalLoopOrchestrator(config, "recovery matrix", execution_mode="mock", json_mode=True)
            self.assertEqual(resumed.nodes[node.node_id].status, "running")
            resumed.knowledge.close()

    def test_tree_packet_acceptance_matrix_has_six_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "matrix", execution_mode="mock", json_mode=True)
            self.assertEqual(len([node for node in orchestrator.nodes.values() if node.parent_node_id is None]), 1)
            self.assertEqual(orchestrator._get_ready_nodes()[0].node_id, "root.scope")
            root = orchestrator.nodes["root.scope"]
            packet = orchestrator._build_work_packet(root)
            self.assertEqual(packet["packet_type"], "WorkPacket")
            self.assertEqual(packet["child_node_id"], "root.scope")
            with self.assertRaises(ValueError):
                orchestrator._build_work_packet(NodeState(node_id="invalid", parent_node_id="missing", purpose="x", prompt_template_name="", prompt="", inputs=[], outputs=[], acceptance_criteria=["x"], tests=[], tolerances={}, escalation_rule="", dependencies=[]))
            child = next(node for node in orchestrator.nodes.values() if node.parent_node_id == "root.scope")
            child_packet = orchestrator._build_work_packet(child)
            child_packet["result_packet"] = {"packet_type": "ResultPacket", "parent_node_id": child.parent_node_id, "child_node_id": child.node_id, "evidence": [{"kind": "test", "value": "ok"}]}
            self.assertEqual(child_packet["result_packet"]["parent_node_id"], "root.scope")
            before = len(orchestrator.nodes["root.scope"].messages_received)
            orchestrator._handle_control_message({"FROM": child.node_id, "TO": "validation.wet_run", "TYPE": "status", "SUMMARY": "lateral"})
            self.assertEqual(len(orchestrator.nodes["root.scope"].messages_received), before)
            self.assertEqual(orchestrator._node_depth(child.node_id), 1)
            orchestrator.knowledge.close()

    def test_goal_blueprint_has_single_root_and_authorized_parent_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_goal_loop_report(AgentConfig(workspace_root=Path(tmp)), "validate tree")
            graph = report["node_graph"]
            self.assertEqual(graph["root"]["id"], "root.scope")
            self.assertEqual(sum(1 for node in graph["children"] if node["parent_id"] is None), 1)
            node_ids = {node["id"] for node in graph["children"]}
            for node in graph["children"]:
                for dependency in node["depends_on"]:
                    self.assertIn(dependency, node_ids)
                    self.assertIn(dependency, {"root.scope", "orchestrator.graph", "subnode.generator", "implementation.refactor", "validation.wet_run", "governance.tolerance"})

    def test_blocked_node_retries_once_and_emits_retry_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "retry", execution_mode="mock", json_mode=True)
            node = orchestrator.nodes["root.scope"]
            node.max_retries = 1
            with patch.object(
                orchestrator,
                "_mock_execution",
                side_effect=[
                    {"ok": False, "error": "temporary blocker", "messages": []},
                    {"ok": True, "summary": "recovered", "messages": []},
                ],
            ):
                orchestrator._execute_node(node)
                self.assertEqual(node.status, "pending")
                self.assertEqual(node.retry_count, 1)
                retry_events = orchestrator.events.read(event="node_retry")
                self.assertEqual(len(retry_events), 1)
                orchestrator._execute_node(node)
            self.assertEqual(node.status, "completed")
            self.assertEqual(node.retry_count, 1)
            self.assertEqual(len(orchestrator.events.read(event="node_retry")), 1)
            orchestrator.knowledge.close()

    def test_retry_checkpoint_replay_safety_matrix_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(workspace_root=Path(tmp))
            orchestrator = GoalLoopOrchestrator(config, "retry checkpoint", execution_mode="mock", json_mode=True)
            node = orchestrator.nodes["root.scope"]
            node.max_retries = 1
            with patch.object(orchestrator, "_mock_execution", return_value={"ok": False, "error": "temporary", "messages": []}):
                # 1. blocked→pending emits bounded retry fields
                orchestrator._execute_node(node)
                self.assertEqual(node.status, "pending")
                event = orchestrator.events.read(event="node_retry")[-1]
                self.assertEqual(event["details"]["retry_count"], 1)
                self.assertEqual(event["details"]["max_retries"], 1)
                # 2. persisted retry/cycle checkpoint reopens
                saved = orchestrator.knowledge.load_node_execution_capsule("goal-loop", node.node_id)["capsule"]
                self.assertEqual(saved["retry_count"], 1)
                reopened = GoalLoopOrchestrator(config, "retry checkpoint", execution_mode="mock", json_mode=True)
                self.assertEqual(reopened.nodes[node.node_id].retry_count, 1)
                self.assertEqual(reopened.nodes[node.node_id].status, "pending")
                retry_replay = reopened.events.replay(node_id=node.node_id)["nodes"][node.node_id]
                self.assertEqual(retry_replay["retry_count"], 1)
                self.assertEqual(retry_replay["max_retries"], 1)
                reopened.knowledge.close()
                # 3. max retry ceiling leaves node blocked, no second retry event
                orchestrator._execute_node(node)
            self.assertEqual(node.status, "blocked")
            self.assertEqual(node.retry_count, 1)
            self.assertEqual(len(orchestrator.events.read(event="node_retry")), 1)
            orchestrator.knowledge.close()

    def test_parent_receives_typed_result_only_after_child_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "typed result", execution_mode="mock", json_mode=True)
            parent = orchestrator.nodes["orchestrator.graph"]
            child = orchestrator.nodes["subnode.generator"]
            parent.status = "completed"
            orchestrator._execute_node(child)
            results = [item for item in parent.messages_received if item.get("TYPE") == "result"]
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["FROM"], child.node_id)
            self.assertEqual(results[0]["TO"], parent.node_id)
            self.assertIsInstance(results[0]["EVIDENCE"], list)
            orchestrator.knowledge.close()

    def test_work_packet_contains_parent_edge_and_acceptance_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "contract", execution_mode="mock", json_mode=True)
            node = orchestrator.nodes["orchestrator.graph"]
            packet = orchestrator._build_work_packet(node)
            self.assertEqual(packet["parent_node_id"], "root.scope")
            self.assertEqual(packet["child_node_id"], node.node_id)
            self.assertTrue(packet["acceptance_criteria"])
            self.assertEqual(packet["dependencies"], ["root.scope"])
            orchestrator.knowledge.close()

    def test_result_forwarding_rejects_lateral_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "lateral", execution_mode="mock", json_mode=True)
            node = orchestrator.nodes["root.scope"]
            node.messages_received.clear()
            orchestrator._handle_control_message({"FROM": "orchestrator.graph", "TO": "implementation.refactor", "TYPE": "result", "SUMMARY": "lateral"})
            self.assertEqual(orchestrator.nodes["implementation.refactor"].messages_received, [])
            self.assertTrue(any(item.get("TYPE") == "result" for item in orchestrator.message_bus.messages))
            orchestrator.knowledge.close()
            orchestrator.knowledge.close()

    def test_result_packet_is_parent_scoped_and_has_evidence_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "packet edge", execution_mode="mock", json_mode=True)
            node = orchestrator.nodes["root.scope"]
            orchestrator._execute_node(node)
            packet = orchestrator._pending_parent_packets[node.node_id]["result_packet"]
            self.assertEqual(packet["parent_node_id"], node.parent_node_id)
            self.assertEqual(packet["child_node_id"], node.node_id)
            self.assertIsInstance(packet["evidence"], list)
            self.assertNotIn("messages", packet)
            orchestrator.knowledge.close()

    def test_ready_nodes_follow_dependency_rank_and_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "ready order", execution_mode="mock", json_mode=True)
            ready = orchestrator._get_ready_nodes()
            self.assertEqual([node.node_id for node in ready], ["root.scope"])
            orchestrator.nodes["root.scope"].status = "completed"
            ready = orchestrator._get_ready_nodes()
            self.assertEqual([node.node_id for node in ready], ["orchestrator.graph"])
            orchestrator.knowledge.close()

    def test_tree_validator_rejects_dependency_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "cycle", execution_mode="mock", json_mode=True)
            orchestrator.nodes["root.scope"].dependencies = ["orchestrator.graph"]
            with self.assertRaises(ValueError):
                orchestrator._validate_tree_invariants()
            orchestrator.knowledge.close()

    def test_work_packet_defaults_to_manual_selection_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "packet policy", execution_mode="mock", json_mode=True)
            node = next(iter(orchestrator.nodes.values()))
            packet = orchestrator._build_work_packet(node)
            self.assertEqual(packet["selection_policy"], "manual")
            self.assertEqual(packet["node_uuid"], node.node_uuid)
            self.assertEqual(packet["context_cache_scope"], "node_uuid")
            orchestrator.knowledge.close()

    def test_goal_loop_uuid_task_scope_matrix_has_three_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp) / "first"), "task alpha", execution_mode="mock", json_mode=True)
            same = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp) / "same"), "task alpha", execution_mode="mock", json_mode=True)
            other = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp) / "other"), "task beta", execution_mode="mock", json_mode=True)
            self.assertEqual(first.nodes["root.scope"].node_uuid, same.nodes["root.scope"].node_uuid)
            self.assertNotEqual(first.nodes["root.scope"].node_uuid, other.nodes["root.scope"].node_uuid)
            packet = first._build_work_packet(first.nodes["root.scope"])
            self.assertEqual(packet["node_uuid"], first.nodes["root.scope"].node_uuid)
            first.knowledge.close()
            same.knowledge.close()
            other.knowledge.close()

    def test_goal_loop_reopen_uses_task_scoped_capsule_uuid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alpha = GoalLoopOrchestrator(AgentConfig(workspace_root=root), "task alpha", execution_mode="mock", json_mode=True)
            node = alpha.nodes["root.scope"]
            node.status = "running"
            alpha._emit_node_event(node, "task_scope_probe", "alpha")
            alpha.knowledge.close()
            beta = GoalLoopOrchestrator(AgentConfig(workspace_root=root), "task beta", execution_mode="mock", json_mode=True)
            self.assertEqual(beta.nodes["root.scope"].status, "pending")
            beta.knowledge.close()

    def test_node_context_uuid_matrix_carries_uuid_through_state_packet_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "node uuid", execution_mode="mock", json_mode=True)
            node = orchestrator.nodes["root.scope"]
            node_uuid = node.node_uuid
            self.assertEqual(str(__import__("uuid").UUID(node_uuid)), node_uuid)
            packet = orchestrator._build_work_packet(node)
            self.assertEqual(packet["node_uuid"], node_uuid)
            self.assertIn(node_uuid, node.prompt)
            self.assertEqual(node.as_dict()["node_uuid"], node_uuid)
            orchestrator.knowledge.close()

    def test_node_cycle_state_defaults_and_serializes(self) -> None:
        node = NodeState(
            node_id="leaf",
            purpose="Inspect source",
            prompt_template_name="goal-loop-execution",
            prompt="prompt",
            inputs=[],
            outputs=[],
            acceptance_criteria=["evidence"],
            tests=["tests"],
            tolerances={},
            escalation_rule="stop",
            dependencies=[],
        )
        self.assertEqual(node.cycle_id, 0)
        self.assertEqual(node.cycle_phase, "ready")
        self.assertEqual(node.context_revision, 0)
        self.assertTrue(node.cycle_budget["max_cycles"] > 0)
        serialized = node.as_dict()
        self.assertEqual(serialized["cycle_id"], 0)
        self.assertEqual(serialized["cycle_phase"], "ready")
        self.assertEqual(serialized["context_revision"], 0)

    def test_node_cycle_checkpoint_persists_cycle_and_context_revision(self) -> None:
        node = NodeState(
            node_id="leaf",
            purpose="Inspect source",
            prompt_template_name="goal-loop-execution",
            prompt="prompt",
            inputs=[],
            outputs=[],
            acceptance_criteria=[],
            tests=[],
            tolerances={},
            escalation_rule="stop",
            dependencies=[],
        )
        node.cycle_id = 2
        node.cycle_phase = "verify"
        node.context_revision = 3
        node.last_checkpoint = "event-7"
        node.output_summary = "tests passed"
        serialized = node.as_dict()
        self.assertEqual(serialized["cycle_id"], 2)
        self.assertEqual(serialized["cycle_phase"], "verify")
        self.assertEqual(serialized["context_revision"], 3)
        self.assertEqual(serialized["last_checkpoint"], "event-7")

    def test_orchestrator_persists_capsule_after_node_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(workspace_root=Path(tmp))
            orchestrator = GoalLoopOrchestrator(config, "bounded cycle capsule", execution_mode="mock", json_mode=True)
            node = next(iter(orchestrator.nodes.values()))
            orchestrator.current_iteration = 1
            node.status = "running"
            node.cycle_id = 1
            node.cycle_phase = "verify"
            node.context_revision = 1
            orchestrator._emit_node_event(node, "node_cycle_checkpoint", "checkpoint")
            saved = orchestrator.knowledge.load_node_execution_capsule("goal-loop", node.node_id)
            self.assertEqual(saved["capsule"]["cycle_phase"], "verify")
            self.assertEqual(saved["capsule"]["context_revision"], 1)
            orchestrator.knowledge.close()

            resumed = GoalLoopOrchestrator(config, "bounded cycle capsule", execution_mode="mock", json_mode=True)
            resumed_node = resumed.nodes[node.node_id]
            self.assertEqual(resumed_node.status, "running")
            self.assertEqual(resumed_node.cycle_id, 1)
            self.assertEqual(resumed_node.last_checkpoint, "node_cycle_checkpoint:1:1")
            resumed.knowledge.close()

    def test_pi_output_cap_guard_only_blocks_when_explicitly_required(self) -> None:
        import stagewarden.goal_loop_orchestrator as mod
        orchestrator = GoalLoopOrchestrator(
            AgentConfig(workspace_root=self.tmp_dir / "pi-output-cap"),
            "pi output cap", execution_mode="pi", json_mode=True,
        )
        self.addCleanup(lambda: orchestrator.knowledge.close())
        node = orchestrator.nodes["root.scope"]
        node.context_budget["max_output_tokens"] = 384
        completed = self._build_result(json.dumps({"summary": "ok", "messages": []}))
        with patch.dict(os.environ, {
            "STAGEWARDEN_GOAL_LOOP_BACKEND": "pi",
            "STAGEWARDEN_GOAL_LOOP_REQUIRE_OUTPUT_CAP": "",
        }), patch.object(mod.shutil, "which", return_value="/usr/bin/pi"), patch.object(
            mod.subprocess, "run", return_value=completed
        ) as run:
            result = orchestrator._pi_execution(node)
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(run.call_args.args[0][:3], ["/usr/bin/pi", "--print", "--no-tools"])

    def test_pi_execution_preserves_reported_output_usage(self) -> None:
        result = self._pi_exec(
            '{"summary":"done","messages":[],"usage":{"completion_tokens":17}}',
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["observed_output_tokens"], 17)

    def test_observed_output_tokens_rejects_fractional_and_malformed_values(self) -> None:
        parse = GoalLoopOrchestrator._observed_output_tokens
        for value in (1.5, True, -1, "1.5", "NaN", "Infinity", "bad"):
            with self.subTest(value=value):
                self.assertIsNone(parse({"usage": {"completion_tokens": value}}))
        self.assertIsNone(parse({"usage": {"completion_tokens": "2.0"}}))
        self.assertEqual(parse({"usage": {"completion_tokens": " 17 "}}), 17)

    def test_executor_usage_extraction_rejects_fractional_counts(self) -> None:
        from stagewarden.executor import Executor
        from stagewarden.handoff import HandoffManager
        from stagewarden.memory import MemoryStore
        from stagewarden.project_handoff import ProjectHandoff
        from stagewarden.rag import DesignRag
        from stagewarden.router import ModelRouter
        executor = Executor(
            config=AgentConfig(workspace_root=self.tmp_dir), router=ModelRouter(),
            handoff=HandoffManager(), memory=MemoryStore(),
            project_handoff=ProjectHandoff(), rag=DesignRag(),
        )
        try:
            self.assertIsNone(executor._safe_positive_int(1.5))
            self.assertIsNone(executor._safe_positive_int("1.5"))
            self.assertIsNone(executor._safe_positive_int("NaN"))
            self.assertEqual(executor._safe_positive_int("17"), 17)
            extracted = executor._extract_usage_metadata({
                "usage": {"prompt_tokens": "11", "completion_tokens": "1.5"},
            })
            self.assertEqual(extracted["input_tokens"], 11)
            self.assertIsNone(extracted["output_tokens"])
            self.assertEqual(extracted["current_usage"], 11)
        finally:
            executor.close()

    def test_node_contract_preserves_reported_output_usage(self) -> None:
        result = GoalLoopOrchestrator._node_contract_result(
            {"summary": "done", "messages": [], "usage": {"completion_tokens": 23}},
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["observed_output_tokens"], 23)

    def test_pi_execution_omits_output_usage_when_provider_does_not_report_it(self) -> None:
        result = self._pi_exec('{"summary":"done","messages":[],"usage":{"prompt_tokens":99}}')
        self.assertTrue(result["ok"])
        self.assertNotIn("observed_output_tokens", result)

    def test_pi_execution_parses_clean_json(self) -> None:
        """Valid JSON output with summary/messages is parsed by the real method."""
        stdout = json.dumps({
            "summary": "Node completed.",
            "messages": [
                {"FROM": "node.a", "TO": "node.b", "TYPE": "status",
                 "SUMMARY": "done", "PRIORITY": "low", "TOLERANCE_IMPACT": "none"}
            ],
            "output": "some output",
        })
        result = self._pi_exec(stdout, task="clean json")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["summary"], "Node completed.")
        self.assertEqual(len(result["messages"]), 1)
        self.assertEqual(result["messages"][0]["FROM"], "node.a")
        self.assertEqual(result["output"], "some output")

    def test_pi_execution_strips_ansi_notification(self) -> None:
        """A notification OSC carrying its own 'summary' must not win the parse.

        The payload deliberately puts the real JSON FIRST and the notify
        envelope SECOND, so if OSC stripping is broken the last-object regex
        picks the notification's summary instead of the real one. An earlier
        version of this test placed them the other way and passed even with OSC
        stripping removed, because the regex fallback masked the regression.
        """
        raw = ('{"summary":"real","messages":[]}'
               '\x1b]777;notify;{"summary":"NOTIFY","messages":[]}\x07')
        result = self._pi_exec(raw, task="ansi order")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["summary"], "real")

    def test_pi_execution_ignores_ansi_escaped_json_envelope(self) -> None:
        """A CSI-wrapped JSON body must still parse after CSI stripping."""
        raw = '\x1b[1;32m{"summary":"coloured","messages":[]}\x1b[0m'
        result = self._pi_exec(raw, task="ansi csi")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["summary"], "coloured")

    def test_pi_execution_fallback_to_raw_text(self) -> None:
        """Non-JSON output still falls back to summary text (legacy pi text mode)."""
        raw = "Hello from pi, I completed the task."
        result = self._pi_exec(raw, task="text fallback")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["summary"], raw)
        self.assertEqual(result["messages"], [])

    def test_pi_execution_regex_finds_json_in_noise(self) -> None:
        """JSON object embedded in other text is extracted by the real method."""
        noisy = 'Some text\n{"summary":"found","messages":[]}\ntrailing'
        result = self._pi_exec(noisy, task="noise")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["summary"], "found")

    def test_pi_execution_handles_multiple_json_objects(self) -> None:
        """When multiple JSON objects exist, the last one with 'summary' wins."""
        output = (
            '{"summary":"first","messages":[],"output":"","error":null}\n'
            '{"summary":"second","messages":[],"output":"","error":null}'
        )
        result = self._pi_exec(output, task="multiple objects")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["summary"], "second")

    def test_pi_execution_rejects_wrong_typed_output_instead_of_leaking_object(self) -> None:
        for value in ('{"secret":"payload"}', "7", "null", "[]"):
            with self.subTest(output=value):
                result = self._pi_exec(
                    '{"summary":"s","messages":[],"output":' + value + '}',
                    task="wrong output type",
                )
                self.assertFalse(result["ok"])
                self.assertIn("string summary and a messages array", result["error"])
                self.assertNotIn("secret", str(result.get("output", "")))

    def test_pi_execution_rejects_wrong_typed_messages_instead_of_crashing(self) -> None:
        """A wrong-typed 'messages' must fail closed, not raise inside node execution.

        The existing tests above re-implement the parse logic instead of calling
        _pi_execution, which is how a real crash survived: a wrong-typed
        'messages' reached the node and AttributeError/TypeError escaped.
        """
        wrong = ('"x"', '{"a":1}', "7", "null")
        for value in wrong:
            with self.subTest(messages=value):
                with tempfile.TemporaryDirectory() as tmp:
                    orchestrator = GoalLoopOrchestrator(
                        AgentConfig(workspace_root=Path(tmp)),
                        f"pi msgs {value}",
                        execution_mode="pi",
                        json_mode=True,
                    )
                    node = orchestrator.nodes["root.scope"]
                    stdout = '{"summary":"s","messages":' + value + "}"
                    completed = subprocess.CompletedProcess(
                        args=["pi"], returncode=0, stdout=stdout, stderr=""
                    )
                    with redirect_stderr(StringIO()), patch(
                        "stagewarden.goal_loop_orchestrator.subprocess.run",
                        return_value=completed,
                    ), patch(
                        "stagewarden.goal_loop_orchestrator.shutil.which",
                        return_value="/usr/bin/pi",
                    ):
                        result = orchestrator._pi_execution(node)
                    self.assertFalse(result["ok"], f"messages={value} must fail closed")
                    self.assertEqual(result["messages"], [])
                    self.assertIn("messages", result["error"])
                    orchestrator.knowledge.close()

    def test_pi_execution_still_accepts_valid_and_text_output(self) -> None:
        """Valid JSON and the legacy plain-text fallback must both keep working."""
        cases = (
            ('{"summary":"s","messages":[]}', True),
            ('{"summary":"s","messages":[{"role":"x"}]}', True),
            ('{"summary":"s","messages":[1,2]}', True),
            ('{"summary":"s"}', True),
            ("Hello from pi, I completed the task.", True),
            ("no json at all", True),
        )
        for stdout, expect_ok in cases:
            with self.subTest(stdout=stdout[:32]):
                with tempfile.TemporaryDirectory() as tmp:
                    orchestrator = GoalLoopOrchestrator(
                        AgentConfig(workspace_root=Path(tmp)),
                        "pi ok",
                        execution_mode="pi",
                        json_mode=True,
                    )
                    node = orchestrator.nodes["root.scope"]
                    completed = subprocess.CompletedProcess(
                        args=["pi"], returncode=0, stdout=stdout, stderr=""
                    )
                    with patch(
                        "stagewarden.goal_loop_orchestrator.subprocess.run",
                        return_value=completed,
                    ), patch(
                        "stagewarden.goal_loop_orchestrator.shutil.which",
                        return_value="/usr/bin/pi",
                    ):
                        result = orchestrator._pi_execution(node)
                    self.assertEqual(result["ok"], expect_ok, result.get("error"))
                    if expect_ok:
                        self.assertIsInstance(result["summary"], str)
                        self.assertIsInstance(result["messages"], list)
                    orchestrator.knowledge.close()

    def test_autonomy_gate_classifies_high_impact(self) -> None:
        """classify_decision returns 'ask_user' for high-impact terms."""
        from stagewarden.goal_loop_orchestrator import classify_decision
        level, reason = classify_decision("Modify auth module", "security")
        self.assertEqual(level, "ask_user")
        self.assertIn("security", reason)

    def test_autonomy_gate_classifies_low_impact(self) -> None:
        """classify_decision returns 'autonomous' for low-impact terms."""
        from stagewarden.goal_loop_orchestrator import classify_decision
        level, reason = classify_decision("Rename local variable", "style")
        self.assertEqual(level, "autonomous")
        self.assertIn("reversible", reason)

    def test_optional_classifier_can_raise_but_never_lower_autonomy_caution(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        orchestrator = GoalLoopOrchestrator(self.config, "optional classifier", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)
        node = orchestrator.nodes["root.scope"]

        class FakeClassifier:
            backend = "test"
            def __init__(self, label): self.label = label
            def classify(self, request):
                self.request = request
                return DecisionResult(self.label, 0.99, "test", "fake", {
                    "autonomous": 0.0, "report": 0.0, "ask_user": 1.0, "stop": 0.0
                })

        classifier = FakeClassifier("autonomous")
        orchestrator._decision_classifier = classifier
        with patch("stagewarden.goal_loop_orchestrator.classify_decision", return_value=("ask_user", "fixed safety rule")):
            proceed, reason = orchestrator._autonomy_gate(node)
        self.assertFalse(proceed)  # Deterministic ask_user remains authoritative.
        self.assertEqual(node.decision_evidence["label"], "autonomous")
        self.assertEqual(reason, "fixed safety rule")
        self.assertEqual(node.decision_evidence["policy_action"], "blocked_json_mode")
        self.assertEqual(classifier.request.labels, ("autonomous", "report", "ask_user", "stop"))

    def test_optional_classifier_may_raise_caution(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        orchestrator = GoalLoopOrchestrator(self.config, "optional classifier", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)
        node = orchestrator.nodes["root.scope"]
        class FakeClassifier:
            backend = "test"
            def classify(self, request):
                return DecisionResult("stop", 0.99, "test", "fake", {
                    "autonomous": 0.0, "report": 0.0, "ask_user": 0.0, "stop": 1.0
                })
        orchestrator._decision_classifier = FakeClassifier()
        with patch("stagewarden.goal_loop_orchestrator.classify_decision", return_value=("autonomous", "fixed")):
            proceed, reason = orchestrator._autonomy_gate(node)
        self.assertFalse(proceed)
        self.assertEqual(reason, "Decision classifier advised stop.")
        self.assertEqual(node.decision_evidence["policy_action"], "blocked")

    def test_optional_classifier_ask_user_blocks_in_json_mode(self) -> None:
        from stagewarden.decision_classifier import DecisionResult
        orchestrator = GoalLoopOrchestrator(self.config, "optional classifier", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)
        node = orchestrator.nodes["root.scope"]
        class FakeClassifier:
            backend = "test"
            def classify(self, request):
                return DecisionResult("ask_user", 0.99, "test", "fake", {
                    "autonomous": 0.0, "report": 0.0, "ask_user": 1.0, "stop": 0.0
                })
        orchestrator._decision_classifier = FakeClassifier()
        with patch("stagewarden.goal_loop_orchestrator.classify_decision", return_value=("autonomous", "fixed")):
            proceed, reason = orchestrator._autonomy_gate(node)
        self.assertFalse(proceed)
        self.assertEqual(node.status, "blocked")
        self.assertEqual(node.decision_evidence["policy_action"], "blocked_json_mode")

    def test_tolerance_violation_detected(self) -> None:
        """check_tolerance_violation returns violation when threshold=none."""
        from stagewarden.goal_loop_orchestrator import check_tolerance_violation
        outcome, reason = check_tolerance_violation(
            {"scope_drift": "none"}, {"scope_drift": "changed"}
        )
        self.assertEqual(outcome, "violation")
        self.assertIn("scope_drift", reason or "")

    def test_tolerance_no_violation(self) -> None:
        """check_tolerance_violation returns ok when tolerances match."""
        from stagewarden.goal_loop_orchestrator import check_tolerance_violation
        outcome, reason = check_tolerance_violation({}, {})
        self.assertEqual(outcome, "ok")

    def test_pi_execution_via_mocked_subprocess(self) -> None:
        """Full _pi_execution flow with mocked subprocess and shutil."""
        import subprocess as _sp
        import shutil as _sh
        from unittest.mock import patch, PropertyMock
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO

        mock_json = json.dumps({
            "summary": "Node completed via pi mock.",
            "messages": [{"FROM": "x", "TO": "y", "TYPE": "status",
                           "SUMMARY": "done", "PRIORITY": "low",
                           "TOLERANCE IMPACT": "none"}],
        })
        mock_process = _sp.CompletedProcess(
            args=["pi", "--print", "--no-tools", "--no-session", "@test.md"],
            returncode=0,
            stdout=mock_json,
            stderr="",
        )

        with patch('stagewarden.goal_loop_orchestrator.shutil.which',
                   return_value="/usr/local/bin/pi"), \
             patch('stagewarden.goal_loop_orchestrator.subprocess.run',
                   return_value=mock_process):
            config = AgentConfig(workspace_root=self.tmp_dir)
            orch = GO(config, "test task", execution_mode="pi")
            result = orch.run_loop()
            self.assertEqual(result["final_status"], "completed")
            # Check that first node completed via pi
            first_node = list(result["node_details"].keys())[0]
            self.assertEqual(result["node_details"][first_node]["status"],
                             "completed")

    def test_omniroute_backend_uses_free_adapter_and_requires_packet_summary(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        node = GO(self.config, "test task", execution_mode="pi").nodes["root.scope"]
        adapter = Path(__file__).parents[1] / "scripts" / "run_model_omniroute.py"
        completed = subprocess.CompletedProcess(
            args=["python", str(adapter), "--node-contract", "cheap", node.prompt],
            returncode=0,
            stdout=json.dumps({"summary": "free node done", "messages": [], "output": "evidence"}),
            stderr="",
        )
        with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_BACKEND": "omniroute"}), patch(
            "stagewarden.goal_loop_orchestrator.subprocess.run", return_value=completed
        ):
            result = GO(self.config, "test task", execution_mode="pi")._pi_execution(node)
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"], "free node done")

    def test_pi_backend_fails_closed_when_output_cap_is_required(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "test task", execution_mode="pi")
        node = orch.nodes["root.scope"]
        node.context_budget["max_output_tokens"] = 512
        with patch.dict(os.environ, {
            "STAGEWARDEN_GOAL_LOOP_BACKEND": "pi",
            "STAGEWARDEN_GOAL_LOOP_REQUIRE_OUTPUT_CAP": "true",
        }), patch("stagewarden.goal_loop_orchestrator.subprocess.run") as run:
            result = orch._pi_execution(node)
        self.assertFalse(result["ok"])
        self.assertIn("cannot enforce", result["error"])
        run.assert_not_called()
        orch.knowledge.close()

    def test_invalid_output_cap_policy_env_fails_before_backend(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "test task", execution_mode="pi")
        node = orch.nodes["root.scope"]
        for value in ("maybe", "2", "enabled", "truth"):
            with self.subTest(value=value), patch.dict(os.environ, {
                "STAGEWARDEN_GOAL_LOOP_BACKEND": "omniroute",
                "STAGEWARDEN_GOAL_LOOP_REQUIRE_OUTPUT_CAP": value,
            }), patch("stagewarden.goal_loop_orchestrator.subprocess.run") as run:
                result = orch._pi_execution(node)
                self.assertFalse(result["ok"])
                self.assertIn("must be a boolean", result["error"])
                run.assert_not_called()
        orch.knowledge.close()

    def test_input_budget_policy_requires_boolean_literal(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "test task", execution_mode="pi")
        self.addCleanup(lambda: orch.knowledge.close())
        node = orch.nodes["root.scope"]
        definition = next(item for item in orch.blueprint["child_prompts"] if item["node_id"] == node.node_id)
        for value in ("maybe", "2", "enabled"):
            with self.subTest(value=value), patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_REQUIRE_INPUT_BUDGET": value}):
                with self.assertRaisesRegex(ValueError, "must be a boolean"):
                    orch._enforce_node_prompt_budget(node, definition)

    def test_unknown_input_budget_can_be_required_or_explicitly_overridden(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "input budget policy", execution_mode="pi")
        self.addCleanup(lambda: orch.knowledge.close())
        node = orch.nodes["root.scope"]
        definition = next(item for item in orch.blueprint["child_prompts"] if item["node_id"] == node.node_id)
        with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_REQUIRE_INPUT_BUDGET": "true"}):
            with self.assertRaisesRegex(ValueError, "Input-token limit unknown"):
                orch._enforce_node_prompt_budget(node, definition)
        with patch.dict(os.environ, {
            "STAGEWARDEN_GOAL_LOOP_REQUIRE_INPUT_BUDGET": "true",
            "STAGEWARDEN_GOAL_LOOP_INPUT_TOKENS": "12000",
        }):
            orch._enforce_node_prompt_budget(node, definition)
        self.assertEqual(node.context_budget["input_limit"], 12000)

    def test_pi_backend_fails_closed_when_output_cap_required_but_unknown(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "test task", execution_mode="pi")
        node = orch.nodes["root.scope"]
        node.context_budget["max_output_tokens"] = None
        with patch.dict(os.environ, {
            "STAGEWARDEN_GOAL_LOOP_BACKEND": "pi",
            "STAGEWARDEN_GOAL_LOOP_REQUIRE_OUTPUT_CAP": "true",
        }), patch("stagewarden.goal_loop_orchestrator.subprocess.run") as run:
            result = orch._pi_execution(node)
        self.assertFalse(result["ok"])
        self.assertIn("whether or not the provider limit is known", result["error"])
        run.assert_not_called()
        orch.knowledge.close()

    def test_work_and_result_packets_preserve_node_purpose(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "test task", execution_mode="mock")
        node = orch.nodes["root.scope"]
        packet = orch._build_work_packet(node)
        self.assertEqual(packet["packet_type"], "WorkPacket")
        self.assertEqual(packet["purpose"], node.purpose)
        orch._execute_node(node)
        stored = orch._pending_parent_packets[node.node_id]
        self.assertEqual(stored["result_packet"]["packet_type"], "ResultPacket")
        self.assertEqual(stored["result_packet"]["child_node_id"], node.node_id)

    def test_required_output_cap_blocks_omniroute_unverified_limit_before_http(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "test task", execution_mode="pi")
        node = orch.nodes["root.scope"]
        with patch.dict(os.environ, {
            "STAGEWARDEN_GOAL_LOOP_BACKEND": "omniroute",
            "STAGEWARDEN_GOAL_LOOP_REQUIRE_OUTPUT_CAP": "true",
        }), patch("stagewarden.goal_loop_orchestrator.subprocess.run") as run:
            result = orch._pi_execution(node)
        self.assertFalse(result["ok"])
        self.assertIn("not verified enforcement", result["error"])
        run.assert_not_called()
        orch.knowledge.close()

    def test_omniroute_backend_clears_inherited_output_cap_when_budget_unknown(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "test task", execution_mode="pi")
        node = orch.nodes["root.scope"]
        node.context_budget.update({"max_output_tokens": None, "reserved_output": None})
        completed = subprocess.CompletedProcess(args=["adapter"], returncode=1, stdout="{}", stderr="failed")
        with patch.dict(os.environ, {
            "STAGEWARDEN_GOAL_LOOP_BACKEND": "omniroute",
            "STAGEWARDEN_OMNIROUTE_MAX_TOKENS": "1234",
        }), patch("stagewarden.goal_loop_orchestrator.subprocess.run", return_value=completed) as run:
            orch._pi_execution(node)
        self.assertNotIn("STAGEWARDEN_OMNIROUTE_MAX_TOKENS", run.call_args.kwargs["env"])
        orch.knowledge.close()

    def test_omniroute_backend_applies_provider_output_cap_to_request_env(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "test task", execution_mode="pi")
        node = orch.nodes["root.scope"]
        node.context_budget.update({"max_output_tokens": 900, "reserved_output": 700})
        completed = subprocess.CompletedProcess(args=["adapter"], returncode=1, stdout="{}", stderr="failed")
        with patch.dict(os.environ, {
            "STAGEWARDEN_GOAL_LOOP_BACKEND": "omniroute",
            "STAGEWARDEN_OMNIROUTE_MAX_TOKENS": "1200",
        }), patch("stagewarden.goal_loop_orchestrator.subprocess.run", return_value=completed) as run:
            orch._pi_execution(node)
        self.assertEqual(run.call_args.kwargs["env"]["STAGEWARDEN_OMNIROUTE_MAX_TOKENS"], "700")
        orch.knowledge.close()

    def test_omniroute_backend_fails_closed_without_summary(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        node = GO(self.config, "test task", execution_mode="pi").nodes["root.scope"]
        completed = subprocess.CompletedProcess(args=["adapter"], returncode=0, stdout="{}", stderr="")
        with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_BACKEND": "omniroute"}), patch(
            "stagewarden.goal_loop_orchestrator.subprocess.run", return_value=completed
        ):
            result = GO(self.config, "test task", execution_mode="pi")._pi_execution(node)
        self.assertFalse(result["ok"])
        self.assertIn("summary", result["error"])

    def test_omniroute_cap_overrun_without_breakdown_keeps_legacy_diagnostic(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "legacy cap diagnostic", execution_mode="pi")
        self.addCleanup(lambda: orch.knowledge.close())
        node = orch.nodes["root.scope"]
        node.context_budget.update({"max_output_tokens": 96, "reserved_output": None, "available_input": 4096})
        proc = subprocess.CompletedProcess(args=["adapter"], returncode=0,
            stdout='{"summary":"s","messages":[],"usage":{"completion_tokens":203}}', stderr="")
        with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_BACKEND":"omniroute"}), patch(
            "stagewarden.goal_loop_orchestrator.subprocess.run", return_value=proc,
        ):
            result=orch._pi_execution(node)
        self.assertFalse(result["ok"])
        self.assertEqual(result["cap_violation"], {"observed_output_tokens":203,"requested_cap":96})
        self.assertNotIn("reasoning_tokens", result)

    def test_omniroute_preserves_observed_output_usage(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "test task", execution_mode="pi")
        self.addCleanup(lambda: orch.knowledge.close())
        node = orch.nodes["root.scope"]
        proc = subprocess.CompletedProcess(
            args=["adapter"], returncode=0,
            stdout='{"summary":"s","messages":[],"usage":{"completion_tokens":12}}', stderr="",
        )
        with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_BACKEND": "omniroute"}), patch(
            "stagewarden.goal_loop_orchestrator.subprocess.run", return_value=proc,
        ):
            result = orch._pi_execution(node)
        self.assertTrue(result["ok"])
        self.assertEqual(result["observed_output_tokens"], 12)

    def test_omniroute_adapter_usage_reaches_end_to_end_cap_diagnostic(self) -> None:
        """Exercise actual adapter serializer + executor boundary with provider reasoning usage."""
        import contextlib
        import io
        import sys
        import scripts.run_model_omniroute as adapter
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "cap usage bridge", execution_mode="pi")
        self.addCleanup(lambda: orch.knowledge.close())
        node = orch.nodes["root.scope"]
        node.context_budget.update({"max_output_tokens":96,"reserved_output":None,"available_input":4096})
        body = {
            "model":"nvidia/nemotron-3.5-super-vl:free",
            "choices":[{"message":{"content":json.dumps({"summary":"READY","messages":[]})},"finish_reason":"stop"}],
            "usage":{"prompt_tokens":151,"completion_tokens":203,"completion_tokens_details":{"reasoning_tokens":199,"visible_content_tokens":1}},
        }
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self): return json.dumps(body).encode()
        def fake_run(args, **kwargs):
            output=io.StringIO()
            with patch.object(sys, "argv", [str(args[1]), "--node-contract", "cheap", "prompt"]):
                with patch.object(adapter.urllib.request, "urlopen", return_value=Response()), patch.dict(
                    os.environ, {"STAGEWARDEN_PROVIDER_MODEL": "auto/coding:free", "STAGEWARDEN_OMNIROUTE_MAX_TOKENS": "96"}):
                    with contextlib.redirect_stdout(output):
                        rc = adapter.main()
            return subprocess.CompletedProcess(args=args,returncode=rc,stdout=output.getvalue(),stderr="")
        with patch.dict(os.environ,{"STAGEWARDEN_GOAL_LOOP_BACKEND":"omniroute","STAGEWARDEN_OMNIROUTE_MAX_TOKENS":"96"}), patch(
            "stagewarden.goal_loop_orchestrator.subprocess.run",side_effect=fake_run
        ):
            result=orch._pi_execution(node)
        self.assertFalse(result["ok"])
        self.assertEqual(result["cap_violation"]["observed_output_tokens"],203)
        self.assertEqual(result["cap_violation"]["reasoning_tokens"],199)
        self.assertEqual(result["cap_violation"]["visible_content_tokens"],1)
        self.assertEqual(result["cap_violation"]["reasoning_overrun_tokens"],103)

    def test_omniroute_reasoning_token_overrun_is_visible_in_cap_violation(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "reasoning cap visibility", execution_mode="pi")
        self.addCleanup(lambda: orch.knowledge.close())
        node = orch.nodes["root.scope"]
        node.context_budget.update({"max_output_tokens": 96, "reserved_output": None, "available_input": 4096})
        proc = subprocess.CompletedProcess(
            args=["adapter"], returncode=0,
            stdout=json.dumps({"summary":"READY", "messages":[], "usage":{
                "completion_tokens":203,
                "completion_tokens_details":{"reasoning_tokens":199},
                "visible_content_tokens":1,
            }}), stderr="",
        )
        with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_BACKEND":"omniroute"}), patch(
            "stagewarden.goal_loop_orchestrator.subprocess.run", return_value=proc,
        ):
            result=orch._pi_execution(node)
        self.assertFalse(result["ok"])
        self.assertEqual(result["cap_violation"], {
            "observed_output_tokens":203,"requested_cap":96,
            "reasoning_tokens":199,"visible_content_tokens":1,
            "reasoning_overrun_tokens":103,
        })
        self.assertEqual(result["reasoning_tokens"],199)
        self.assertEqual(result["visible_content_tokens"],1)
        self.assertEqual(result["reasoning_token_overrun"],103)

    def test_omniroute_observed_output_token_overrun_fails_closed(self) -> None:
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO
        orch = GO(self.config, "test task", execution_mode="pi")
        node = orch.nodes["root.scope"]
        node.context_budget.update({"max_output_tokens": 128, "reserved_output": None, "available_input": 4096})
        overrun = subprocess.CompletedProcess(
            args=["adapter"], returncode=0,
            stdout='{"summary":"s","messages":[],"usage":{"completion_tokens":999}}', stderr="",
        )
        with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_BACKEND": "omniroute"}), patch(
            "stagewarden.goal_loop_orchestrator.subprocess.run", return_value=overrun
        ):
            result = orch._pi_execution(node)
        self.assertFalse(result["ok"])
        self.assertEqual(result["cap_violation"], {"observed_output_tokens": 999, "requested_cap": 128})
        self.assertIn("exceeded requested output cap", result["error"])
        within = subprocess.CompletedProcess(
            args=["adapter"], returncode=0,
            stdout='{"summary":"s","messages":[],"usage":{"completion_tokens":10}}', stderr="",
        )
        with patch.dict(os.environ, {"STAGEWARDEN_GOAL_LOOP_BACKEND": "omniroute"}), patch(
            "stagewarden.goal_loop_orchestrator.subprocess.run", return_value=within
        ):
            accepted = orch._pi_execution(node)
        self.assertTrue(accepted["ok"])
        self.assertNotIn("cap_violation", accepted)
        orch.knowledge.close()

    def test_pi_execution_handles_nonzero_returncode(self) -> None:
        """_pi_execution returns error on non-zero pi exit."""
        import subprocess as _sp
        from unittest.mock import patch
        from stagewarden.goal_loop_orchestrator import GoalLoopOrchestrator as GO

        mock_process = _sp.CompletedProcess(
            args=["pi", "--print", "--no-tools", "--no-session", "@test.md"],
            returncode=1,
            stdout="",
            stderr="Error: something went wrong",
        )

        with patch('stagewarden.goal_loop_orchestrator.shutil.which',
                   return_value="/usr/local/bin/pi"), \
             patch('stagewarden.goal_loop_orchestrator.subprocess.run',
                   return_value=mock_process):
            config = AgentConfig(workspace_root=self.tmp_dir)
            orch = GO(config, "test task", execution_mode="pi")
            result = orch.run_loop()
            # With non-zero return code, nodes should block
            first_node = list(result["node_details"].keys())[0]
            self.assertIn(result["node_details"][first_node]["status"],
                          ("blocked", "pending"))


class CustomNodeSkillFileTests(unittest.TestCase):
    """Custom-node skill files are user-authored, so per the cycle-172 ranking
    they are among the most likely inputs to be corrupt. Both readers decoded
    them unguarded, so invalid UTF-8 raised out of node registration and out of
    goal-loop node construction."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # CUSTOM_NODES_PATH is repo-relative, so it MUST be redirected or the
        # test would read and write the real repository.
        import stagewarden.goal_loop_views as views
        self.views = views
        self.addCleanup(setattr, views, "CUSTOM_NODES_PATH", views.CUSTOM_NODES_PATH)
        views.CUSTOM_NODES_PATH = self.root / "goal_loop_custom_nodes.json"

    def _skill(self, name: str, body: bytes) -> Path:
        path = self.root / name
        path.write_bytes(body)
        return path

    def test_registration_rejects_an_undecodable_skill_file(self) -> None:
        bodies = {
            "binary garbage": b"\xff\xfe\x00\x01\x80\x81 not utf-8",
            "lone continuation": b"\x80\x81\x82 only continuation bytes",
            "truncated utf8": b"# Skill\nvalid \xc3",
        }
        for label, body in bodies.items():
            with self.subTest(skill=label):
                skill = self._skill(f"{label}.md", body)
                result = self.views.register_custom_node("probe", str(skill), purpose="p")
                self.assertIs(result.get("ok"), False, f"{label} must be refused: {result}")
                self.assertIn("utf-8", str(result.get("error", "")).lower())
                # a refused node must NOT be persisted
                self.assertEqual(self.views.load_custom_nodes(), [])

    def test_goal_loop_builds_a_custom_node_from_an_undecodable_skill_file(self) -> None:
        for label, body in {
            "binary garbage": b"\xff\xfe not utf-8",
            "lone continuation": b"\x80\x81 only continuation",
            "truncated utf8": b"# Skill\nvalid \xc3",
        }.items():
            with self.subTest(skill=label):
                skill = self._skill(f"{label}-build.md", body)
                self.views.save_custom_nodes([{
                    "node_id": "custom.probe", "skill_path": str(skill),
                    "purpose": "p", "template": "custom", "inputs": [],
                    # parented under the default root, otherwise the custom node
                    # becomes a second root and the tree invariant rejects it
                    "parent_id": "root.scope",
                }])
                orchestrator = GoalLoopOrchestrator(
                    AgentConfig(workspace_root=self.root / f"ws-{label}"),
                    "probe task", execution_mode="pi", json_mode=True,
                )
                self.addCleanup(orchestrator.knowledge.close)
                node = orchestrator.nodes["custom.probe"]
                self.assertEqual(node.purpose, "p")
                self.assertIn("not valid utf-8", node.prompt.lower())

    def test_catalog_registers_multiple_skills_for_node(self) -> None:
        skill_root = self.root / ".stagewarden" / "skills"
        (skill_root / "review").mkdir(parents=True)
        (skill_root / "review" / "SKILL.md").write_text(
            "---\nname: review\ndescription: Review safely\n---\nReview instructions.", encoding="utf-8"
        )
        (skill_root / "tests").mkdir(parents=True)
        (skill_root / "tests" / "SKILL.md").write_text("# Test skill\nRun focused tests.", encoding="utf-8")
        catalog = self.views.load_skill_catalog([skill_root])
        self.assertEqual([item["name"] for item in catalog], ["review", "tests"])
        with patch.object(self.views, "Path", wraps=Path):
            # Register uses workspace-root catalog; point cwd to the test root so fixture is in-scope.
            with patch("stagewarden.goal_loop_views.Path.cwd", return_value=self.root):
                result = self.views.register_custom_node("multi", purpose="Review", skills=["review", "tests"])
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["node"]["skills"], ["review", "tests"])
        self.assertEqual(set(result["node"]["skill_hashes"]), {"review", "tests"})
        self.assertEqual(self.views.resolve_node_skills(["review"] * 11, [skill_root])[1],
                         ["A node may use at most 10 skills."])

    def test_named_skills_are_added_to_each_assigned_node_prompt(self) -> None:
        skill_root = self.root / "ws" / ".stagewarden" / "skills"
        (skill_root / "one").mkdir(parents=True)
        (skill_root / "one" / "SKILL.md").write_text("---\nname: one\ndescription: one\n---\nNODE SKILL BODY", encoding="utf-8")
        workspace = self.root / "ws"
        config_dir = workspace / ".stagewarden"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "goal_loop_skills.json").write_text(
            json.dumps({"root.scope": ["one"], "missing.node": ["one"]}), encoding="utf-8"
        )
        orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=workspace), "skill assignment", json_mode=True)
        self.addCleanup(orchestrator.knowledge.close)
        self.assertIn("NODE SKILL BODY", orchestrator.nodes["root.scope"].prompt)
        self.assertNotIn("NODE SKILL BODY", orchestrator.nodes[next(n for n in orchestrator.nodes if n != "root.scope")].prompt)

    def test_skill_registry_and_node_assignment_are_workspace_scoped(self) -> None:
        from stagewarden.goal_loop_views import load_node_skill_assignments
        workspace = self.root / "workspace"
        skill_root = workspace / ".stagewarden" / "skills" / "inspect"
        skill_root.mkdir(parents=True)
        (skill_root / "SKILL.md").write_text("---\nname: inspect\n---\nInspect only.", encoding="utf-8")
        node = GoalLoopOrchestrator(AgentConfig(workspace_root=workspace), "skills", json_mode=True)
        self.addCleanup(node.knowledge.close)
        # Capture per-node assignment registry read by fresh loop construction.
        (workspace / ".stagewarden" / "goal_loop_skills.json").write_text(
            json.dumps({"root.scope": ["inspect"]}), encoding="utf-8"
        )
        fresh = GoalLoopOrchestrator(AgentConfig(workspace_root=workspace), "skills", json_mode=True)
        self.addCleanup(fresh.knowledge.close)
        self.assertIn("Inspect only.", fresh.nodes["root.scope"].prompt)
        self.assertEqual(load_node_skill_assignments(workspace), {"root.scope": ["inspect"]})

    def test_skill_file_controls_keep_their_existing_behaviour(self) -> None:
        good = self._skill("GOOD.md", b"# Good skill\nbody\n")
        self.assertIs(self.views.register_custom_node("g", str(good)).get("ok"), True)

        empty = self._skill("EMPTY.md", b"")
        result = self.views.register_custom_node("e", str(empty))
        self.assertIs(result.get("ok"), False)
        self.assertIn("empty", str(result.get("error", "")).lower())

        missing = self.root / "NOPE.md"
        result = self.views.register_custom_node("m", str(missing))
        self.assertIs(result.get("ok"), False)
        self.assertIn("not found", str(result.get("error", "")).lower())

        # a corrupt REGISTRY stays tolerated (already fail-closed in cycle 175)
        self.views.CUSTOM_NODES_PATH.write_bytes(b"\xff\xfe not utf-8")
        self.assertEqual(self.views.load_custom_nodes(), [])


class GoalLoopResultPacketProvenanceTests(unittest.TestCase):
    """A node's ResultPacket is the project's audit record. In `auto` mode a
    missing pi falls back to mock execution, but the packet carried no execution
    mode, so a run with NO AI backend produced persisted evidence
    byte-identical to a real one. The two-gate test says a finding is fixed only
    when it is both a safety issue and in approved scope; this is both: node-first
    MVP is the top approved priority, and claiming completion for work that never
    ran is a misleading success."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _orchestrator(self, mode: str):
        return GoalLoopOrchestrator(
            AgentConfig(workspace_root=self.root / mode),
            "provenance task", execution_mode=mode, json_mode=True,
        )

    def test_mock_fallback_in_auto_mode_is_recorded_in_the_result_packet(self) -> None:
        import stagewarden.goal_loop_orchestrator as mod

        orchestrator = self._orchestrator("auto")
        self.addCleanup(orchestrator.knowledge.close)
        with patch.object(mod, "_pi_available", return_value=False):
            ready = orchestrator._get_ready_nodes()
            self.assertTrue(ready, "expected a ready node")
            orchestrator._execute_node(ready[0])

        packet = orchestrator._pending_parent_packets[ready[0].node_id]["result_packet"]
        self.assertIsNotNone(packet)
        self.assertEqual(
            packet.get("execution_mode"), "mock",
            "a node completed by mock fallback must say so in its ResultPacket",
        )
        self.assertEqual(ready[0].status, "completed")

    def test_explicit_mock_mode_is_also_recorded(self) -> None:
        orchestrator = self._orchestrator("mock")
        self.addCleanup(orchestrator.knowledge.close)
        ready = orchestrator._get_ready_nodes()
        self.assertTrue(ready)
        orchestrator._execute_node(ready[0])
        packet = orchestrator._pending_parent_packets[ready[0].node_id]["result_packet"]
        self.assertIsNotNone(packet)
        self.assertEqual(packet.get("execution_mode"), "mock")

    def test_real_pi_execution_is_recorded_as_pi(self) -> None:
        import stagewarden.goal_loop_orchestrator as mod

        orchestrator = self._orchestrator("auto")
        self.addCleanup(orchestrator.knowledge.close)
        with patch.object(mod, "_pi_available", return_value=True), \
             patch.object(orchestrator, "_pi_execution",
                          return_value={"ok": True, "summary": "real", "messages": [],
                                         "evidence": ["e"]}):
            ready = orchestrator._get_ready_nodes()
            self.assertTrue(ready)
            orchestrator._execute_node(ready[0])
        packet = orchestrator._pending_parent_packets[ready[0].node_id]["result_packet"]
        self.assertIsNotNone(packet)
        self.assertEqual(
            packet.get("execution_mode"), "pi",
            "a node completed by real pi execution must record pi, not mock",
        )


    def test_provenance_survives_event_replay_projection(self) -> None:
        import stagewarden.goal_loop_orchestrator as mod
        orchestrator = self._orchestrator("auto")
        self.addCleanup(orchestrator.knowledge.close)
        with patch.object(mod, "_pi_available", return_value=False):
            ready = orchestrator._get_ready_nodes()
            self.assertTrue(ready)
            orchestrator._execute_node(ready[0])
        projection = orchestrator.events.replay(node_id=ready[0].node_id)
        self.assertEqual(
            projection["nodes"][ready[0].node_id].get("execution_mode"), "mock",
            "event replay must preserve execution provenance",
        )

    def test_provenance_reaches_parent_result_message(self) -> None:
        import stagewarden.goal_loop_orchestrator as mod
        orchestrator = self._orchestrator("auto")
        self.addCleanup(orchestrator.knowledge.close)
        with patch.object(mod, "_pi_available", return_value=False):
            ready = orchestrator._get_ready_nodes()
            self.assertTrue(ready)
            orchestrator._execute_node(ready[0])
            child = next(
                (node for node in orchestrator.nodes.values()
                 if node.parent_node_id and node.status == "pending"),
                None,
            )
            self.assertIsNotNone(child)
            orchestrator._execute_node(child)
        parent = orchestrator.nodes[child.parent_node_id]
        self.assertTrue(parent.messages_received)
        self.assertEqual(
            parent.messages_received[-1].get("EXECUTION_MODE"), "mock",
            "typed child->parent result must retain execution provenance",
        )

    def test_incoming_child_result_provenance_survives_handoff_and_reopen(self) -> None:
        """A parent receives typed child results in memory, but as_dict omitted
        messages_received. Thus goal_loop_context/capsule/reopen lost the upward
        execution provenance even though parent.messages_received was truthful."""
        orchestrator = self._orchestrator("mock")
        self.addCleanup(orchestrator.knowledge.close)
        # Real child->parent path: execute root, then its ready child.
        ready = orchestrator._get_ready_nodes()
        self.assertTrue(ready)
        orchestrator._execute_node(ready[0])
        child = next(
            (node for node in orchestrator.nodes.values()
             if node.parent_node_id and node.status == "pending"),
            None,
        )
        self.assertIsNotNone(child)
        orchestrator._execute_node(child)
        parent = orchestrator.nodes[child.parent_node_id]
        self.assertEqual(parent.messages_received[-1]["EXECUTION_MODE"], "mock")

        report = orchestrator._sync_goal_loop_context()
        details = orchestrator.handoff.goal_loop_context["node_details"][parent.node_id]
        self.assertEqual(
            details["messages_received"][-1]["EXECUTION_MODE"], "mock"
        )
        orchestrator.handoff.save(orchestrator.config.handoff_path)
        orchestrator.knowledge.close()

        reopened = GoalLoopOrchestrator(
            orchestrator.config, "provenance task", execution_mode="mock", json_mode=True
        )
        self.addCleanup(reopened.knowledge.close)
        restored = reopened.nodes[parent.node_id]
        self.assertEqual(restored.messages_received[-1]["EXECUTION_MODE"], "mock")

    def test_provenance_reaches_event_and_capsule_recovery_records(self) -> None:
        import stagewarden.goal_loop_orchestrator as mod
        orchestrator = self._orchestrator("auto")
        self.addCleanup(orchestrator.knowledge.close)
        with patch.object(mod, "_pi_available", return_value=False):
            ready = orchestrator._get_ready_nodes()
            self.assertTrue(ready)
            orchestrator._execute_node(ready[0])
        node_id = ready[0].node_id
        events = orchestrator.events.read(node_id=node_id, event="node_cycle_checkpoint")
        self.assertTrue(events)
        self.assertEqual(events[-1]["details"].get("execution_mode"), "mock")
        capsule = orchestrator.knowledge.load_node_execution_capsule(
            "goal-loop", node_id, node_uuid=ready[0].node_uuid
        )
        self.assertEqual(capsule["capsule"].get("execution_mode"), "mock")

class GoalLoopControlSocketTests(unittest.TestCase):
    """Tests for goal loop TCP control socket."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_control_server_start_stop(self) -> None:
        """Server starts and stops without error."""
        from stagewarden.goal_loop_control import GoalLoopControlServer
        server = GoalLoopControlServer(self.tmp_dir)
        server.start()
        self.assertGreater(server.port, 0)
        server.stop()
        # verify info file is removed after stop
        info_file = self.tmp_dir / ".stagewarden" / "goal_loop_control.txt"
        self.assertFalse(info_file.exists())

    def test_control_server_writes_info_file(self) -> None:
        """Info file is created with correct port and host."""
        from stagewarden.goal_loop_control import GoalLoopControlServer
        server = GoalLoopControlServer(self.tmp_dir)
        server.start()
        info_file = self.tmp_dir / ".stagewarden" / "goal_loop_control.txt"
        self.assertTrue(info_file.exists())
        import json
        data = json.loads(info_file.read_text())
        self.assertEqual(data["host"], "127.0.0.1")
        self.assertEqual(data["port"], server.port)
        self.assertEqual(data["pid"], os.getpid())
        server.stop()

    def test_control_server_receives_message(self) -> None:
        """Message sent to control port is received via callback."""
        from stagewarden.goal_loop_control import (
            GoalLoopControlServer, send_control_message,
        )
        received: list[dict] = []

        def on_msg(msg):
            received.append(msg)

        server = GoalLoopControlServer(self.tmp_dir, on_message=on_msg)
        server.start()

        msg = {
            "FROM": "external.tool",
            "TO": "root.scope",
            "TYPE": "decision",
            "SUMMARY": "User approved the scope.",
            "PRIORITY": "high",
            "TOLERANCE IMPACT": "none",
        }
        response = send_control_message(server.port, msg)
        self.assertEqual(response, "OK")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["FROM"], "external.tool")
        self.assertEqual(received[0]["SUMMARY"], "User approved the scope.")
        server.stop()

    def test_control_server_rejects_invalid_message(self) -> None:
        """Message without FROM/TO is rejected."""
        from stagewarden.goal_loop_control import (
            GoalLoopControlServer, send_control_message,
        )
        server = GoalLoopControlServer(self.tmp_dir)
        server.start()

        msg = {"TYPE": "status", "SUMMARY": "Missing FROM/TO"}
        response = send_control_message(server.port, msg)
        self.assertIn("ERROR", response)
        self.assertIn("FROM", response)
        server.stop()

    def test_discover_control_port(self) -> None:
        """discover_control_port reads port from info file."""
        from stagewarden.goal_loop_control import (
            GoalLoopControlServer, discover_control_port,
        )
        server = GoalLoopControlServer(self.tmp_dir)
        server.start()
        port = discover_control_port(self.tmp_dir)
        self.assertEqual(port, server.port)
        server.stop()
        port = discover_control_port(self.tmp_dir)
        self.assertIsNone(port)


if __name__ == "__main__":
    unittest.main()
