from __future__ import annotations

from ..config import AgentConfig
from ..project_handoff import ProjectHandoff
from . import role_tree_views as _project_role_tree_views


def _main():
    from .. import main as _main_module
    return _main_module


def _prince2_role_runtime_report(config: AgentConfig) -> dict[str, object]:
    main = _main()
    prefs = main._load_model_preferences(config)
    main._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.prince2_node_runtime_report()


def _render_prince2_role_runtime(config: AgentConfig) -> str:
    main = _main()
    prefs = main._load_model_preferences(config)
    main._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.rendered_prince2_node_runtime()


def _prince2_role_active_report(config: AgentConfig) -> dict[str, object]:
    main = _main()
    prefs = main._load_model_preferences(config)
    main._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.prince2_node_active_report()


def _render_prince2_role_active(config: AgentConfig) -> str:
    main = _main()
    prefs = main._load_model_preferences(config)
    main._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.rendered_prince2_node_active()


def _prince2_role_queue_report(config: AgentConfig) -> dict[str, object]:
    main = _main()
    prefs = main._load_model_preferences(config)
    main._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.prince2_node_queue_report()


def _render_prince2_role_queues(config: AgentConfig) -> str:
    main = _main()
    prefs = main._load_model_preferences(config)
    main._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.rendered_prince2_node_queues()


def _prince2_role_control_report(config: AgentConfig) -> dict[str, object]:
    main = _main()
    prefs = main._load_model_preferences(config)
    main._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    report = handoff.prince2_node_control_report()
    report["local_fallback"] = _project_role_tree_views._delivery_local_fallback_report(config)
    return report


def _render_prince2_role_control(config: AgentConfig) -> str:
    main = _main()
    report = _prince2_role_control_report(config)
    if report["status"] == "missing":
        return "PRINCE2 control view: missing\n- action: run /project start, /roles tree approve, or /project tree approve first."
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    queue_summary = report.get("queue_summary", {}) if isinstance(report.get("queue_summary"), dict) else {}
    local_fallback = report.get("local_fallback", {}) if isinstance(report.get("local_fallback"), dict) else {}
    lines = [
        "PRINCE2 control view:",
        f"- board_signal: {decision.get('board_signal', 'unknown')} next_action={decision.get('next_action', 'unknown')}",
        f"- reason: {decision.get('reason', 'none')}",
        f"- nodes: {summary.get('nodes', 0)} active={report.get('active_nodes', 0)} completed={report.get('completed_nodes', 0)}",
        f"- waiting: {report.get('waiting_nodes', 0)} blocked={report.get('blocked_nodes', 0)} escalated={report.get('escalated_nodes', 0)}",
        f"- queues: inbox_total={queue_summary.get('inbox_total', 0)} outbox_total={queue_summary.get('outbox_total', 0)} inbox_nodes={report.get('queued_inbox_nodes', 0)}",
        (
            "- local_fallback: "
            f"status={local_fallback.get('status', 'missing')} "
            f"ready_nodes={local_fallback.get('delivery_nodes_with_local_fallback', 0)}/{local_fallback.get('delivery_nodes', 0)} "
            f"candidates={','.join(local_fallback.get('candidate_ids', [])) if local_fallback.get('candidate_ids') else 'none'}"
        ),
    ]
    critical_nodes = [item for item in report.get("critical_nodes", []) if isinstance(item, dict)]
    if critical_nodes:
        lines.append("- critical_nodes:")
        for node in critical_nodes:
            lines.append(
                f"  - {node.get('label')} [{node.get('node_id')}]: severity={node.get('severity')} "
                f"state={node.get('state')} wait={node.get('wait_status')} "
                f"inbox={node.get('inbox_count')} outbox={node.get('outbox_count')} "
                f"reasons={'; '.join(str(item) for item in node.get('reasons', []))}"
            )
            node_record = main._role_tree_node_record(config, str(node.get("node_id", "")))
            if node_record:
                recommendation = main._node_model_recommendation(config, node_record)
                suggested = recommendation.get("suggested", {}) if isinstance(recommendation.get("suggested"), dict) else {}
                lines.append(
                    f"    model_recommendation: direction={recommendation.get('direction', 'hold')} "
                    f"provider={suggested.get('provider') or 'none'} provider_model={suggested.get('provider_model') or 'none'} "
                    f"bucket={suggested.get('bucket', 'none')}"
                )
                lines.append(f"    switch_hint: role switch {node_record.get('node_id', node.get('node_id', 'unknown'))}")
    else:
        lines.append("- critical_nodes: none")
    return "\n".join(lines)


def _prince2_role_messages_report(config: AgentConfig, node_id: str | None = None) -> dict[str, object]:
    main = _main()
    prefs = main._load_model_preferences(config)
    main._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.prince2_node_messages_report(node_id=node_id)


def _render_prince2_role_messages(config: AgentConfig, node_id: str | None = None) -> str:
    main = _main()
    prefs = main._load_model_preferences(config)
    main._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    return handoff.rendered_prince2_node_messages(node_id=node_id)
