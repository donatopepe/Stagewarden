"""Stagewarden goal loop orchestrator for multi-node, hierarchical execution."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import AgentConfig
from .project_handoff import ProjectHandoff
from .textcodec import utc_now
from .goal_loop_views import build_goal_loop_report, _read_prompt_template

# ── execution mode ──────────────────────────────────────────────────────────
EXECUTION_MODE_MOCK = "mock"
EXECUTION_MODE_AUTO = "auto"       # try pi, fall back to mock
EXECUTION_MODE_PI = "pi"           # fail if pi not available
_AVAILABLE_PI: bool | None = None  # cached detection

def _pi_available() -> bool:
    global _AVAILABLE_PI
    if _AVAILABLE_PI is not None:
        return _AVAILABLE_PI
    _AVAILABLE_PI = shutil.which("pi") is not None
    return _AVAILABLE_PI


# ── decision / autonomy helpers ──────────────────────────────────────────────

DecisionLevel = str  # "autonomous" | "report" | "ask_user" | "stop"

def classify_decision(description: str, impact: str) -> tuple[DecisionLevel, str]:
    """Classify a decision per autonomy-decision template."""
    low_impact = ("local", "cosmetic", "style", "minor", "reversible")
    medium_impact = ("medium", "moderate", "config", "scoped")
    high_impact = ("architecture", "security", "compatibility", "data",
                   "fundamental_test", "irreversible", "safety")

    text = f"{description} {impact}".lower()
    for token in high_impact:
        if token in text:
            return ("ask_user", f"High-impact / irreversible: '{token}' detected. Ask the user.")
    for token in medium_impact:
        if token in text:
            return ("report", f"Medium impact '{token}' – report and decide autonomously.")
    for token in low_impact:
        if token in text:
            return ("autonomous", f"Low impact / reversible – decide autonomously.")
    return ("autonomous", "No clear risk signal – decide autonomously (default).")


def check_tolerance_violation(tolerances: dict[str, str],
                              actual: dict[str, str]) -> tuple[str, str | None]:
    """Return ('ok', None) or ('violation', reason)."""
    for key, threshold in tolerances.items():
        value = actual.get(key, "")
        if not value or value == threshold:
            continue
        # If threshold is "none", any non-empty value is a violation
        if threshold == "none":
            return ("violation", f"Tolerance '{key}' threshold=none but got '{value}'")
    return ("ok", None)


# ── data classes ─────────────────────────────────────────────────────────────

@dataclass
class NodeState:
    node_id: str
    purpose: str
    prompt_template_name: str
    prompt: str
    inputs: list[str]
    outputs: list[str]
    acceptance_criteria: list[str]
    tests: list[str]
    tolerances: dict[str, str]
    escalation_rule: str
    dependencies: list[str]
    status: str = "pending"
    messages_received: list[dict[str, Any]] = field(default_factory=list)
    messages_sent: list[dict[str, Any]] = field(default_factory=list)
    session_id: str | None = None
    last_run_at: str | None = None
    output_summary: str | None = None
    error_message: str | None = None
    pi_stdout: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "purpose": self.purpose,
            "status": self.status,
            "dependencies": list(self.dependencies),
            "tolerances": dict(self.tolerances) if isinstance(self.tolerances, dict) else {},
            "output_summary": self.output_summary or "",
            "error_message": self.error_message,
            "pi_stdout": self.pi_stdout[:500] if self.pi_stdout else "",
            "messages_sent": [
                {"FROM": m.get("FROM"), "TO": m.get("TO"),
                 "TYPE": m.get("TYPE"), "SUMMARY": m.get("SUMMARY")}
                for m in (self.messages_sent or [])
            ],
        }


@dataclass
class MessageBus:
    messages: list[dict[str, Any]] = field(default_factory=list)

    def send_message(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def get_messages_for_node(self, node_id: str) -> list[dict[str, Any]]:
        return [msg for msg in self.messages if msg.get("TO") == node_id]


# ── orchestrator ─────────────────────────────────────────────────────────────

class GoalLoopOrchestrator:
    def __init__(self, config: AgentConfig, task: str,
                 execution_mode: str | None = None,
                 json_mode: bool = False):
        if execution_mode is None:
            execution_mode = os.environ.get("STAGEWARDEN_GOAL_LOOP_EXECUTION_MODE",
                                            EXECUTION_MODE_AUTO)
        self.config = config
        self.task = task
        self.execution_mode = execution_mode
        self.json_mode = json_mode
        self.handoff = ProjectHandoff.load(config.handoff_path)
        self.blueprint = build_goal_loop_report(config, task)
        self.nodes: dict[str, NodeState] = {}
        self.message_bus = MessageBus()
        self.current_iteration = 0
        self._initialize_nodes()

    # ── initialisation ──────────────────────────────────────────────────────

    def _initialize_nodes(self) -> None:
        for child in self.blueprint.get("child_prompts", []):
            node_id = child["node_id"]
            raw_tols = child.get("tolerances", {})
            tolerances_parsed = (
                {str(k): str(v) for k, v in raw_tols.items()}
                if isinstance(raw_tols, dict) else {}
            )
            self.nodes[node_id] = NodeState(
                node_id=node_id,
                purpose=child["purpose"],
                prompt_template_name=child.get("template", ""),
                prompt=self._generate_node_prompt(child),
                inputs=child.get("inputs", []),
                outputs=child.get("outputs", []),
                acceptance_criteria=child.get("acceptance_criteria", []),
                tests=child.get("tests", []),
                tolerances=tolerances_parsed,
                escalation_rule=child.get("escalation_rule", ""),
                dependencies=child.get("dependencies", []),
            )

    def _generate_node_prompt(self, child: dict[str, Any]) -> str:
        template = _read_prompt_template(child.get("template", ""))
        raw_tols = child.get("tolerances", {})
        tolerances_flat = (
            ", ".join(f"{k}={v}" for k, v in raw_tols.items())
            if isinstance(raw_tols, dict) else str(raw_tols)
        )
        return (
            f"{template}\n\n"
            f"Task: {self.task}\n\n"
            f"Node: {child['node_id']}\n\n"
            f"Purpose: {child['purpose']}\n\n"
            f"Dependencies: {', '.join(child.get('dependencies', []))}\n\n"
            f"Tests: {'; '.join(child.get('tests', []))}\n\n"
            f"Tolerances: {tolerances_flat}\n\n"
            f"Escalation: {child.get('escalation_rule', '')}"
        )

    # ── dependency resolution ───────────────────────────────────────────────

    def _get_ready_nodes(self) -> list[NodeState]:
        ready: list[NodeState] = []
        for node_id, node in self.nodes.items():
            if node.status in ("pending", "blocked"):
                all_deps_ok = all(
                    self.nodes[dep_id].status == "completed"
                    for dep_id in node.dependencies
                )
                if all_deps_ok:
                    ready.append(node)
        return ready

    # ── autonomy / tolerance gates ──────────────────────────────────────────

    def _autonomy_gate(self, node_state: NodeState) -> tuple[bool, str | None]:
        """Classify the node execution decision.
        Returns (proceed, reason).
        In interactive mode (not json_mode), prompts user for high-risk decisions."""
        level, reason = classify_decision(node_state.purpose, "medium")
        if level == "stop":
            node_state.status = "blocked"
            node_state.error_message = reason
            return (False, reason)
        if level == "ask_user":
            sys.stderr.write(f"[goal-loop] autonomy gate: {reason}\n")
            if not self.json_mode:
                # Interactive prompt
                try:
                    answer = input(f"High-risk decision for node '{node_state.node_id}':\n"
                                   f"  {reason}\n"
                                   f"  Proceed? [y/N] ")
                    if answer.strip().lower() in ("y", "yes"):
                        return (True, reason)
                    sys.stderr.write(f"[goal-loop] user declined node {node_state.node_id}\n")
                    node_state.status = "blocked"
                    node_state.error_message = "User declined high-risk execution."
                    return (False, "User declined.")
                except (EOFError, KeyboardInterrupt):
                    sys.stderr.write(f"[goal-loop] no user input, blocking node {node_state.node_id}\n")
                    node_state.status = "blocked"
                    node_state.error_message = "No user input for high-risk decision."
                    return (False, "No user input.")
            # JSON mode: record but proceed
            sys.stderr.write(f"[goal-loop] autonomy gate (proceeding): {reason}\n")
            return (True, reason)
        if level == "report":
            sys.stderr.write(f"[goal-loop] autonomy gate: {reason}\n")
            return (True, reason)
        return (True, None)

    def _tolerance_gate(self, node_state: NodeState) -> tuple[bool, str | None]:
        """Check tolerances after execution.
        Returns (passes, reason)."""
        if node_state.status != "completed":
            return (True, None)
        actual = {"output_summary": node_state.output_summary or ""}
        outcome, reason = check_tolerance_violation(node_state.tolerances, actual)
        if outcome == "violation":
            node_state.status = "blocked"
            node_state.error_message = reason
            return (False, reason)
        return (True, None)

    # ── execution ───────────────────────────────────────────────────────────

    def _execute_node(self, node_state: NodeState) -> None:
        self.current_iteration += 1
        node_state.status = "running"
        node_state.last_run_at = utc_now()
        node_state.session_id = str(uuid.uuid4())

        # autonomy gate before execution
        proceed, reason = self._autonomy_gate(node_state)
        if not proceed:
            self._record_node_execution_to_handoff(node_state)
            return

        # execute
        if self.execution_mode == EXECUTION_MODE_MOCK:
            result = self._mock_execution(node_state.node_id)
        elif self.execution_mode == EXECUTION_MODE_PI:
            result = self._pi_execution(node_state)
        else:  # auto
            if _pi_available():
                result = self._pi_execution(node_state)
            else:
                sys.stderr.write(
                    "[goal-loop] pi not available, falling back to mock execution. "
                    "Install pi for real AI-powered node execution.\n"
                )
                result = self._mock_execution(node_state.node_id)

        # apply result
        if result.get("ok"):
            node_state.status = "completed"
            node_state.output_summary = result.get("summary", "Node completed.")
            for msg in result.get("messages", []):
                self.message_bus.send_message(msg)
                node_state.messages_sent.append(msg)
        else:
            node_state.status = "blocked"
            node_state.error_message = result.get("error", "Node execution failed.")

        # tolerance gate after execution
        passes, tol_reason = self._tolerance_gate(node_state)
        if not passes:
            sys.stderr.write(f"[goal-loop] tolerance violation: {tol_reason}\n")

        self._record_node_execution_to_handoff(node_state)

    def _mock_execution(self, node_id: str) -> dict[str, Any]:
        responses = {
            "root.scope": {
                "ok": True, "summary": "Root scope defined.",
                "messages": [{"FROM": "root.scope", "TO": "orchestrator.graph",
                              "TYPE": "status", "SUMMARY": "Scope defined",
                              "PRIORITY": "low", "TOLERANCE IMPACT": "none"}],
            },
            "orchestrator.graph": {
                "ok": True, "summary": "Node graph created.",
                "messages": [{"FROM": "orchestrator.graph", "TO": "subnode.generator",
                              "TYPE": "status", "SUMMARY": "Graph created",
                              "PRIORITY": "low", "TOLERANCE IMPACT": "none"}],
            },
            "subnode.generator": {
                "ok": True, "summary": "Subnode prompts generated.",
                "messages": [{"FROM": "subnode.generator", "TO": "implementation.refactor",
                              "TYPE": "status", "SUMMARY": "Prompts generated",
                              "PRIORITY": "low", "TOLERANCE IMPACT": "none"}],
            },
            "implementation.refactor": {
                "ok": True, "summary": "Refactoring complete with TDD.",
                "messages": [{"FROM": "implementation.refactor", "TO": "validation.wet_run",
                              "TYPE": "status", "SUMMARY": "Refactoring done",
                              "PRIORITY": "low", "TOLERANCE IMPACT": "none"}],
            },
            "validation.wet_run": {
                "ok": True, "summary": "Wet-run validation passed.",
                "messages": [{"FROM": "validation.wet_run", "TO": "governance.tolerance",
                              "TYPE": "status", "SUMMARY": "Validation passed",
                              "PRIORITY": "low", "TOLERANCE IMPACT": "none"}],
            },
            "governance.tolerance": {
                "ok": True, "summary": "Tolerance check passed.",
                "messages": [{"FROM": "governance.tolerance", "TO": "communication.bridge",
                              "TYPE": "status", "SUMMARY": "Tolerances OK",
                              "PRIORITY": "low", "TOLERANCE IMPACT": "none"}],
            },
            "communication.bridge": {
                "ok": True, "summary": "Structured messages delivered.",
                "messages": [{"FROM": "communication.bridge", "TO": "learning.pi",
                              "TYPE": "status", "SUMMARY": "Messages routed",
                              "PRIORITY": "low", "TOLERANCE IMPACT": "none"}],
            },
            "learning.pi": {
                "ok": True, "summary": "pi benchmark compiled.",
                "messages": [],
            },
        }
        return responses.get(node_id,
                             {"ok": True, "summary": f"Node {node_id} completed.",
                              "messages": []})

    def _pi_execution(self, node_state: NodeState) -> dict[str, Any]:
        """Execute a node via `pi --print --no-tools --no-session @file`."""
        pi_bin = shutil.which("pi")
        if not pi_bin:
            return {"ok": False, "error": "pi executable not found", "messages": []}

        prompt = node_state.prompt
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md',
                                             delete=False, encoding='utf-8') as f:
                f.write(prompt)
                tmp_path = f.name
            proc = subprocess.run(
                [pi_bin, "--print", "--no-tools", "--no-session",
                 f"@{tmp_path}"],
                capture_output=True, text=True,
                timeout=self.config.model_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False,
                    "error": f"pi execution timed out ({self.config.model_timeout_seconds}s)",
                    "messages": []}
        except OSError as exc:
            return {"ok": False, "error": f"pi execution failed: {exc}",
                    "messages": []}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        node_state.pi_stdout = stdout[:2000]

        if proc.returncode != 0:
            return {"ok": False,
                    "error": f"pi exited with code {proc.returncode}: {stderr[:500]}",
                    "messages": []}

        # Parse JSON from stdout
        import re as _re
        # Try 1: full stdout as JSON
        for candidate in (stdout,):
            try:
                data = __import__("json").loads(candidate)
                if isinstance(data, dict) and "summary" in data:
                    return {
                        "ok": True,
                        "summary": data.get("summary", "Node executed via pi."),
                        "messages": data.get("messages", []),
                        "output": data.get("output", ""),
                    }
            except (ValueError, TypeError):
                pass
        # Try 2: find JSON object via regex
        match = _re.search(r'\{.*\}', stdout, _re.DOTALL)
        if match:
            try:
                data = __import__("json").loads(match.group(0))
                if isinstance(data, dict):
                    return {
                        "ok": True,
                        "summary": data.get("summary", stdout[:200]),
                        "messages": data.get("messages", []),
                        "output": data.get("output", stdout),
                    }
            except (ValueError, TypeError):
                pass
        # Fallback: treat raw stdout as summary
        return {
            "ok": True,
            "summary": stdout[:500],
            "messages": [],
            "output": stdout,
        }

    # ── handoff ─────────────────────────────────────────────────────────────

    def _record_node_execution_to_handoff(self, node_state: NodeState) -> None:
        self.handoff.record_action(
            phase=f"goal_loop_node_{node_state.status}",
            task=self.task,
            summary=f"Node {node_state.node_id} {node_state.status}.",
            details=node_state.as_dict(),
        )
        self.handoff.save(self.config.handoff_path)

    # ── main loop ───────────────────────────────────────────────────────────

    def run_loop(self) -> dict[str, Any]:
        self.handoff.record_action(
            phase="goal_loop_start",
            task=self.task,
            summary="Goal loop initiated.",
            details={"objective":
                     self.blueprint.get("scope_summary", {}).get("objective",
                                                                  self.task)},
        )
        self.handoff.save(self.config.handoff_path)

        max_iterations = 10
        for _ in range(max_iterations):
            ready_nodes = self._get_ready_nodes()
            if not ready_nodes:
                if all(n.status == "completed"
                       for n in self.nodes.values()):
                    break
                sys.stderr.write("[goal-loop] stalled – no ready nodes.\n")
                self.handoff.record_action(
                    phase="goal_loop_stalled",
                    task=self.task,
                    summary="Goal loop stalled.",
                    details={"node_statuses":
                             {nid: n.status
                              for nid, n in self.nodes.items()}},
                )
                self.handoff.save(self.config.handoff_path)
                break

            # Execute ready nodes in parallel if they have no cross-dependency
            with ThreadPoolExecutor(max_workers=min(len(ready_nodes), 4)) as pool:
                fut_to_node = {pool.submit(self._execute_node, n): n
                               for n in ready_nodes}
                for fut in as_completed(fut_to_node):
                    n = fut_to_node[fut]
                    try:
                        fut.result()
                    except Exception as exc:
                        sys.stderr.write(
                            f"[goal-loop] node {n.node_id} raised: {exc}\n"
                        )
                        n.status = "blocked"
                        n.error_message = str(exc)
                        self._record_node_execution_to_handoff(n)

            if all(n.status == "completed"
                   for n in self.nodes.values()):
                break
        else:
            sys.stderr.write(
                f"[goal-loop] max iterations ({max_iterations}) reached.\n"
            )
            self.handoff.record_action(
                phase="goal_loop_max_iterations",
                task=self.task,
                summary=f"Reached max iterations ({max_iterations}).",
                details={"node_statuses":
                         {nid: n.status for nid, n in self.nodes.items()}},
            )
            self.handoff.save(self.config.handoff_path)

        final_status = (
            "completed"
            if all(n.status == "completed" for n in self.nodes.values())
            else "failed"
        )
        self.handoff.record_action(
            phase="goal_loop_end",
            task=self.task,
            summary=f"Goal loop {final_status}.",
            details={"final_status": final_status,
                     "node_statuses":
                     {nid: n.status for nid, n in self.nodes.items()}},
        )
        self.handoff.save(self.config.handoff_path)

        return {
            "final_status": final_status,
            "node_statuses": {nid: n.status for nid, n in self.nodes.items()},
            "node_details": {nid: n.as_dict() for nid, n in self.nodes.items()},
            "report": self.blueprint,
        }


# ── render ───────────────────────────────────────────────────────────────────

def render_goal_loop_execution_report(report: dict[str, Any]) -> str:
    lines = ["Goal loop execution report:"]
    lines.append(f"- final_status: {report.get('final_status', 'unknown')}")
    node_statuses = report.get("node_statuses", {})
    if isinstance(node_statuses, dict) and node_statuses:
        lines.append("Node statuses:")
        for node_id, status in node_statuses.items():
            lines.append(f"  - {node_id}: {status}")
    node_details = report.get("node_details", {})
    if isinstance(node_details, dict) and node_details:
        lines.append("")
        lines.append("Node details:")
        for node_id, detail in node_details.items():
            if not isinstance(detail, dict):
                continue
            lines.append(
                f"  - {node_id}: status={detail.get('status')}, "
                f"output={detail.get('output_summary', '')}"
            )
            msgs = detail.get("messages_sent", [])
            if msgs:
                lines.append("    messages sent:")
                for m in msgs:
                    lines.append(
                        f"      {m.get('FROM')} -> {m.get('TO')}"
                        f" [{m.get('TYPE')}]: {m.get('SUMMARY')}"
                    )
    return "\n".join(lines)
