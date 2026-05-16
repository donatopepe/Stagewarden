from __future__ import annotations

from ..config import AgentConfig
from .. import model_views as _model_views
from ..modelprefs import PRINCE2_ROLE_IDS, PRINCE2_ROLE_LABELS
from ..project_handoff import ProjectHandoff
from . import role_flow as _project_role_flow
from ..role_tree import (
    PRINCE2_ROLE_AUTOMATION_RULES,
    PRINCE2_ROLE_SCOPE_DESCRIPTIONS,
    build_prince2_role_flow as _build_prince2_role_flow,
    build_prince2_role_matrix_payload as _build_prince2_role_matrix_payload,
    build_prince2_role_tree_with_tolerance as _build_prince2_role_tree_with_tolerance,
    check_prince2_role_tree as _check_prince2_role_tree,
    render_prince2_role_check as _render_role_check,
    render_prince2_role_flow as _render_role_flow,
    render_prince2_role_matrix as _render_role_matrix,
    render_prince2_role_tree as _render_role_tree,
)


def _main():
    from .. import main as _main_module

    return _main_module


def _prince2_role_domains_report() -> dict[str, object]:
    return {
        "command": "roles domains",
        "rule": "a role-assigned model receives only the context inside its PRINCE2 domain unless escalation changes the active role",
        "roles": [
            {
                "role": role,
                "label": PRINCE2_ROLE_LABELS[role],
                "responsibility": PRINCE2_ROLE_AUTOMATION_RULES.get(role, "controlled project work"),
                "context_scope": PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role, "controlled project work"),
            }
            for role in PRINCE2_ROLE_IDS
        ],
    }


def _render_prince2_role_domains() -> str:
    report = _prince2_role_domains_report()
    lines = ["PRINCE2 role domains:"]
    for item in report["roles"]:
        lines.append(
            f"- {item['label']} ({item['role']}): "
            f"responsibility={item['responsibility']}; "
            f"context_scope={item['context_scope']}"
        )
    lines.append("- rule: a role-assigned model receives only the context inside its PRINCE2 domain unless escalation changes the active role.")
    return "\n".join(lines)


def _prince2_role_tree_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    tolerance_profile = _project_role_flow._project_tolerance_profile(handoff)
    return _build_prince2_role_tree_with_tolerance(
        _model_views._load_model_preferences(config),
        tolerance_profile=tolerance_profile,
        accountable_owner=tolerance_profile.accountable_owner,
    )


def _render_prince2_role_tree(config: AgentConfig) -> str:
    return _render_role_tree(_prince2_role_tree_report(config))


def _prince2_role_check_report(config: AgentConfig) -> dict[str, object]:
    return _check_prince2_role_tree(_model_views._load_model_preferences(config))


def _render_prince2_role_check(config: AgentConfig) -> str:
    return _render_role_check(_prince2_role_check_report(config))


def _prince2_role_flow_report() -> dict[str, object]:
    return _build_prince2_role_flow()


def _render_prince2_role_flow() -> str:
    return _render_role_flow(_prince2_role_flow_report())


def _prince2_role_matrix_report(config: AgentConfig) -> dict[str, object]:
    main = _main()
    prefs = _model_views._load_model_preferences(config)
    handoff = ProjectHandoff.load(config.handoff_path)
    tolerance_profile = _project_role_flow._project_tolerance_profile(handoff)
    tree = _build_prince2_role_tree_with_tolerance(
        prefs,
        tolerance_profile=tolerance_profile,
        accountable_owner=tolerance_profile.accountable_owner,
    )
    return _build_prince2_role_matrix_payload(tree, prefs)


def _render_prince2_role_matrix(config: AgentConfig) -> str:
    return _render_role_matrix(_prince2_role_matrix_report(config))


def _prince2_role_tree_baseline_report(config: AgentConfig) -> dict[str, object]:
    main = _main()
    prefs = _model_views._load_model_preferences(config)
    baseline = dict(prefs.prince2_role_tree_baseline or {})
    return {
        "command": "roles baseline",
        "status": "approved" if baseline else "missing",
        "baseline": baseline,
        "decomposition": baseline.get("decomposition", {}) if isinstance(baseline.get("decomposition"), dict) else {},
        "adaptation": baseline.get("adaptation", {}) if isinstance(baseline.get("adaptation"), dict) else {},
    }


