from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import AgentConfig
from .json_schema_registry import json_schema
from .project_handoff import ProjectHandoff

PROMPT_ROOT = Path(__file__).resolve().parents[1] / ".pi" / "prompts"


def _read_prompt_template(name: str) -> str:
    path = PROMPT_ROOT / f"{name}.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return f"# {name}\n\nTemplate unavailable: {path}"


def _goal_text(handoff: ProjectHandoff) -> str:
    goal = handoff.goal_view()
    objective = str(goal.get("objective") or "").strip()
    if objective:
        return objective
    if handoff.task.strip():
        return handoff.task.strip()
    return ""


def _normalize_task(task: str, handoff: ProjectHandoff) -> str:
    rest = task.removeprefix("goal loop").strip()
    if rest:
        return rest
    return _goal_text(handoff)


def _scope_summary(task: str, handoff: ProjectHandoff) -> dict[str, object]:
    goal = handoff.goal_view()
    objective = _normalize_task(task, handoff)
    brief = dict(handoff.project_brief or {})
    scope = str(brief.get("scope") or "").strip()
    expected_outputs = str(brief.get("expected_outputs") or "").strip()
    constraints = str(brief.get("constraints") or "").strip()
    return {
        "objective": objective,
        "scope": scope or "Create a governed hierarchical goal loop for Stagewarden.",
        "out_of_scope": [
            "Do not remove existing Stagewarden capabilities.",
            "Do not perform gratuitous refactors without a linked change request.",
            "Do not claim wet-run evidence without a real command execution.",
        ],
        "deliverables": [
            "Scope summary",
            "Node graph",
            "Child-node prompts",
            "Execution order",
            "Tolerance matrix",
            "Exception policy",
            "Validation plan",
            "Final report with risks and decisions",
        ],
        "acceptance_criteria": [
            "Root scope is defined before implementation.",
            "Each node has input, output, tests, tolerances, and escalation.",
            "Node communication is structured and reversible decisions are explicit.",
            "TDD gates are present before any non-trivial refactor.",
            "Wet-run evidence is required when the environment allows it.",
            "pi-agent benchmarking is referenced as an explicit learning lane.",
        ],
        "constraints": {
            "existing_goal": goal,
            "constraints": constraints or "Preserve current commands and handoff behavior.",
            "expected_outputs": expected_outputs or "Operational loop blueprint and execution artifacts.",
        },
        "assumptions": [
            "The loop can start from the current task or the persisted goal when no explicit task is supplied.",
            "Prompt templates live under .pi/prompts/ and are discoverable by the local pi CLI.",
        ],
        "risks": [
            "Runtime integration may require additional command wiring beyond prompt templates.",
            "Wet-run coverage can be limited by missing provider or shell capabilities.",
            "Loop fan-out can increase orchestration complexity and validation time.",
        ],
        "open_questions": [
            "How many child nodes should run in parallel in a real execution phase?",
            "Should loop state be persisted automatically or only emitted as a report?",
        ],
    }


