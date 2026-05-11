from __future__ import annotations

from ..agent import Agent
from ..config import AgentConfig
from ..project_handoff import ProjectHandoff


def _main():
    from .. import main as _main_module

    return _main_module


def _project_design_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    handoff = ProjectHandoff.load(config.handoff_path)
    prefs = main._load_model_preferences(config)
    runtime = main.detect_runtime_capabilities()
    shell_backend = main._shell_backend_report(config)
    provider_limits = main._provider_limit_status_report(agent, config)
    permissions = main._permissions_report(config)
    role_check = main._prince2_role_check_report(config)
    baseline = main._prince2_role_tree_baseline_report(config)
    focus = main._focus_snapshot(agent, config)

    enabled_providers = [item["provider"] for item in provider_limits["providers"] if item["enabled"]]
    active_accounts = {
        provider: account
        for provider, account in (prefs.active_account_by_model or {}).items()
        if account
    }
    blocked_providers = [
        {
            "provider": item["provider"],
            "blocked_until": item["blocked_until"],
            "reason": item["last_error_reason"],
        }
        for item in provider_limits["providers"]
        if item["blocked_until"]
    ]
    capability_spec = {
        "workspace": str(config.workspace_root),
        "os_family": str(runtime.get("os_family", "unknown")),
        "platform_release": str(runtime.get("platform_release", "unknown")),
        "architecture": str(runtime.get("platform_machine", "unknown")),
        "default_shell": str(runtime.get("default_shell") or "none"),
        "recommended_shell": str(runtime.get("recommended_shell", "unknown")),
        "shell_backend": {
            "configured": shell_backend["configured"],
            "selected": shell_backend["selected"] or "none",
            "executable": shell_backend["executable"] or "none",
        },
        "capabilities": {
            "shell": True,
            "files": True,
            "git": True,
            "web_research": True,
            "download": True,
            "compression": True,
            "wet_run_required": True,
        },
        "permission_mode": permissions["effective"]["mode"],
        "enabled_providers": enabled_providers,
        "active_accounts": active_accounts,
        "blocked_providers": blocked_providers,
        "preferred_provider": prefs.preferred_model or "automatic",
    }
    project_spec = {
        "task": handoff.task or "missing",
        "brief": dict(handoff.project_brief),
        "brief_fields": sorted(handoff.project_brief),
        "project_status": handoff.status,
        "current_step": handoff.current_step_id or "none",
        "current_step_status": handoff.current_step_status or "none",
        "boundary_decision": handoff.stage_view()["boundary_decision"],
        "next_action": handoff.rendered_next_action(),
        "open_risks": len([item for item in handoff.risk_register if str(item.get("status", "open")).strip().lower() != "closed"]),
        "open_issues": len([item for item in handoff.issue_register if str(item.get("status", "open")).strip().lower() != "closed"]),
        "quality_open": len([item for item in handoff.quality_register if str(item.get("status", "")).strip().lower() not in {"accepted", "closed"}]),
        "role_tree_status": baseline["status"],
        "role_tree_nodes": len((baseline.get("baseline", {}) or {}).get("tree", {}).get("nodes", [])) if isinstance((baseline.get("baseline", {}) or {}).get("tree", {}), dict) else 0,
    }
    gaps: list[dict[str, str]] = []
    if not handoff.task.strip():
        gaps.append({"code": "missing_project_task", "message": "Project specification is missing a task/objective in handoff context."})
    if not handoff.project_brief.get("objective"):
        gaps.append({"code": "missing_project_objective", "message": "Project brief is missing the objective field."})
    if not handoff.project_brief.get("scope"):
        gaps.append({"code": "missing_project_scope", "message": "Project brief is missing the scope field."})
    if not handoff.project_brief.get("expected_outputs"):
        gaps.append({"code": "missing_expected_outputs", "message": "Project brief is missing the expected_outputs field."})
    if not handoff.project_brief.get("delivery_mode"):
        gaps.append({"code": "missing_delivery_mode", "message": "Project brief is missing the delivery_mode field."})
    if role_check.get("status") != "ok":
        gaps.append({"code": "role_tree_not_ready", "message": "Role tree is not fully ready; AI tree design must treat current structure as provisional."})
    if not enabled_providers:
        gaps.append({"code": "no_enabled_providers", "message": "No enabled providers are available for AI-assisted design."})
    if shell_backend["selected"] in {None, ""}:
        gaps.append({"code": "shell_backend_unknown", "message": "Selected shell backend is unknown, so capability context is incomplete."})
    if not baseline.get("baseline"):
        gaps.append({"code": "missing_role_tree_baseline", "message": "No approved role-tree baseline exists yet."})
    ready = not gaps
    return {
        "command": "project design",
        "ready_for_ai_design": ready,
        "agent_capability_specification": capability_spec,
        "project_specification": project_spec,
        "role_tree_check": role_check,
        "focus": focus,
        "clarification_gaps": gaps,
    }


def _render_project_design(agent: Agent, config: AgentConfig) -> str:
    report = _project_design_report(agent, config)
    capability = report["agent_capability_specification"]
    project = report["project_specification"]
    blocked_text = ", ".join(
        f"{item['provider']}:{item['blocked_until']}"
        for item in capability["blocked_providers"]
    ) or "none"
    lines = [
        "Project design packet:",
        f"- ready_for_ai_design: {str(report['ready_for_ai_design']).lower()}",
        "Agent capability specification:",
        f"- workspace: {capability['workspace']}",
        f"- os_family: {capability['os_family']}",
        f"- shell_backend: configured={capability['shell_backend']['configured']} selected={capability['shell_backend']['selected']} executable={capability['shell_backend']['executable']}",
        f"- permission_mode: {capability['permission_mode']}",
        f"- enabled_providers: {', '.join(capability['enabled_providers']) or 'none'}",
        f"- active_accounts: {', '.join(f'{key}={value}' for key, value in sorted(capability['active_accounts'].items())) or 'none'}",
        f"- blocked_providers: {blocked_text}",
        f"- wet_run_required: {str(capability['capabilities']['wet_run_required']).lower()}",
        "Project specification:",
        f"- task: {project['task']}",
        f"- brief_fields: {', '.join(project['brief_fields']) or 'none'}",
        f"- project_status: {project['project_status']}",
        f"- current_step: {project['current_step']}",
        f"- boundary_decision: {project['boundary_decision']}",
        f"- next_action: {project['next_action']}",
        f"- open_risks: {project['open_risks']}",
        f"- open_issues: {project['open_issues']}",
        f"- quality_open: {project['quality_open']}",
        f"- role_tree_status: {project['role_tree_status']}",
        f"- role_tree_nodes: {project['role_tree_nodes']}",
        "Project brief:",
    ]
    brief = project["brief"]
    if isinstance(brief, dict) and brief:
        for key in sorted(brief):
            lines.append(f"- {key}: {brief[key]}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "Clarification gaps:",
        ]
    )
    gaps = report["clarification_gaps"]
    if gaps:
        for item in gaps:
            lines.append(f"- {item['code']}: {item['message']}")
    else:
        lines.append("- none")
    return "\n".join(lines)
