from __future__ import annotations

from .agent import Agent
from .config import AgentConfig
from .json_schema_registry import with_json_schema
from .permissions import VALID_PERMISSION_MODES, PermissionSettings
from .textcodec import dumps_ascii
from . import battery_views as _battery_views
from . import project_handoff_views as _project_handoff_views
from . import project_state_views as _project_state_views
from . import account_views as _account_views
from . import command_views as _command_views
from . import report_views as _report_views
from . import status_dashboard_views as _status_dashboard_views
from . import status_views as _status_views
from . import agent_setup_views as _agent_setup_views


def _handle_mode_command(command: str, agent: Agent, config: AgentConfig) -> str | None:
    parts = command.split()
    if not parts:
        return None
    if parts[0] == "status":
        if len(parts) == 2 and parts[1] == "full":
            return _status_views._render_status_full(agent, config)
        return _status_views._render_status(agent, config)
    if parts[0] == "goal" or command.startswith("goal "):
        report = _project_state_views.goal_command_report(command, config)
        if report.get("ok") is False:
            return str(report.get("error", "Goal command failed."))
        if command == "goal":
            return _project_state_views.render_goal_report(config)
        goal = report.get("goal", {})
        if isinstance(goal, dict):
            return f"Goal {goal.get('status', 'updated')}: {goal.get('objective', '') or 'none'}"
        return "Goal updated."
    if parts[0] == "budget" or command.startswith("budget "):
        report = _project_state_views.budget_command_report(command, config)
        if report.get("ok") is False:
            return str(report.get("error", "Budget command failed."))
        if command == "budget":
            return _project_state_views.render_budget_report(config)
        if report.get("command") == "budget clear":
            return "Project budget cleared."
        budget = report.get("budget", {})
        if isinstance(budget, dict):
            return f"Budget {budget.get('status', 'updated')}: {budget.get('budget_usd', 'none')} {budget.get('currency', 'USD')}"
        return "Budget updated."
    if parts[0] == "question" or command.startswith("question "):
        report = _project_state_views.question_command_report(command, config)
        if report.get("ok") is False:
            return str(report.get("error", "Question command failed."))
        if command == "question":
            return _project_state_views.render_question_report(config)
        if report.get("command") == "question ask":
            question = report.get("user_question", {})
            if isinstance(question, dict):
                return f"Question asked: {question.get('question', 'none')}"
        return "Question updated."
    if parts[0] == "answer" or command.startswith("answer "):
        report = _project_state_views.question_command_report(command, config)
        if report.get("ok") is False:
            return str(report.get("error", "Answer command failed."))
        question = report.get("user_question", {})
        if isinstance(question, dict):
            return f"Question answered: {question.get('question', 'none')}"
        return "Question answered."
    if parts[0] == "statusline":
        return dumps_ascii(with_json_schema("statusline", _status_dashboard_views._statusline_report(agent, config)), indent=2)
    if parts[0] == "preflight":
        return _status_dashboard_views._render_preflight(agent, config)
    if parts[0] == "battery":
        return _battery_views._render_battery(config)
    if len(parts) == 3 and parts[0] == "auth" and parts[1] == "status":
        return _auth_views._render_auth_status(parts[2])
    if parts[0] == "overview":
        return _status_views._render_overview(agent, config)
    if parts[0] == "health":
        return _status_views._render_health(agent, config)
    if parts[0] == "report":
        return _status_dashboard_views._render_report(agent, config)
    if parts[0] == "doctor":
        return _status_dashboard_views._render_doctor(config)
    if parts[0] == "handoff":
        if len(parts) == 2 and parts[1] in {"md", "export"}:
            return _project_handoff_views._export_handoff_markdown(config)
        if len(parts) >= 2 and parts[1] == "actions":
            return _project_handoff_views._render_handoff_actions(config, limit=_project_handoff_views._parse_optional_limit(parts))
        return _project_handoff_views._render_handoff(config)
    if parts[0] == "board" or command == "stage review":
        return _report_views._render_board(config)
    if parts[0] == "boundary":
        return _report_views._render_boundary(config)
    if parts[0] == "risks":
        if len(parts) >= 3 and parts[1] == "close":
            resolution = command.partition("close")[2].strip() or "Resolved by explicit mitigation and wet-run validation."
            return _report_views._render_risks_close(config, resolution)
        return _report_views._render_risks(config)
    if parts[0] == "issues":
        return _report_views._render_issues(config)
    if parts[0] == "quality":
        return _report_views._render_quality(config)
    if parts[0] == "exception":
        return _report_views._render_exception(config)
    if parts[0] == "lessons":
        return _report_views._render_lessons(config)
    if parts[0] in {"transcript", "trace"}:
        return _project_handoff_views._render_transcript(config)
    if parts[0] == "todo":
        return _report_views._render_todo(config)
    if parts[0] == "permissions":
        return _report_views._render_permissions(config)
    if parts[0] == "permission":
        return _command_views._handle_permission_command(parts, config, agent)
    if parts[0] == "shell":
        return _command_views._handle_shell_command(parts, config)
    if parts[0] != "mode":
        return None
    if len(parts) == 2:
        mode = parts[1].strip().lower().replace("-", "_")
        if mode in VALID_PERMISSION_MODES:
            settings = PermissionSettings.load(config.settings_path)
            settings.default_mode = mode
            settings.normalize().save(config.settings_path)
            _agent_setup_views._refresh_runtime_permissions(agent)
            return f"Permission mode set to {mode}."
    if len(parts) == 2 and parts[1] == "normal":
        result = agent.run("normal mode")
        return result.message
    if len(parts) == 3 and parts[1] == "caveman":
        result = agent.run(f"/caveman {parts[2]}")
        return result.message
    return (
        "Usage: mode <normal|default|accept_edits|accept-edits|plan|auto|dont_ask|dont-ask> "
        "| mode caveman <level>"
    )
