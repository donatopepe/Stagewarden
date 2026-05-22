from __future__ import annotations

from ..config import AgentConfig
from .. import model_views as _model_views
from . import model_recommendation as _project_model_recommendation
from . import role_flow as _project_role_flow
from ..modelprefs import PRINCE2_ROLE_IDS, PRINCE2_ROLE_LABELS
from ..project_handoff import ProjectHandoff
from ..roles import PRINCE2_ROLE_AUTOMATION_RULES, PRINCE2_ROLE_SCOPE_DESCRIPTIONS
from ..role_tree import prince2_role_mnemonic, prince2_role_team_name


def _status_views():
    from .. import status_views as status_views_module

    return status_views_module


def _prince2_roles_report(config: AgentConfig) -> dict[str, object]:
    prefs = _model_views._load_model_preferences(config)
    return {
        "command": "roles",
        "roles": [
            {
                "role": role,
                "label": PRINCE2_ROLE_LABELS[role],
                "mnemonic": prince2_role_mnemonic(role),
                "team_name": prince2_role_team_name(role),
                "assignment": dict((prefs.prince2_roles or {}).get(role, {})),
            }
            for role in PRINCE2_ROLE_IDS
        ],
    }


def _prince2_role_context_report(config: AgentConfig, node_id: str) -> dict[str, object]:
    prefs = _model_views._load_model_preferences(config)
    _model_views._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    runtime_report = handoff.prince2_node_runtime_report()
    runtime = runtime_report.get("runtime", {}) if isinstance(runtime_report.get("runtime"), dict) else {}
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    node = next((item for item in nodes if str(item.get("node_id", "")).strip() == node_id), None)
    if node is None:
        return {
            "command": "roles context",
            "status": "missing",
            "node_id": node_id,
            "message": f"Node '{node_id}' not found in PRINCE2 runtime.",
        }
    baseline = handoff.prince2_role_tree_baseline if isinstance(handoff.prince2_role_tree_baseline, dict) else {}
    flow = baseline.get("flow", {}) if isinstance(baseline.get("flow"), dict) else {}
    edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
    incoming = [edge for edge in edges if str(edge.get("target_node", "")).strip() == node_id]
    outgoing = [edge for edge in edges if str(edge.get("source_node", "")).strip() == node_id]
    assignment = dict(node.get("assignment", {})) if isinstance(node.get("assignment"), dict) else {}
    role_type = str(node.get("role_type", "")).strip()
    return {
        "command": "roles context",
        "status": "ok",
        "node_id": node_id,
        "node_label": str(node.get("label", node_id)),
        "role_type": role_type,
        "runtime_state": {
            "state": str(node.get("state", "unknown")),
            "wait_status": str(node.get("wait_status", "none")),
            "wait_reason": node.get("wait_reason"),
            "wake_triggers": list(node.get("wake_triggers", [])),
            "inbox_count": int(node.get("inbox_count", 0) or 0),
            "outbox_count": int(node.get("outbox_count", 0) or 0),
            "transcript_refs": [str(item) for item in node.get("transcript_refs", [])] if isinstance(node.get("transcript_refs", []), list) else [],
        },
        "assignment": assignment,
        "prince2_role_context": {
            "responsibility_domain": str(node.get("responsibility_domain", PRINCE2_ROLE_AUTOMATION_RULES.get(role_type, ""))),
            "context_scope": str(node.get("context_scope", PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role_type, ""))),
            "accountability_boundary": str(node.get("accountability_boundary", "")),
            "delegated_authority": str(node.get("delegated_authority", "")),
            "context_include": list((node.get("context_rule") or {}).get("include", [])) if isinstance(node.get("context_rule"), dict) else [],
            "context_exclude": list((node.get("context_rule") or {}).get("exclude", [])) if isinstance(node.get("context_rule"), dict) else [],
        },
        "communications": {
            "incoming_edges": incoming,
            "outgoing_edges": outgoing,
            "commands": [
                "roles active [--json]",
                "roles control [--json]",
                "roles queues [--json]",
                "roles messages [node_id]",
                "role message <source_node> <target_node> <edge_id> payload=<scope1,scope2>",
                "role wait <node_id> reason=<text_with_underscores> [wake=<trigger1,trigger2>]",
                "role wake <node_id> trigger=<name>",
                "role tick <node_id>",
                "roles tick [max_nodes]",
            ],
        },
        "agent_capabilities": _status_views()._agent_capability_surface_for_node(config),
        "project_context": {
            "task": handoff.task or "none",
            "project_status": handoff.status or "idle",
            "current_step": handoff.current_step_id or "none",
            "current_step_status": handoff.current_step_status or "none",
        },
    }