_CHILD_NODE_BLUEPRINTS: tuple[dict[str, Any], ...] = (
    {
        "node_id": "root.scope",
        "purpose": "Define scope, out-of-scope, outputs, acceptance criteria, and risk posture.",
        "template": "goal-root",
        "dependencies": [],
        "tests": ["Scope is complete before decomposition begins.", "Open questions are classified by risk and reversibility."],
        "tolerances": {"scope_drift": "none", "ambiguity": "low"},
        "escalation_rule": "Escalate to the user if architecture, safety, or irreversibility is unclear.",
    },
    {
        "node_id": "orchestrator.graph",
        "purpose": "Transform the scope into a graph of work, child nodes, and execution order.",
        "template": "goal-loop-orchestrator",
        "dependencies": ["root.scope"],
        "tests": ["Graph has a root and at least three child nodes.", "Each child node has single responsibility."],
        "tolerances": {"graph_depth": "moderate", "node_count": "configurable"},
        "escalation_rule": "Stop and ask when graph shape changes the safety or delivery strategy.",
    },
    {
        "node_id": "subnode.generator",
        "purpose": "Generate prompts for sub-nodes and attach inputs, outputs, and escalation rules.",
        "template": "subnode-generator",
        "dependencies": ["orchestrator.graph"],
        "tests": ["Every generated sub-node has an explicit prompt and test contract."],
        "tolerances": {"prompt_length": "pragmatic", "missing_contract": "none"},
        "escalation_rule": "Escalate if sub-node prompts would embed unreviewable policy changes.",
    },
    {
        "node_id": "implementation.refactor",
        "purpose": "Apply any needed refactor with TDD before changing behavior.",
        "template": "refactor-complete",
        "dependencies": ["subnode.generator"],
        "tests": ["A failing test exists before the code change.", "Behavior is preserved after refactor."],
        "tolerances": {"regression": "zero", "refactor_scope": "linked-only"},
        "escalation_rule": "Stop if refactor is not justified by a linked goal-loop requirement.",
    },
    {
        "node_id": "validation.wet_run",
        "purpose": "Run real tests and wet-run commands with evidence.",
        "template": "validation-wet-run",
        "dependencies": ["implementation.refactor"],
        "tests": ["Targeted tests fail before the change and pass after it.", "Wet-run evidence is recorded from a real command path."],
        "tolerances": {"dry_run_only": "none", "evidence_gap": "minor if environment-limited"},
        "escalation_rule": "Escalate if wet-run cannot be executed or evidence is missing.",
    },
    {
        "node_id": "governance.tolerance",
        "purpose": "Classify deviations, exceptions, and escalation decisions.",
        "template": "tolerance-exception",
        "dependencies": ["validation.wet_run"],
        "tests": ["Every deviation is classified as low, medium, or high risk.", "Irreversible changes trigger a stop."],
        "tolerances": {"risk": "explicit", "irreversibility": "zero"},
        "escalation_rule": "Ask the user on medium risk; stop on high risk or irreversible changes.",
    },
    {
        "node_id": "communication.bridge",
        "purpose": "Emit structured node-to-node messages and dependency handoffs.",
        "template": "node-communication",
        "dependencies": ["orchestrator.graph", "governance.tolerance"],
        "tests": ["Each message has FROM, TO, TYPE, SUMMARY, ACTIONS REQUIRED, PRIORITY, and TOLERANCE IMPACT."],
        "tolerances": {"message_noise": "low", "missing_fields": "none"},
        "escalation_rule": "Escalate if communication becomes ambiguous or non-reversible.",
    },
    {
        "node_id": "learning.pi",
        "purpose": "Benchmark Stagewarden against pi-agent patterns and adaptation opportunities.",
        "template": "pi-learning-benchmark",
        "dependencies": ["validation.wet_run"],
        "tests": ["Benchmark extracts patterns for prompt templates, skills, extensions, and SDK usage."],
        "tolerances": {"copying": "none", "abstraction_required": "yes"},
        "escalation_rule": "Escalate if a benchmarked pattern would copy behavior instead of abstracting it.",
    },
)


def _child_prompts(task: str, scope_summary: dict[str, object]) -> list[dict[str, object]]:
    prompts: list[dict[str, object]] = []
    objective = str(scope_summary.get("objective") or task).strip()
    for blueprint in _CHILD_NODE_BLUEPRINTS:
        template_text = _read_prompt_template(str(blueprint["template"]))
        prompt = "\n\n".join(
            [
                f"Template: {blueprint['template']}",
                template_text,
                f"Task: {objective}",
                f"Node: {blueprint['node_id']}",
                f"Purpose: {blueprint['purpose']}",
                f"Dependencies: {', '.join(blueprint['dependencies']) or 'none'}",
                f"Tests: {'; '.join(blueprint['tests'])}",
                f"Tolerances: {', '.join(f'{key}={value}' for key, value in blueprint['tolerances'].items())}",
                f"Escalation: {blueprint['escalation_rule']}",
            ]
        )
        prompts.append(
            {
                **blueprint,
                "prompt": prompt,
                "inputs": {
                    "task": objective,
                    "scope_summary": scope_summary,
                },
                "outputs": [
                    "node-specific plan",
                    "structured dependencies",
                    "evidence requirements",
                ],
                "acceptance_criteria": [
                    "The prompt is directly usable for the node.",
                    "The node can generate child prompts when needed.",
                    "The node states when to escalate or stop.",
                ],
            }
        )
    return prompts


