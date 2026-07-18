from __future__ import annotations

import io
import os
import tempfile
import time
from pathlib import Path

from .agent import Agent
from .config import AgentConfig
from .memory import MemoryStore
from .modelprefs import ModelPreferences, account_key, limit_snapshot_from_message
from .project_handoff import ProjectHandoff
from .project import role_flow as _project_role_flow
from .project import role_runtime_views as _project_role_runtime_views
from . import project_handoff_views as _project_handoff_views
from . import status_dashboard_views as _status_dashboard_views
from .planner import PlanStep
from .textcodec import dumps_ascii


def _battery_report(config: AgentConfig) -> dict[str, object]:

    class _BatteryHandoffStub:
        def __init__(self, outputs: list[dict[str, object]]) -> None:
            self.outputs = list(outputs)
            self.calls: list[str] = []
            self.model_variant_by_model: dict[str, str] = {}
            self.account_env_by_target: dict[str, str] = {}
            self.model_params_by_model: dict[str, dict[str, str]] = {}

        def execute(self, command: str):  # noqa: ANN001
            self.calls.append(command)
            command_lower = command.lower()
            if (
                "required keys: verdict" in command_lower
                or "allowed verdict values: accept, revise, block" in command_lower
                or "you are the devil's advocate / project assurance critic" in command_lower
                or ("retrospettiva prospettica" in command_lower and "primary model response" in command_lower)
            ) and not self.outputs:
                payload = {
                    "ok": True,
                    "model": "local",
                    "backend": "local/ollama",
                    "prompt": command,
                    "command": command,
                    "output": dumps_ascii(
                        {
                            "summary": "devil advocate review",
                            "verdict": "accept",
                            "contradictions": [],
                            "missing_evidence": [],
                            "counter_argument": "No contradiction found.",
                            "must_escalate": False,
                            "confidence": 0.9,
                        }
                    ),
                    "error": "",
                }
                return type("ModelResult", (), payload)()
            payload = self.outputs.pop(0) if self.outputs else {
                "ok": True,
                "model": "local",
                "backend": "local/ollama",
                "prompt": "",
                "command": command,
                "output": dumps_ascii({"summary": "battery fallback", "action": {"type": "complete", "message": "validation completed exit_code=0"}}),
                "error": "",
            }
            return type("ModelResult", (), payload)()

    def _run_simulation(name: str, runner) -> dict[str, object]:
        started = time.monotonic()
        try:
            payload = runner()
            ok = bool(payload.get("ok", False)) if isinstance(payload, dict) else bool(payload)
            message = str(payload.get("message", "ok")) if isinstance(payload, dict) else "ok"
            details = payload if isinstance(payload, dict) else {"value": payload}
        except Exception as exc:  # pragma: no cover - defensive
            ok = False
            message = str(exc)
            details = {"error": str(exc)}
        return {
            "name": name,
            "ok": ok,
            "message": message,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "details": details,
        }

    simulations: list[dict[str, object]] = []

    def bootstrap_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            agent = Agent(AgentConfig(workspace_root=Path(tmp_dir), max_steps=1))
            git_head = agent.git.head()
            return {
                "ok": True,
                "message": "agent bootstrapped",
                "workspace": str(agent.config.workspace_root),
                "git_head": git_head.stdout.strip() if git_head.ok else None,
            }

    def executor_write_file_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            agent.executor.handoff = _BatteryHandoffStub(
                [
                    {
                        "ok": True,
                        "model": "local",
                        "backend": "local/ollama",
                        "prompt": "battery",
                        "command": "run_model local battery",
                        "output": dumps_ascii(
                            {
                                "summary": "battery file write",
                                "action": {
                                    "type": "write_file",
                                    "path": "battery.txt",
                                    "content": "battery ok\n",
                                },
                            }
                        ),
                        "error": "",
                    }
                ]
            )
            step = PlanStep(
                id="battery.write",
                title="Write battery file",
                instruction="create a file named battery.txt",
                validation="battery file exists",
            )
            outcome = agent.executor.execute_step(
                task="create a file",
                step=step,
                plan=[step],
                iteration=1,
                last_observation="none",
            )
            created = (root / "battery.txt").exists()
            return {
                "ok": bool(outcome.ok and outcome.step_completed and created),
                "message": "file write simulation passed" if outcome.ok and created else "file write simulation failed",
                "file_created": created,
                "step_completed": outcome.step_completed,
                "observation": outcome.observation,
            }

    def executor_read_file_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "battery-read.txt").write_text("battery read ok\n", encoding="utf-8")
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            observation = agent.executor._run_action({"type": "read_file", "path": "battery-read.txt"}, iteration=1, step_id="battery.read")  # noqa: SLF001
            ok = bool(observation.get("ok")) and "battery read ok" in str(observation.get("message", ""))
            return {
                "ok": ok,
                "message": "file read simulation passed" if ok else "file read simulation failed",
                "observation": observation,
            }

    def executor_inspect_file_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "battery-inspect.txt").write_text("battery inspect ok\nline two\n", encoding="utf-8")
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            observation = agent.executor._run_action({"type": "inspect_file", "path": "battery-inspect.txt"}, iteration=1, step_id="battery.inspect")  # noqa: SLF001
            message = str(observation.get("message", ""))
            ok = bool(observation.get("ok")) and '"path":' in message and "battery-inspect.txt" in message
            return {
                "ok": ok,
                "message": "file inspect simulation passed" if ok else "file inspect simulation failed",
                "observation": observation,
            }

    def executor_search_replace_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "battery-replace.txt"
            target.write_text("alpha beta gamma\n", encoding="utf-8")
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            observation = agent.executor._run_action(  # noqa: SLF001
                {
                    "type": "search_replace_file",
                    "path": "battery-replace.txt",
                    "search": "beta",
                    "replace": "delta",
                },
                iteration=1,
                step_id="battery.replace",
            )
            content = target.read_text(encoding="utf-8")
            ok = bool(observation.get("ok")) and "delta" in content and "beta" not in content
            return {
                "ok": ok,
                "message": "search replace simulation passed" if ok else "search replace simulation failed",
                "content": content,
                "observation": observation,
            }

    def executor_list_search_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "alpha.txt").write_text("one\nneedle\n", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "beta.txt").write_text("needle inside nested file\n", encoding="utf-8")
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            listed = agent.executor._run_action({"type": "list_files", "base_path": ".", "pattern": "*.txt"}, iteration=1, step_id="battery.list")  # noqa: SLF001
            searched = agent.executor._run_action({"type": "search_files", "pattern": "needle", "base_path": ".", "glob": "*.txt"}, iteration=1, step_id="battery.search")  # noqa: SLF001
            list_message = str(listed.get("message", ""))
            search_message = str(searched.get("message", ""))
            ok = bool(listed.get("ok")) and bool(searched.get("ok")) and "alpha.txt" in list_message and "beta.txt" in search_message
            return {
                "ok": ok,
                "message": "list/search simulation passed" if ok else "list/search simulation failed",
                "list": listed,
                "search": searched,
            }

    def filesystem_mutation_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "battery-fs.txt"
            source.write_text("filesystem mutation\n", encoding="utf-8")
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            inspect_meta = agent.executor._run_action({"type": "inspect_metadata_file", "path": "battery-fs.txt"}, iteration=1, step_id="battery.fs")  # noqa: SLF001
            copy = agent.executor._run_action({"type": "copy_path_file", "source": "battery-fs.txt", "destination": "battery-fs-copy.txt"}, iteration=1, step_id="battery.fs")  # noqa: SLF001
            copy_exists = (root / "battery-fs-copy.txt").exists()
            move = agent.executor._run_action({"type": "move_path_file", "source": "battery-fs-copy.txt", "destination": "battery-fs-moved.txt"}, iteration=1, step_id="battery.fs")  # noqa: SLF001
            moved_exists_before_delete = (root / "battery-fs-moved.txt").exists()
            chmod = agent.executor._run_action({"type": "chmod_path_file", "path": "battery-fs-moved.txt", "mode": "600"}, iteration=1, step_id="battery.fs")  # noqa: SLF001
            mode_bits_before_delete = oct((root / "battery-fs-moved.txt").stat().st_mode & 0o777) if moved_exists_before_delete else "missing"
            delete = agent.executor._run_action({"type": "delete_path_file", "path": "battery-fs-moved.txt"}, iteration=1, step_id="battery.fs")  # noqa: SLF001
            moved_exists = (root / "battery-fs-moved.txt").exists()
            deleted_exists = (root / "battery-fs-moved.txt").exists()
            ok = (
                bool(inspect_meta.get("ok"))
                and bool(copy.get("ok"))
                and bool(move.get("ok"))
                and bool(chmod.get("ok"))
                and bool(delete.get("ok"))
                and copy_exists
                and moved_exists_before_delete
                and not moved_exists
                and not deleted_exists
                and mode_bits_before_delete == "0o600"
            )
            return {
                "ok": ok,
                "message": "filesystem mutation simulation passed" if ok else "filesystem mutation simulation failed",
                "inspect_meta": inspect_meta,
                "copy": copy,
                "move": move,
                "chmod": chmod,
                "delete": delete,
                "copy_exists": copy_exists,
                "moved_exists_before_delete": moved_exists_before_delete,
                "moved_exists": moved_exists,
                "deleted_exists": deleted_exists,
                "mode_bits": mode_bits_before_delete,
            }

    def executor_shell_command_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            observation = agent.executor._run_action(  # noqa: SLF001
                {"type": "shell", "command": "python3 -c \"print('battery shell ok')\""},
                iteration=1,
                step_id="battery.shell",
            )
            ok = bool(observation.get("ok")) and "battery shell ok" in str(observation.get("message", ""))
            return {
                "ok": ok,
                "message": "shell command simulation passed" if ok else "shell command simulation failed",
                "observation": observation,
            }

    def git_workflow_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            target = root / "battery-git.txt"
            target.write_text("git workflow\n", encoding="utf-8")
            status = agent.executor._run_action({"type": "git_status"}, iteration=1, step_id="battery.git")  # noqa: SLF001
            diff = agent.executor._run_action({"type": "git_diff"}, iteration=1, step_id="battery.git")  # noqa: SLF001
            commit = agent.executor._run_action({"type": "git_commit", "message": "battery: git workflow"}, iteration=1, step_id="battery.git")  # noqa: SLF001
            log = agent.executor._run_action({"type": "git_log", "limit": 3}, iteration=1, step_id="battery.git")  # noqa: SLF001
            show = agent.executor._run_action({"type": "git_show", "revision": "HEAD", "stat": True}, iteration=1, step_id="battery.git")  # noqa: SLF001
            ok = bool(status.get("ok")) and bool(diff.get("ok")) and bool(commit.get("ok")) and bool(log.get("ok")) and bool(show.get("ok"))
            return {
                "ok": ok,
                "message": "git workflow simulation passed" if ok else "git workflow simulation failed",
                "status": status,
                "diff": diff,
                "commit": commit,
                "log": log,
                "show": show,
            }

    def executor_shell_session_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            create = agent.executor._run_action({"type": "shell_session_create"}, iteration=1, step_id="battery.shell_session")  # noqa: SLF001
            session_id = ""
            if hasattr(agent.executor.shell, "sessions") and agent.executor.shell.sessions:
                session_id = next(iter(agent.executor.shell.sessions.keys()))
            send = agent.executor._run_action(  # noqa: SLF001
                {"type": "shell_session_send", "session_id": session_id, "command": "python3 -c \"print('battery session ok')\""},
                iteration=1,
                step_id="battery.shell_session",
            )
            close = agent.executor._run_action({"type": "shell_session_close", "session_id": session_id}, iteration=1, step_id="battery.shell_session")  # noqa: SLF001
            ok = (
                bool(create.get("ok"))
                and bool(send.get("ok"))
                and bool(close.get("ok"))
                and "battery session ok" in str(send.get("message", ""))
            )
            return {
                "ok": ok,
                "message": "shell session simulation passed" if ok else "shell session simulation failed",
                "create": create,
                "send": send,
                "close": close,
            }

    def executor_complete_action_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            observation = agent.executor._run_action({"type": "complete", "message": "Step completed."}, iteration=1, step_id="battery.complete")  # noqa: SLF001
            ok = bool(observation.get("ok")) and "Step completed." in str(observation.get("message", ""))
            return {
                "ok": ok,
                "message": "complete action simulation passed" if ok else "complete action simulation failed",
                "observation": observation,
            }

    def provider_limit_snapshot_simulation() -> dict[str, object]:
        prefs = ModelPreferences.default()
        model_snapshot = limit_snapshot_from_message("Claude Sonnet five-hour usage limited until 2026-05-01T19:00.")
        account_snapshot = limit_snapshot_from_message("Too many requests until 2026-05-01T20:05.")
        prefs.set_model_limit_snapshot("claude", model_snapshot)
        prefs.set_account_limit_snapshot("claude", "team", account_snapshot)
        model_limit = dict((prefs.provider_limit_snapshot_by_model or {}).get("claude", {}))
        account_limit = dict((prefs.provider_limit_snapshot_by_account or {}).get(account_key("claude", "team"), {}))
        ok = (
            model_limit.get("status") == "blocked"
            and model_limit.get("reason") == "usage_limit"
            and model_limit.get("blocked_until") == "2026-05-01T19:00"
            and model_limit.get("rate_limit_type") == "five_hour_sonnet"
            and account_limit.get("status") == "blocked"
            and account_limit.get("reason") == "rate_limit"
            and account_limit.get("blocked_until") == "2026-05-01T20:05"
        )
        return {
            "ok": ok,
            "message": "provider limit snapshot simulation passed" if ok else "provider limit snapshot simulation failed",
            "model_limit": model_limit,
            "account_limit": account_limit,
        }

    def executor_write_permission_denied_simulation() -> dict[str, object]:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return {
                "ok": True,
                "message": "write permission denial simulation skipped for root",
                "skipped": True,
                "reason": "root bypasses POSIX mode bits",
            }
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            locked = root / "locked.txt"
            locked.write_text("locked\n", encoding="utf-8")
            locked.chmod(0o400)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            observation = agent.executor._run_action(  # noqa: SLF001
                {"type": "write_file", "path": "locked.txt", "content": "updated\n"},
                iteration=1,
                step_id="battery.write_denied",
            )
            message = str(observation.get("message", ""))
            ok = not bool(observation.get("ok")) and "permission denied" in message.lower()
            return {
                "ok": ok,
                "message": "write permission denial simulation passed" if ok else "write permission denial simulation failed",
                "observation": observation,
            }

    def executor_shell_permission_denied_simulation() -> dict[str, object]:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return {
                "ok": True,
                "message": "shell permission denial simulation skipped for root",
                "skipped": True,
                "reason": "root bypasses POSIX mode bits",
            }
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            locked = root / "locked"
            locked.mkdir()
            locked.chmod(0o500)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            observation = agent.executor._run_action(  # noqa: SLF001
                {"type": "shell", "command": "python3 -c \"from pathlib import Path; Path('locked/x.txt').write_text('x')\""},
                iteration=1,
                step_id="battery.shell_denied",
            )
            message = str(observation.get("message", ""))
            ok = not bool(observation.get("ok")) and "permissionerror" in message.lower()
            return {
                "ok": ok,
                "message": "shell permission denial simulation passed" if ok else "shell permission denial simulation failed",
                "observation": observation,
            }

    def role_runtime_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            prefs = ModelPreferences.default()
            baseline = {
                "status": "approved",
                "source": "battery_simulation",
                "tree": {
                    "nodes": [
                        {
                            "node_id": "management.project_manager",
                            "role_type": "project_manager",
                            "label": "Project Manager",
                            "parent_id": "board.executive",
                            "level": "management",
                            "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                        }
                    ]
                },
                "flow": {"edges": []},
            }
            prefs.set_prince2_role_tree_baseline(baseline)
            prefs.save(config.model_prefs_path)
            handoff = ProjectHandoff.load(config.handoff_path)
            handoff.sync_prince2_role_tree_baseline(baseline)
            rendered = handoff.rendered_prince2_node_runtime()
            ok = "switch_hint=role switch management.project_manager" in rendered and "description=" in rendered
            return {
                "ok": ok,
                "message": "role runtime simulation passed" if ok else "role runtime simulation failed",
                "rendered": rendered,
            }

    def role_runtime_missing_baseline_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            handoff = ProjectHandoff.load(config.handoff_path)
            rendered = handoff.rendered_prince2_node_runtime()
            report = handoff.prince2_node_runtime_report()
            ok = report.get("status") == "missing" and "Approve a role-tree baseline first" in str(report.get("message", ""))
            return {
                "ok": ok,
                "message": "role runtime missing-baseline simulation passed" if ok else "role runtime missing-baseline simulation failed",
                "rendered": rendered,
                "report": report,
            }

    def _seed_role_runtime(config: AgentConfig) -> None:
        prefs = ModelPreferences.default()
        baseline = {
            "status": "approved",
            "source": "battery_simulation",
            "tree": {
                "nodes": [
                    {
                        "node_id": "management.project_manager",
                        "role_type": "project_manager",
                        "label": "Project Manager",
                        "parent_id": "board.executive",
                        "level": "management",
                        "description": "Project Manager role for battery simulation",
                        "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                    }
                ]
            },
            "flow": {"edges": []},
        }
        prefs.set_prince2_role_tree_baseline(baseline)
        prefs.save(config.model_prefs_path)
        handoff = ProjectHandoff.load(config.handoff_path)
        handoff.sync_prince2_role_tree_baseline(baseline)

    def role_shell_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            _seed_role_runtime(config)
            rendered = _project_role_flow._render_prince2_role_node_shell(config, "management.project_manager")
            ok = (
                "PRINCE2 node shell:" in rendered
                and "description=" in rendered
                and "status_legend:" in rendered
                and "switch_hint: role switch management.project_manager" in rendered
            )
            return {
                "ok": ok,
                "message": "role shell simulation passed" if ok else "role shell simulation failed",
                "rendered": rendered,
            }

    def role_switch_agent_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            _seed_role_runtime(config)
            prefs = ModelPreferences.load(config.model_prefs_path)
            input_stream = io.StringIO("q\n")
            output_stream = io.StringIO()
            message = _project_role_flow._guided_role_node_switch_agent(
                prefs=prefs,
                config=config,
                node_id="management.project_manager",
                input_stream=input_stream,
                output_stream=output_stream,
            )
            rendered = output_stream.getvalue()
            ok = "KiloCode-style switch agent:" in rendered and "switch_summary:" in rendered and "Role node model selection cancelled." in message
            return {
                "ok": ok,
                "message": "role switch simulation passed" if ok else "role switch simulation failed",
                "rendered": rendered,
                "response": message,
            }

    def role_message_cycle_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            prefs = ModelPreferences.default()
            baseline = {
                "status": "approved",
                "source": "battery_simulation",
                "tree": {
                    "nodes": [
                        {
                            "node_id": "management.project_manager",
                            "role_type": "project_manager",
                            "label": "Project Manager",
                            "parent_id": "board.executive",
                            "level": "management",
                            "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                        },
                        {
                            "node_id": "delivery.team_manager",
                            "role_type": "team_manager",
                            "label": "Team Manager",
                            "parent_id": "management.project_manager",
                            "level": "delivery",
                            "assignment": {"provider": "claude", "provider_model": "claude-sonnet-4.5"},
                        },
                    ]
                },
                "flow": {
                    "edges": [
                        {
                            "edge_id": "pm-to-team",
                            "source_node": "management.project_manager",
                            "target_node": "delivery.team_manager",
                            "flow_type": "directive",
                            "payload_scope": ["scope"],
                            "expected_evidence": ["plan"],
                            "validation_condition": "team confirmed receipt",
                            "decision_authority": "management.project_manager",
                            "return_path": "delivery.team_manager -> management.project_manager",
                        }
                    ]
                },
            }
            prefs.set_prince2_role_tree_baseline(baseline)
            prefs.save(config.model_prefs_path)
            handoff = ProjectHandoff.load(config.handoff_path)
            handoff.sync_prince2_role_tree_baseline(baseline)
            handoff.set_prince2_node_waiting(
                node_id="delivery.team_manager",
                reason="awaiting instructions",
                wake_triggers=["message_received"],
            )
            message = handoff.send_prince2_node_message(
                source_node="management.project_manager",
                target_node="delivery.team_manager",
                edge_id="pm-to-team",
                payload_scope=["scope"],
                evidence_refs=["plan.md"],
                summary="scope hand-off",
            )
            woke = handoff.wake_prince2_node(node_id="delivery.team_manager", trigger="message_received")
            first_tick = handoff.tick_prince2_node(node_id="delivery.team_manager")
            second_tick = handoff.tick_prince2_node(node_id="delivery.team_manager")
            messages = handoff.prince2_node_messages_report(node_id="delivery.team_manager")
            ok = (
                message.get("status") == "queued"
                and woke.get("state") == "ready"
                and first_tick.get("state") == "running"
                and second_tick.get("state") == "completed"
                and int(messages.get("count", 0) or 0) >= 1
            )
            return {
                "ok": ok,
                "message": "role message cycle simulation passed" if ok else "role message cycle simulation failed",
                "message_record": message,
                "woke": woke,
                "first_tick": first_tick,
                "second_tick": second_tick,
                "messages": messages,
            }

    def role_wait_wake_guard_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            prefs = ModelPreferences.default()
            baseline = {
                "status": "approved",
                "source": "battery_simulation",
                "tree": {
                    "nodes": [
                        {
                            "node_id": "delivery.team_manager",
                            "role_type": "team_manager",
                            "label": "Team Manager",
                            "parent_id": "board.executive",
                            "level": "delivery",
                            "assignment": {"provider": "claude", "provider_model": "claude-sonnet-4.5"},
                        }
                    ]
                },
                "flow": {"edges": []},
            }
            prefs.set_prince2_role_tree_baseline(baseline)
            prefs.save(config.model_prefs_path)
            handoff = ProjectHandoff.load(config.handoff_path)
            handoff.sync_prince2_role_tree_baseline(baseline)
            waiting = handoff.set_prince2_node_waiting(
                node_id="delivery.team_manager",
                reason="awaiting instructions",
                wake_triggers=["message_received"],
            )
            invalid_error = ""
            try:
                handoff.wake_prince2_node(node_id="delivery.team_manager", trigger="not-authorized")
            except ValueError as exc:
                invalid_error = str(exc)
            valid = handoff.wake_prince2_node(node_id="delivery.team_manager", trigger="message_received")
            tick = handoff.tick_prince2_node(node_id="delivery.team_manager")
            ok = (
                waiting.get("state") == "waiting"
                and "not authorized" in invalid_error.lower()
                and valid.get("state") == "ready"
                and tick.get("state") == "completed"
            )
            return {
                "ok": ok,
                "message": "role wait/wake simulation passed" if ok else "role wait/wake simulation failed",
                "waiting": waiting,
                "invalid_error": invalid_error,
                "valid": valid,
                "tick": tick,
            }

    def role_escalation_guard_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            prefs = ModelPreferences.default()
            baseline = {
                "status": "approved",
                "source": "battery_simulation",
                "tree": {
                    "nodes": [
                        {
                            "node_id": "management.project_manager",
                            "role_type": "project_manager",
                            "label": "Project Manager",
                            "parent_id": "board.executive",
                            "level": "management",
                            "tolerance_margin_percent": 25.0,
                            "tolerance_pressure_percent": 42.0,
                            "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                        }
                    ]
                },
                "flow": {"edges": []},
            }
            prefs.set_prince2_role_tree_baseline(baseline)
            prefs.save(config.model_prefs_path)
            handoff = ProjectHandoff.load(config.handoff_path)
            handoff.sync_prince2_role_tree_baseline(baseline)
            tick = handoff.tick_prince2_node(node_id="management.project_manager")
            runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
            nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
            child = next((node for node in nodes if node.get("parent_id") == "management.project_manager"), {})
            ok = (
                tick.get("state") == "escalated"
                and tick.get("spawned_child")
                and child.get("spawn_source") == "escalation"
                and int(child.get("thread_token_count", 0) or 0) > 0
            )
            return {
                "ok": ok,
                "message": "role escalation guard simulation passed" if ok else "role escalation guard simulation failed",
                "tick": tick,
                "spawned_child": child,
            }

    def role_antagonist_guard_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            prefs = ModelPreferences.default()
            baseline = {
                "status": "approved",
                "source": "battery_simulation",
                "tree": {
                    "nodes": [
                        {
                            "node_id": "board.executive",
                            "role_type": "project_board",
                            "label": "Board Executive",
                            "parent_id": None,
                            "level": "board",
                            "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                        }
                    ]
                },
                "flow": {"edges": []},
            }
            prefs.set_prince2_role_tree_baseline(baseline)
            prefs.save(config.model_prefs_path)
            handoff = ProjectHandoff.load(config.handoff_path)
            handoff.sync_prince2_role_tree_baseline(baseline)
            rendered = handoff.rendered_prince2_node_runtime()
            ok = "threat_count=" in rendered
            return {
                "ok": ok,
                "message": "role antagonist guard simulation passed" if ok else "role antagonist guard simulation failed",
                "rendered": rendered,
            }

    def role_devil_advocate_review_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            prefs = ModelPreferences.default()
            baseline = {
                "status": "approved",
                "source": "battery_simulation",
                "tree": {
                    "nodes": [
                        {
                            "node_id": "assurance.project_assurance",
                            "role_type": "project_assurance",
                            "label": "Project Assurance",
                            "parent_id": "board.executive",
                            "level": "assurance",
                            "assignment": {"provider": "openai", "provider_model": "gpt-5.4-nano"},
                        }
                    ]
                },
                "flow": {"edges": []},
            }
            prefs.set_prince2_role_tree_baseline(baseline)
            prefs.save(config.model_prefs_path)
            handoff = ProjectHandoff.load(config.handoff_path)
            handoff.sync_prince2_role_tree_baseline(baseline)
            rendered = _project_role_runtime_views._render_prince2_role_runtime(config)
            ok = "Project Assurance" in rendered and "openai" in rendered
            return {
                "ok": ok,
                "message": "role devil advocate review simulation passed" if ok else "role devil advocate review simulation failed",
                "rendered": rendered,
            }

    def role_unauthorized_edge_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            prefs = ModelPreferences.default()
            baseline = {
                "status": "approved",
                "source": "battery_simulation",
                "tree": {
                    "nodes": [
                        {
                            "node_id": "management.project_manager",
                            "role_type": "project_manager",
                            "label": "Project Manager",
                            "parent_id": "board.executive",
                            "level": "management",
                            "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                        },
                        {
                            "node_id": "delivery.team_manager",
                            "role_type": "team_manager",
                            "label": "Team Manager",
                            "parent_id": "management.project_manager",
                            "level": "delivery",
                            "assignment": {"provider": "claude", "provider_model": "claude-sonnet-4.5"},
                        }
                    ]
                },
                "flow": {
                    "edges": [
                        {
                            "edge_id": "pm-to-team",
                            "source_node": "management.project_manager",
                            "target_node": "delivery.team_manager",
                            "flow_type": "directive",
                            "payload_scope": ["scope"],
                            "expected_evidence": ["plan"],
                            "validation_condition": "team confirmed receipt",
                            "decision_authority": "management.project_manager",
                            "return_path": "delivery.team_manager -> management.project_manager",
                        }
                    ]
                },
            }
            prefs.set_prince2_role_tree_baseline(baseline)
            prefs.save(config.model_prefs_path)
            handoff = ProjectHandoff.load(config.handoff_path)
            handoff.sync_prince2_role_tree_baseline(baseline)
            try:
                result = handoff.send_prince2_node_message(
                    source_node="management.project_manager",
                    target_node="delivery.team_manager",
                    edge_id="missing-edge",
                    payload_scope=["scope"],
                    evidence_refs=["plan.md"],
                    summary="scope hand-off",
                )
            except ValueError as exc:
                result = {"ok": False, "message": str(exc), "error": str(exc)}
            ok = not bool(result.get("ok")) and "authorized" in str(result.get("message", "")).lower()
            return {
                "ok": ok,
                "message": "role unauthorized edge simulation passed" if ok else "role unauthorized edge simulation failed",
                "result": result,
            }

    def action_validation_guard_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            payload = dumps_ascii({"summary": "battery guard", "action": {"type": "wipe_workspace"}})
            parsed = agent.executor._parse_model_json(payload)  # noqa: SLF001
            error = str(parsed.get("error", ""))
            ok = not bool(parsed.get("ok")) and "Unknown destructive action denied" in error
            return {
                "ok": ok,
                "message": "action validation guard simulation passed" if ok else "action validation guard simulation failed",
                "error": error,
            }

    def health_guard_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            agent = Agent(config)
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="battery.health",
                model="local",
                action_type="complete",
                action_signature="battery",
                success=False,
                observation="Exception: health simulation failure",
                error_type="runtime_error",
            )
            memory.record_tool_transcript(
                iteration=1,
                step_id="battery.health",
                tool="shell",
                action_type="shell",
                success=False,
                summary="health probe",
                detail="error: failed health probe",
                duration_ms=1,
                error_type="runtime_error",
            )
            memory.save(config.memory_path)
            report = _status_dashboard_views._health_report(agent, config)
            ok = not report["ready"] and int(report.get("log_errors", {}).get("count", 0) or 0) >= 2
            return {
                "ok": ok,
                "message": "health guard simulation passed" if ok else "health guard simulation failed",
                "health": report,
            }

    def preflight_guard_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            agent = Agent(config)
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="battery.preflight",
                model="local",
                action_type="complete",
                action_signature="battery",
                success=False,
                observation="Traceback: preflight simulation failure",
                error_type="runtime_error",
            )
            memory.save(config.memory_path)
            report = _status_dashboard_views._preflight_report(agent, config)
            remediation_codes = {str(item.get("code")) for item in report.get("remediations", []) if isinstance(item, dict)}
            ok = not report["ready"] and "log_errors" in remediation_codes
            return {
                "ok": ok,
                "message": "preflight guard simulation passed" if ok else "preflight guard simulation failed",
                "preflight": report,
            }

    def log_detection_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="battery.log",
                model="local",
                action_type="complete",
                action_signature="battery",
                success=False,
                observation="Traceback: simulated failure",
                error_type="runtime_error",
            )
            memory.record_tool_transcript(
                iteration=1,
                step_id="battery.log",
                tool="shell",
                action_type="shell",
                success=False,
                summary="run battery",
                detail="traceback observed in log",
                duration_ms=1,
                error_type="runtime_error",
            )
            memory.save(config.memory_path)
            report = _project_handoff_views._log_error_report(config)
            ok = int(report.get("count", 0) or 0) >= 2
            return {
                "ok": ok,
                "message": "log detection simulation passed" if ok else "log detection simulation failed",
                "log_errors": report,
            }

    def git_roundtrip_simulation() -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            (root / "battery_git.txt").write_text("battery\n", encoding="utf-8")
            committed = agent.git.commit_if_changed("battery: git roundtrip")
            status = agent.git.status()
            log = agent.git.log(limit=3)
            ok = committed.ok and status.ok and log.ok
            return {
                "ok": ok,
                "message": "git roundtrip simulation passed" if ok else "git roundtrip simulation failed",
                "commit": committed.stdout.strip() if committed.ok else committed.error,
            }

    simulations.append(_run_simulation("agent_bootstrap", bootstrap_simulation))
    simulations.append(_run_simulation("executor_write_file", executor_write_file_simulation))
    simulations.append(_run_simulation("executor_read_file", executor_read_file_simulation))
    simulations.append(_run_simulation("executor_inspect_file", executor_inspect_file_simulation))
    simulations.append(_run_simulation("executor_search_replace", executor_search_replace_simulation))
    simulations.append(_run_simulation("executor_list_search", executor_list_search_simulation))
    simulations.append(_run_simulation("filesystem_mutation", filesystem_mutation_simulation))
    simulations.append(_run_simulation("executor_shell_command", executor_shell_command_simulation))
    simulations.append(_run_simulation("git_workflow", git_workflow_simulation))
    simulations.append(_run_simulation("executor_shell_session", executor_shell_session_simulation))
    simulations.append(_run_simulation("executor_complete_action", executor_complete_action_simulation))
    simulations.append(_run_simulation("provider_limit_snapshot", provider_limit_snapshot_simulation))
    simulations.append(_run_simulation("executor_write_permission_denied", executor_write_permission_denied_simulation))
    simulations.append(_run_simulation("executor_shell_permission_denied", executor_shell_permission_denied_simulation))
    simulations.append(_run_simulation("role_runtime", role_runtime_simulation))
    simulations.append(_run_simulation("role_runtime_missing_baseline", role_runtime_missing_baseline_simulation))
    simulations.append(_run_simulation("role_shell", role_shell_simulation))
    simulations.append(_run_simulation("role_switch_agent", role_switch_agent_simulation))
    simulations.append(_run_simulation("role_message_cycle", role_message_cycle_simulation))
    simulations.append(_run_simulation("role_wait_wake_guard", role_wait_wake_guard_simulation))
    simulations.append(_run_simulation("role_escalation_guard", role_escalation_guard_simulation))
    simulations.append(_run_simulation("role_antagonist_guard", role_antagonist_guard_simulation))
    simulations.append(_run_simulation("role_devil_advocate_review", role_devil_advocate_review_simulation))
    simulations.append(_run_simulation("role_unauthorized_edge", role_unauthorized_edge_simulation))
    simulations.append(_run_simulation("action_validation_guard", action_validation_guard_simulation))
    simulations.append(_run_simulation("health_guard", health_guard_simulation))
    simulations.append(_run_simulation("preflight_guard", preflight_guard_simulation))
    simulations.append(_run_simulation("log_detection", log_detection_simulation))
    simulations.append(_run_simulation("git_roundtrip", git_roundtrip_simulation))

    failures = [item for item in simulations if not item["ok"]]
    return {
        "command": "battery",
        "ready": not failures,
        "total": len(simulations),
        "passed": len(simulations) - len(failures),
        "failed": len(failures),
        "simulations": simulations,
        "failures": failures,
    }


def _render_battery(config: AgentConfig) -> str:
    report = _battery_report(config)
    lines = [
        "Agent battery:",
        f"- ready: {str(report['ready']).lower()}",
        f"- passed: {report['passed']}/{report['total']}",
    ]
    for item in report["simulations"]:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {item.get('name')}: {str(item.get('ok')).lower()} "
            f"duration_ms={item.get('duration_ms', 0)} message={item.get('message', '')}"
        )
    if report["failures"]:
        lines.append("Failures:")
        for item in report["failures"]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('name')}: {item.get('message', '')}")
    return "\n".join(lines)
