from __future__ import annotations

from .agent import Agent
from .config import AgentConfig
from .project_handoff import ProjectHandoff
from .json_schema_registry import json_schema
from .permissions import PermissionSettings
from . import project_handoff_views as _project_handoff_views


def _render_boundary(config: AgentConfig) -> str:
    return _project_handoff_views._render_boundary(config)


def _boundary_report(config: AgentConfig) -> dict[str, object]:
    return _project_handoff_views._boundary_report(config)


def _board_report(config: AgentConfig) -> dict[str, object]:
    return _project_handoff_views._board_report(config)


def _render_board(config: AgentConfig) -> str:
    return _project_handoff_views._render_board(config)


def _render_permissions(config: AgentConfig) -> str:
    workspace_settings = PermissionSettings.load(config.settings_path)
    session_settings = config.session_permission_settings
    effective_settings = workspace_settings.merged(session_settings)
    lines = ["Permission settings:"]
    lines.append(f"- workspace mode: {workspace_settings.default_mode}")
    lines.append(f"- workspace allow: {', '.join(workspace_settings.allow) if workspace_settings.allow else 'none'}")
    lines.append(f"- workspace ask: {', '.join(workspace_settings.ask) if workspace_settings.ask else 'none'}")
    lines.append(f"- workspace deny: {', '.join(workspace_settings.deny) if workspace_settings.deny else 'none'}")
    if session_settings is None:
        lines.append("- session mode: none")
        lines.append("- session allow: none")
        lines.append("- session ask: none")
        lines.append("- session deny: none")
    else:
        lines.append(f"- session mode: {session_settings.default_mode}")
        lines.append(f"- session allow: {', '.join(session_settings.allow) if session_settings.allow else 'none'}")
        lines.append(f"- session ask: {', '.join(session_settings.ask) if session_settings.ask else 'none'}")
        lines.append(f"- session deny: {', '.join(session_settings.deny) if session_settings.deny else 'none'}")
    lines.append(f"- effective mode: {effective_settings.default_mode}")
    lines.append(f"- effective allow: {', '.join(effective_settings.allow) if effective_settings.allow else 'none'}")
    lines.append(f"- effective ask: {', '.join(effective_settings.ask) if effective_settings.ask else 'none'}")
    lines.append(f"- effective deny: {', '.join(effective_settings.deny) if effective_settings.deny else 'none'}")
    return "\n".join(lines)


def _render_risks(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_risks()


def _risks_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "risks",
        "schema": json_schema("risks"),
        "count": len(handoff.risk_register),
        "items": list(handoff.risk_register),
    }


def _render_risks_close(config: AgentConfig, resolution: str) -> str:
    report = _risks_close_report(config, resolution)
    lines = [
        "Risk closure:",
        f"- ok: {str(report['ok']).lower()}",
        f"- open_before: {report['open_before']}",
        f"- open_after: {report['open_after']}",
        f"- resolution: {report['resolution']}",
        "Risk register:",
    ]
    items = [item for item in report.get("items", []) if isinstance(item, dict)]
    if not items:
        lines.append("- none")
    else:
        for item in items:
            lines.append(f"- [{item.get('status', 'unknown')}] {item.get('risk', '')}")
    return "\n".join(lines)


def _risks_close_report(config: AgentConfig, resolution: str) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    open_before = sum(1 for item in handoff.risk_register if str(item.get("status", "open")).strip().lower() != "closed")
    handoff.close_all_open_risks(resolution=resolution)
    handoff.save(config.handoff_path)
    return {
        "command": "risks close",
        "ok": True,
        "open_before": open_before,
        "open_after": sum(1 for item in handoff.risk_register if str(item.get("status", "open")).strip().lower() != "closed"),
        "resolution": resolution,
        "items": list(handoff.risk_register),
    }


def _render_issues(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_issues()


def _issues_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "issues",
        "schema": json_schema("issues"),
        "count": len(handoff.issue_register),
        "items": list(handoff.issue_register),
    }


def _render_issues_close(config: AgentConfig, resolution: str) -> str:
    report = _issues_close_report(config, resolution)
    lines = [
        "Issue closure:",
        f"- ok: {str(report['ok']).lower()}",
        f"- open_before: {report['open_before']}",
        f"- open_after: {report['open_after']}",
        f"- resolution: {report['resolution']}",
        "Issue register:",
    ]
    items = [item for item in report.get("items", []) if isinstance(item, dict)]
    if not items:
        lines.append("- none")
    else:
        for item in items:
            lines.append(
                f"- [{item.get('severity', 'unknown')}] {item.get('step_id', '-')} :: {item.get('summary', '')} [{item.get('status', 'unknown')}]"
            )
    return "\n".join(lines)


def _issues_close_report(config: AgentConfig, resolution: str) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    open_before = sum(1 for item in handoff.issue_register if str(item.get("status", "open")).strip().lower() != "closed")
    handoff.close_all_open_issues(resolution=resolution)
    handoff.save(config.handoff_path)
    return {
        "command": "issues close",
        "ok": True,
        "open_before": open_before,
        "open_after": sum(1 for item in handoff.issue_register if str(item.get("status", "open")).strip().lower() != "closed"),
        "resolution": resolution,
        "items": list(handoff.issue_register),
    }


def _render_quality(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_quality()


def _quality_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "quality",
        "schema": json_schema("quality"),
        "count": len(handoff.quality_register),
        "items": list(handoff.quality_register),
    }


def _render_quality_close(config: AgentConfig, resolution: str) -> str:
    report = _quality_close_report(config, resolution)
    lines = [
        "Quality closure:",
        f"- ok: {str(report['ok']).lower()}",
        f"- open_before: {report['open_before']}",
        f"- open_after: {report['open_after']}",
        f"- resolution: {report['resolution']}",
        "Quality register:",
    ]
    items = [item for item in report.get("items", []) if isinstance(item, dict)]
    if not items:
        lines.append("- none")
    else:
        for item in items:
            lines.append(
                f"- [{item.get('status', 'unknown')}] {item.get('step_id', '-')} :: {item.get('evidence', '')}"
            )
    return "\n".join(lines)


def _quality_close_report(config: AgentConfig, resolution: str) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    open_before = sum(
        1 for item in handoff.quality_register if str(item.get("status", "")).strip().lower() not in {"accepted", "closed"}
    )
    handoff.finalize_quality_register(resolution=resolution)
    handoff.save(config.handoff_path)
    return {
        "command": "quality close",
        "ok": True,
        "open_before": open_before,
        "open_after": sum(
            1 for item in handoff.quality_register if str(item.get("status", "")).strip().lower() not in {"accepted", "closed"}
        ),
        "resolution": resolution,
        "items": list(handoff.quality_register),
    }


def _render_exception(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_exception_plan()


def _exception_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "exception",
        "schema": json_schema("exception"),
        "count": len(handoff.exception_plan),
        "items": list(handoff.exception_plan),
    }


def _render_lessons(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_lessons()


def _lessons_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "lessons",
        "schema": json_schema("lessons"),
        "count": len(handoff.lessons_log),
        "items": list(handoff.lessons_log),
    }


def _render_todo(config: AgentConfig) -> str:
    return ProjectHandoff.load(config.handoff_path).rendered_implementation_backlog()


def _todo_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "todo",
        "schema": json_schema("todo"),
        "count": len(handoff.implementation_backlog),
        "items": list(handoff.implementation_backlog),
    }