def _node_graph(scope_summary: dict[str, object], child_prompts: list[dict[str, object]]) -> dict[str, object]:
    nodes = []
    for idx, child in enumerate(child_prompts, start=1):
        nodes.append(
            {
                "id": child["node_id"],
                "rank": idx,
                "purpose": child["purpose"],
                "depends_on": child["dependencies"],
                "input": child["inputs"],
                "output": child["outputs"],
                "tests": child["tests"],
                "tolerances": child["tolerances"],
                "escalation": child["escalation_rule"],
            }
        )
    return {
        "root": {
            "id": "root.scope",
            "purpose": "Define the task before any refactor or execution.",
            "input": {"task": scope_summary["objective"]},
            "output": ["scope_summary", "acceptance_criteria", "child-node plan"],
        },
        "children": nodes,
        "subnodes": [
            {
                "parent": "subnode.generator",
                "generated_children": [
                    "implementation.refactor",
                    "validation.wet_run",
                    "learning.pi",
                ],
                "communication": "Structured messages only; every dependency and blocker is explicit.",
            }
        ],
    }


def _tolerance_matrix() -> list[dict[str, object]]:
    return [
        {"dimension": "scope drift", "threshold": "none", "action": "stop and re-scope"},
        {"dimension": "refactor without test", "threshold": "none", "action": "write failing test first"},
        {"dimension": "wet-run unavailable", "threshold": "environment-limited only", "action": "record why and separate env from code bug"},
        {"dimension": "communication ambiguity", "threshold": "none", "action": "rewrite structured message or escalate"},
        {"dimension": "irreversible decision", "threshold": "none", "action": "ask the user before continuing"},
        {"dimension": "pi benchmark drift", "threshold": "no copying", "action": "abstract pattern and document trade-offs"},
    ]


def _exception_policy() -> dict[str, object]:
    return {
        "classification": {
            "low": "decide autonomously and annotate",
            "medium": "decide if clearly reversible; otherwise ask the user",
            "high": "stop and ask the user immediately",
        },
        "required_fields": ["cause", "impact", "options", "recommendation", "decision_final"],
        "stop_conditions": [
            "tolerance exceeded",
            "irreversible architecture change",
            "missing wet-run evidence when the environment supports it",
        ],
    }


def _validation_plan(child_prompts: list[dict[str, object]]) -> dict[str, object]:
    return {
        "test_first": [
            "Add a failing test for the new goal-loop command output.",
            "Add a failing schema coverage test for goal loop.",
        ],
        "commands": [
            "pytest tests/test_json_schema_registry.py tests/test_trace_cli.py -q",
            "stagewarden \"goal loop <task>\" --json",
        ],
        "wet_run": [
            "Run the CLI in a temporary workspace and confirm output and schema JSON.",
            "Check that the command render contains scope summary, node graph, validation plan, and final report sections.",
        ],
        "evidence": [
            "pytest output",
            "CLI stdout/stderr from a real invocation",
            "handoff update entries",
        ],
        "residual_risks": [
            "A real multi-session orchestration engine is still not implemented.",
            "Prompt templates are available, but session fan-out remains a future step.",
        ],
        "covered_nodes": [child["node_id"] for child in child_prompts],
    }


def _final_report(scope_summary: dict[str, object], node_graph: dict[str, object], child_prompts: list[dict[str, object]]) -> dict[str, object]:
    return {
        "status": "ready_for_execution",
        "decision": "Proceed with the prompt-backed goal loop and validate with real CLI execution.",
        "risks": scope_summary["risks"],
        "decisions": [
            "Use project-local .pi/prompts templates as the technical benchmark.",
            "Choose a seven-node graph to keep responsibilities single-purpose but complete.",
            "Treat loader integration as a later step unless tests prove the current surface is insufficient.",
        ],
        "node_count": len(node_graph["children"]),
        "prompt_count": len(child_prompts),
    }


def build_goal_loop_report(config: AgentConfig, task: str) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    effective_task = _normalize_task(task, handoff)
    if not effective_task:
        raise ValueError("Usage: goal loop <task>")
    scope_summary = _scope_summary(task, handoff)
    child_prompts = _child_prompts(effective_task, scope_summary)
    node_graph = _node_graph(scope_summary, child_prompts)
    report = {
        "command": "goal loop",
        "schema": json_schema("goal loop"),
        "task": effective_task,
        "scope_summary": scope_summary,
        "node_graph": node_graph,
        "child_prompts": child_prompts,
        "execution_order": [child["node_id"] for child in child_prompts],
        "tolerance_matrix": _tolerance_matrix(),
        "exception_policy": _exception_policy(),
        "validation_plan": _validation_plan(child_prompts),
        "final_report": _final_report(scope_summary, node_graph, child_prompts),
        "template_root": str(PROMPT_ROOT),
    }
    return report