def _render_prince2_role_tree_baseline(config: AgentConfig) -> str:
    report = _prince2_role_tree_baseline_report(config)
    baseline = report["baseline"]
    if not isinstance(baseline, dict) or not baseline:
        return "PRINCE2 role-tree baseline: missing\n- action: run /project start or /roles tree approve"
    check = baseline.get("check", {})
    matrix = baseline.get("matrix", {})
    tree = baseline.get("tree", {})
    local_execution = baseline.get("local_execution", {}) if isinstance(baseline.get("local_execution"), dict) else {}
    decomposition = baseline.get("decomposition", {}) if isinstance(baseline.get("decomposition"), dict) else {}
    adaptation = baseline.get("adaptation", {}) if isinstance(baseline.get("adaptation"), dict) else {}
    nodes = tree.get("nodes", []) if isinstance(tree, dict) else []
    rows = matrix.get("rows", []) if isinstance(matrix, dict) else []
    check_status = check.get("status", "unknown") if isinstance(check, dict) else "unknown"
    lines = [
        "PRINCE2 role-tree baseline:",
        f"- status: {baseline.get('status', 'approved')}",
        f"- approved_at: {baseline.get('approved_at', 'unknown')}",
        f"- source: {baseline.get('source', 'unknown')}",
        f"- check_status: {check_status}",
        f"- nodes: {len(nodes)}",
        f"- matrix_rows: {len(rows)}",
        "- rule: this approved role tree is the governance baseline for future role-routed context handoffs.",
    ]
    if decomposition:
        lines.append("Decomposition:")
        lines.append(f"- policy: {decomposition.get('policy') or 'none'}")
        lines.append(f"- status: {decomposition.get('status') or 'unknown'} score={decomposition.get('score', 0)}")
        lines.append(f"- micro_task_count: {decomposition.get('micro_task_count', 0)}")
    if adaptation:
        lines.append("Adaptation:")
        lines.append(f"- policy: {adaptation.get('policy') or 'none'}")
        lines.append(f"- status: {adaptation.get('status') or 'unknown'}")
        lines.append(f"- reason: {adaptation.get('reason') or 'none'}")
        changed = adaptation.get("changed_fields", [])
        lines.append(f"- changed_fields: {', '.join(changed) if isinstance(changed, list) and changed else 'none'}")
    if local_execution:
        candidates = [item for item in local_execution.get("candidates", []) if isinstance(item, dict)]
        lines.append(
            "- local_execution_candidates: "
            + (", ".join(str(item.get("id", "")) for item in candidates if str(item.get("id", "")).strip()) or "none")
        )
    return "\n".join(lines)


def _delivery_local_fallback_report(config: AgentConfig) -> dict[str, object]:
    baseline = _prince2_role_tree_baseline_report(config).get("baseline", {})
    if not isinstance(baseline, dict) or not baseline:
        return {
            "status": "missing",
            "delivery_nodes": 0,
            "delivery_nodes_with_local_fallback": 0,
            "candidate_ids": [],
            "ready_nodes": [],
            "message": "No approved baseline available.",
        }
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = [item for item in tree.get("nodes", []) if isinstance(item, dict)]
    delivery_nodes = [item for item in nodes if str(item.get("level", "")).startswith("delivery")]
    ready_nodes: list[dict[str, object]] = []
    candidate_ids: list[str] = []
    for node in delivery_nodes:
        node_id = str(node.get("node_id", "")).strip()
        if node_id == "delivery.rollback_lane":
            continue
        node_candidates = [str(item).strip() for item in node.get("local_execution_candidates", []) if str(item).strip()]
        for item in node_candidates:
            if item not in candidate_ids:
                candidate_ids.append(item)
        pools = node.get("assignment_pool", {}) if isinstance(node.get("assignment_pool"), dict) else {}
        fallback_routes = [dict(item) for item in pools.get("fallback", []) if isinstance(item, dict)]
        local_routes = [item for item in fallback_routes if str(item.get("provider", "")).strip() == "local"]
        if local_routes:
            ready_nodes.append(
                {
                    "node_id": node_id,
                    "label": str(node.get("label", node.get("node_id", ""))),
                    "local_candidates": node_candidates,
                    "fallback_models": [
                        str(item.get("provider_model", "")).strip()
                        for item in local_routes
                        if str(item.get("provider_model", "")).strip()
                    ],
                }
            )
    status = "ready" if ready_nodes else ("available" if candidate_ids else "missing")
    message = (
        f"{len(ready_nodes)}/{len(delivery_nodes)} delivery node(s) have preloaded local fallback routes."
        if delivery_nodes
        else "No delivery nodes in the approved baseline."
    )
    return {
        "status": status,
        "delivery_nodes": len(delivery_nodes),
        "delivery_nodes_with_local_fallback": len(ready_nodes),
        "candidate_ids": candidate_ids,
        "ready_nodes": ready_nodes,
        "message": message,
    }


def _prince2_role_tree_baseline_matrix_report(config: AgentConfig) -> dict[str, object]:
    report = _prince2_role_tree_baseline_report(config)
    baseline = report.get("baseline", {})
    matrix = baseline.get("matrix", {}) if isinstance(baseline, dict) else {}
    if not isinstance(matrix, dict) or not matrix:
        return {
            "command": "roles baseline matrix",
            "status": "missing",
            "message": "No approved PRINCE2 role-tree baseline matrix. Run /project start, /roles propose, or /roles tree approve first.",
        }
    payload = dict(matrix)
    payload["command"] = "roles baseline matrix"
    payload["baseline_status"] = report.get("status", "missing")
    return payload


def _render_prince2_role_tree_baseline_matrix(config: AgentConfig) -> str:
    report = _prince2_role_tree_baseline_matrix_report(config)
    if report.get("status") == "missing":
        return str(report.get("message", "No approved PRINCE2 role-tree baseline matrix."))
    return _render_role_matrix(report)


def _render_prince2_role_status_hint(config: AgentConfig) -> str:
    main = _main()
    prefs = _model_views._load_model_preferences(config)
    configured = len(prefs.prince2_roles or {})
    tree_baseline = "approved" if prefs.prince2_role_tree_baseline else "missing"
    if configured == len(PRINCE2_ROLE_IDS):
        return f"- prince2_role_baseline: complete ({configured}/{len(PRINCE2_ROLE_IDS)}); role_tree={tree_baseline}"
    if configured:
        return (
            f"- prince2_role_baseline: partial ({configured}/{len(PRINCE2_ROLE_IDS)}); "
            f"role_tree={tree_baseline}; run /roles setup to complete governance ownership."
        )
    return "- prince2_role_baseline: missing; role_tree=missing; run /project start or /roles setup before controlled delivery."