def _render_prince2_role_context(config: AgentConfig, node_id: str) -> str:
    report = _prince2_role_context_report(config, node_id)
    if report.get("status") != "ok":
        return str(report.get("message", "PRINCE2 role context unavailable."))
    runtime_state = report["runtime_state"]
    role_context = report["prince2_role_context"]
    assignment = report["assignment"]
    comms = report["communications"]
    caps = report["agent_capabilities"]
    lines = [
        "PRINCE2 node AI context:",
        f"- node: {report['node_label']} [{report['node_id']}]",
        f"- role_type: {report['role_type']}",
        f"- state: {runtime_state['state']} wait={runtime_state['wait_status']} inbox={runtime_state['inbox_count']} outbox={runtime_state['outbox_count']}",
        f"- provider: {assignment.get('provider') or 'none'} provider_model={assignment.get('provider_model') or 'none'} account={assignment.get('account') or 'none'}",
        f"- tolerance_margin: {runtime_state.get('tolerance_margin_percent', 'unknown')} pressure={runtime_state.get('tolerance_pressure_percent', 'unknown')} state={runtime_state.get('tolerance_state', runtime_state['state'])}",
        f"- responsibility_domain: {role_context['responsibility_domain']}",
        f"- context_scope: {role_context['context_scope']}",
        f"- accountability_boundary: {role_context['accountability_boundary']}",
        f"- delegated_authority: {role_context['delegated_authority']}",
        f"- context_include: {', '.join(role_context['context_include']) or 'none'}",
        f"- context_exclude: {', '.join(role_context['context_exclude']) or 'none'}",
        f"- wake_triggers: {', '.join(runtime_state['wake_triggers']) or 'none'}",
        f"- incoming_edges: {', '.join(str(edge.get('edge_id')) for edge in comms['incoming_edges']) or 'none'}",
        f"- outgoing_edges: {', '.join(str(edge.get('edge_id')) for edge in comms['outgoing_edges']) or 'none'}",
        f"- agent_tools: {', '.join(caps['shell_operations'] + caps['git_operations'][:2] + ['...'])}",
        f"- file_ops: {', '.join(caps['file_operations'][:6])}, ...",
    ]
    recommendation = _project_model_recommendation._node_model_recommendation(config, _project_role_flow._role_tree_node_record(config, node_id) or {})
    suggested = recommendation.get("suggested", {}) if isinstance(recommendation.get("suggested"), dict) else {}
    lines.append(
        f"- model_recommendation: direction={recommendation.get('direction', 'hold')} "
        f"provider={suggested.get('provider') or 'none'} provider_model={suggested.get('provider_model') or 'none'} "
        f"bucket={suggested.get('bucket', 'none')}"
    )
    lines.append("- communication_commands:")
    for command in comms["commands"]:
        lines.append(f"  {command}")
    lines.append(f"- project_task: {report['project_context']['task']}")
    lines.append(f"- project_status: {report['project_context']['project_status']}")
    lines.append(f"- current_step: {report['project_context']['current_step']} [{report['project_context']['current_step_status']}]")
    return "\n".join(lines)


def _render_prince2_roles(config: AgentConfig) -> str:
    report = _prince2_roles_report(config)
    lines = ["PRINCE2 role assignments:"]
    for item in report["roles"]:
        assignment = item["assignment"]
        if not assignment:
            lines.append(f"- {item['label']} ({item['role']}): unassigned team={item['team_name']} mnemonic={item['mnemonic']}")
            continue
        params = assignment.get("params", {})
        params_text = (
            " params=" + ",".join(f"{key}={value}" for key, value in sorted(params.items()))
            if isinstance(params, dict) and params
            else ""
        )
        lines.append(
            f"- {item['label']} ({item['role']}): mode={assignment.get('mode', 'manual')} "
            f"mnemonic={item['mnemonic']} team={item['team_name']} "
            f"provider={assignment.get('provider', 'unknown')} "
            f"provider_model={assignment.get('provider_model', 'unknown')} "
            f"account={assignment.get('account') or 'none'}"
            f"{params_text} source={assignment.get('source', 'manual')}"
        )
    return "\n".join(lines)