def render_goal_loop_report(report: dict[str, object]) -> str:
    lines: list[str] = ["Goal loop blueprint:"]
    scope = report.get("scope_summary", {})
    if isinstance(scope, dict):
        lines.append(f"- objective: {scope.get('objective', '')}")
        lines.append(f"- scope: {scope.get('scope', '')}")
        lines.append("- out_of_scope:")
        for item in scope.get("out_of_scope", []) if isinstance(scope.get("out_of_scope"), list) else []:
            lines.append(f"  - {item}")
        lines.append("- acceptance_criteria:")
        for item in scope.get("acceptance_criteria", []) if isinstance(scope.get("acceptance_criteria"), list) else []:
            lines.append(f"  - {item}")
    lines.append("")
    lines.append("Node graph:")
    node_graph = report.get("node_graph", {})
    if isinstance(node_graph, dict):
        root = node_graph.get("root", {})
        if isinstance(root, dict):
            lines.append(f"- root: {root.get('id')} :: {root.get('purpose')}")
        for node in node_graph.get("children", []) if isinstance(node_graph.get("children"), list) else []:
            if not isinstance(node, dict):
                continue
            lines.append(f"- {node.get('id')}: {node.get('purpose')} (depends_on={', '.join(node.get('depends_on', [])) or 'none'})")
    lines.append("")
    lines.append("Child prompts:")
    for child in report.get("child_prompts", []) if isinstance(report.get("child_prompts"), list) else []:
        if not isinstance(child, dict):
            continue
        lines.append(f"- {child.get('node_id')}: {child.get('purpose')}")
    lines.append("")
    lines.append("Execution order:")
    order = report.get("execution_order", []) if isinstance(report.get("execution_order"), list) else []
    for index, node_id in enumerate(order, start=1):
        lines.append(f"- {index}. {node_id}")
    lines.append("")
    lines.append("Tolerance matrix:")
    for row in report.get("tolerance_matrix", []) if isinstance(report.get("tolerance_matrix"), list) else []:
        if not isinstance(row, dict):
            continue
        lines.append(f"- {row.get('dimension')}: threshold={row.get('threshold')} action={row.get('action')}")
    lines.append("")
    lines.append("Exception policy:")
    policy = report.get("exception_policy", {})
    if isinstance(policy, dict):
        for key, value in policy.items():
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("Validation plan:")
    validation = report.get("validation_plan", {})
    if isinstance(validation, dict):
        for key, value in validation.items():
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("Final report:")
    final_report = report.get("final_report", {})
    if isinstance(final_report, dict):
        for key, value in final_report.items():
            lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def goal_loop_status_report(config: AgentConfig) -> dict[str, object]:
    """Report current goal-loop execution state from handoff."""
    handoff = ProjectHandoff.load(config.handoff_path)
    entries = [e for e in handoff.entries if e.phase.startswith("goal_loop_")]
    latest_goal_loop_entries = entries[-10:] if entries else []
    # Build node status summary from entries
    node_statuses: dict[str, str] = {}
    for entry in entries:
        details = entry.details if isinstance(entry.details, dict) else {}
        node_id = details.get("node_id", "")
        status = details.get("status", "")
        if node_id and status:
            node_statuses[node_id] = status
    return {
        "command": "goal loop status",
        "schema": json_schema("goal loop"),
        "running": any(e.phase == "goal_loop_start" for e in entries) and not any(e.phase == "goal_loop_end" for e in entries),
        "completed": any(e.phase == "goal_loop_end" for e in entries),
        "latest_phase": entries[-1].phase if entries else "idle",
        "latest_summary": entries[-1].summary if entries else "",
        "node_statuses": node_statuses,
        "total_goal_loop_actions": len(entries),
    }


def render_goal_loop_status(report: dict[str, object]) -> str:
    lines = ["Goal loop status:"]
    lines.append(f"- running: {report.get('running', False)}")
    lines.append(f"- completed: {report.get('completed', False)}")
    lines.append(f"- latest_phase: {report.get('latest_phase', 'idle')}")
    lines.append(f"- latest_summary: {report.get('latest_summary', '')}")
    lines.append("")
    lines.append("Node statuses:")
    node_statuses = report.get("node_statuses", {})
    if isinstance(node_statuses, dict) and node_statuses:
        for node_id, status in node_statuses.items():
            lines.append(f"- {node_id}: {status}")
    else:
        lines.append("  (no goal loop nodes recorded yet)")
    lines.append("")
    lines.append(f"Total goal loop actions: {report.get('total_goal_loop_actions', 0)}")
    return "\n".join(lines)
