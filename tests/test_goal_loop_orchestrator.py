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

    def test_budget_estimator_uses_utf8_bytes_and_compaction_respects_byte_cap(self) -> None:
        self.assertEqual(GoalLoopOrchestrator._estimate_tokens("aé🙂"), len("aé🙂".encode("utf-8")))
        compacted = GoalLoopOrchestrator._compact_node_text("🙂" * 1000, 300)
        self.assertLessEqual(len(compacted.encode("utf-8")), 300)
        self.assertIn("context auto-compacted", compacted)
        self.assertEqual(
            GoalLoopOrchestrator._estimate_tokens(compacted),
            len(compacted.encode("utf-8")),
        )

    def test_node_context_codemode_is_uuid_scoped_and_compacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = GoalLoopOrchestrator(AgentConfig(workspace_root=Path(tmp)), "context test", execution_mode="mock", json_mode=True)
            self.addCleanup(lambda: orchestrator.knowledge.close())
            root = orchestrator.nodes["root.scope"]
            other = orchestrator.nodes[next(node_id for node_id in orchestrator.nodes if node_id != "root.scope")]
            first = orchestrator.codemode_context(root.node_id, "append", text="private root fact")
            self.assertTrue(first["ok"])
            self.assertIn("private root fact", orchestrator.codemode_context(root.node_id, "read")["context"])
            saved = orchestrator.knowledge.search("private root fact", node_id=root.node_id, namespace="context")
            self.assertTrue(saved)
            self.assertNotIn("private root fact", orchestrator.codemode_context(other.node_id, "read")["context"])
            before = root.context_revision
            orchestrator._append_node_context(root, "test", "long " * 10000)
            self.assertGreater(root.context_revision, before)
            self.assertNotIn("private root fact", other.compacted_context)
            self.assertFalse(orchestrator.codemode_context(root.node_id, "eval", text="__import__('os').system('true')")["ok"])

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
