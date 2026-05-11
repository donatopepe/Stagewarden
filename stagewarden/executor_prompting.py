from __future__ import annotations

from typing import Any

from .planner import PlanStep
from .role_tree import build_prince2_role_flow
from .roles import PRINCE2_ROLE_AUTOMATION_RULES, PRINCE2_ROLE_SCOPE_DESCRIPTIONS
from .runtime_env import detect_runtime_capabilities
from .textcodec import dumps_ascii


ALLOWED_MODEL_ACTIONS = {
    "shell",
    "shell_session_create",
    "shell_session_send",
    "shell_session_close",
    "read_file",
    "inspect_file",
    "inspect_metadata_file",
    "write_file",
    "apply_patch",
    "search_replace_file",
    "insert_text_file",
    "delete_range_file",
    "delete_backward_file",
    "replace_range_file",
    "convert_encoding_file",
    "normalize_line_endings_file",
    "copy_path_file",
    "move_path_file",
    "delete_path_file",
    "chmod_path_file",
    "chown_path_file",
    "patch_file",
    "patch_files",
    "preview_patch_files",
    "list_files",
    "search_files",
    "git_status",
    "git_diff",
    "git_log",
    "git_show",
    "git_file_history",
    "git_commit",
    "complete",
}

MODEL_ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "shell": {"tool": "shell", "required": ["command"], "optional": ["cwd"], "mutates": "depends_on_command"},
    "shell_session_create": {"tool": "shell", "required": [], "optional": ["cwd"], "mutates": False},
    "shell_session_send": {"tool": "shell", "required": ["session_id", "command"], "optional": [], "mutates": "depends_on_command"},
    "shell_session_close": {"tool": "shell", "required": ["session_id"], "optional": [], "mutates": False},
    "read_file": {"tool": "files", "required": ["path"], "optional": [], "mutates": False},
    "inspect_file": {"tool": "files", "required": ["path"], "optional": [], "mutates": False},
    "inspect_metadata_file": {"tool": "files", "required": ["path"], "optional": [], "mutates": False},
    "write_file": {"tool": "files", "required": ["path", "content"], "optional": [], "mutates": True},
    "apply_patch": {"tool": "files", "required": ["path", "search", "replace"], "optional": [], "mutates": True},
    "search_replace_file": {"tool": "files", "required": ["path", "search", "replace"], "optional": ["count", "dry_run"], "mutates": "unless_dry_run"},
    "insert_text_file": {"tool": "files", "required": ["path", "content"], "optional": ["line_number", "pattern", "position", "occurrence", "dry_run"], "mutates": "unless_dry_run"},
    "delete_range_file": {"tool": "files", "required": ["path", "start_line", "end_line"], "optional": ["dry_run"], "mutates": "unless_dry_run"},
    "delete_backward_file": {"tool": "files", "required": ["path", "count"], "optional": ["line_number", "pattern", "occurrence", "dry_run"], "mutates": "unless_dry_run"},
    "replace_range_file": {"tool": "files", "required": ["path", "start_line", "end_line", "content"], "optional": ["dry_run"], "mutates": "unless_dry_run"},
    "convert_encoding_file": {"tool": "files", "required": ["path", "target_encoding"], "optional": ["source_encoding", "dry_run"], "mutates": "unless_dry_run"},
    "normalize_line_endings_file": {"tool": "files", "required": ["path", "newline"], "optional": ["dry_run"], "mutates": "unless_dry_run"},
    "copy_path_file": {"tool": "files", "required": ["source", "destination"], "optional": ["overwrite", "dry_run"], "mutates": "unless_dry_run"},
    "move_path_file": {"tool": "files", "required": ["source", "destination"], "optional": ["overwrite", "dry_run"], "mutates": "unless_dry_run"},
    "delete_path_file": {"tool": "files", "required": ["path"], "optional": ["recursive", "dry_run"], "mutates": "unless_dry_run"},
    "chmod_path_file": {"tool": "files", "required": ["path", "mode"], "optional": ["recursive", "dry_run"], "mutates": "unless_dry_run"},
    "chown_path_file": {"tool": "files", "required": ["path"], "optional": ["user", "group", "recursive", "dry_run"], "mutates": "unless_dry_run"},
    "patch_file": {"tool": "files", "required": ["path", "diff"], "optional": [], "mutates": True},
    "patch_files": {"tool": "files", "required": ["diff"], "optional": [], "mutates": True},
    "preview_patch_files": {"tool": "files", "required": ["diff"], "optional": [], "mutates": False},
    "list_files": {"tool": "files", "required": [], "optional": ["base_path", "pattern", "limit"], "mutates": False},
    "search_files": {"tool": "files", "required": ["pattern"], "optional": ["base_path", "glob", "limit"], "mutates": False},
    "git_status": {"tool": "git", "required": [], "optional": [], "mutates": False},
    "git_diff": {"tool": "git", "required": [], "optional": [], "mutates": False},
    "git_log": {"tool": "git", "required": [], "optional": ["limit", "path"], "mutates": False},
    "git_show": {"tool": "git", "required": [], "optional": ["revision", "stat"], "mutates": False},
    "git_file_history": {"tool": "git", "required": ["path"], "optional": ["limit"], "mutates": False},
    "git_commit": {"tool": "git", "required": ["message"], "optional": [], "mutates": True},
    "complete": {"tool": "agent", "required": ["message"], "optional": [], "mutates": False},
}


def bounded_context(text: str, limit: int, *, label: str) -> str:
    clean = text if text else ""
    if len(clean) <= limit:
        return clean
    remaining = len(clean) - limit
    return f"{clean[:limit]}\n[truncated {label}: {remaining} chars omitted]"


def example_value_for_action_field(field: str) -> Any:
    examples = {
        "command": "git status --short",
        "session_id": "session id",
        "path": "relative/path",
        "content": "text",
        "search": "old text",
        "replace": "new text",
        "start_line": 1,
        "end_line": 1,
        "count": 1,
        "target_encoding": "utf-8",
        "newline": "lf",
        "source": "relative/source",
        "destination": "relative/destination",
        "mode": "0644",
        "diff": "unified diff",
        "pattern": "regex",
        "message": "why the current step is done",
    }
    return examples.get(field, f"{field} value")


def executor_action_branches(executor: Any) -> set[str]:
    source = ""
    try:
        source = executor.__class__._run_action.__code__.co_consts.__repr__()
    except (AttributeError, TypeError):
        source = ""
    return {item for item in ALLOWED_MODEL_ACTIONS if f"'{item}'" in source or f'"{item}"' in source}


def model_visible_tool_schema_report(executor: Any) -> dict[str, Any]:
    allowed = set(ALLOWED_MODEL_ACTIONS)
    schema_actions = set(MODEL_ACTION_SCHEMAS)
    executor_actions = executor_action_branches(executor)
    missing_schema = sorted(allowed - schema_actions)
    extra_schema = sorted(schema_actions - allowed)
    missing_executor = sorted(allowed - executor_actions)
    extra_executor = sorted(executor_actions - allowed)
    status = "ok" if not (missing_schema or extra_schema or missing_executor or extra_executor) else "invalid"
    tools: dict[str, list[str]] = {}
    for action_name, schema in sorted(MODEL_ACTION_SCHEMAS.items()):
        tools.setdefault(str(schema.get("tool", "unknown")), []).append(action_name)
    return {
        "status": status,
        "action_count": len(allowed),
        "tools": tools,
        "missing_schema": missing_schema,
        "extra_schema": extra_schema,
        "missing_executor": missing_executor,
        "extra_executor": extra_executor,
        "rule": "Only actions listed here may be emitted by the model; required fields must be present before execution.",
    }


def model_visible_tool_schema_section(executor: Any) -> str:
    report = model_visible_tool_schema_report(executor)
    lines = [
        f"- status: {report['status']}",
        f"- action_count: {report['action_count']}",
        f"- validation_rule: {report['rule']}",
    ]
    for issue_key in ("missing_schema", "extra_schema", "missing_executor", "extra_executor"):
        values = report[issue_key]
        lines.append(f"- {issue_key}: {', '.join(values) if values else 'none'}")
    tools = report.get("tools", {})
    if isinstance(tools, dict):
        for tool_name, actions in sorted(tools.items()):
            action_list = ", ".join(str(action) for action in actions)
            lines.append(f"- tool {tool_name}: {action_list}")
    return "\n".join(lines)


def model_action_examples_section(executor: Any) -> str:
    lines = []
    for index, action_name in enumerate(sorted(MODEL_ACTION_SCHEMAS), start=1):
        schema = MODEL_ACTION_SCHEMAS[action_name]
        required = list(schema.get("required", []))
        optional = list(schema.get("optional", []))
        example: dict[str, Any] = {"type": action_name}
        for field in required:
            example[str(field)] = example_value_for_action_field(str(field))
        for field in optional:
            if field in {"dry_run", "overwrite", "recursive", "stat"}:
                example[str(field)] = False
            elif field in {"limit", "count", "occurrence"}:
                example[str(field)] = 1
            elif field in {"start_line", "end_line", "line_number"}:
                example[str(field)] = 1
        lines.append(f"{index}. {action_name} -> {dumps_ascii(example)}")
    return "\n".join(lines)


def role_scoped_context(executor: Any, role: str) -> dict[str, str | bool]:
    rendered = {
        "risks": executor.project_handoff.rendered_risks(),
        "issues": executor.project_handoff.rendered_issues(),
        "quality": executor.project_handoff.rendered_quality(),
        "lessons": executor.project_handoff.rendered_lessons(),
        "exception_plan": executor.project_handoff.rendered_exception_plan(),
    }
    omitted = "Omitted by PRINCE2 role scope."
    if role == "team_manager":
        return {
            "risks": omitted,
            "issues": omitted,
            "quality": rendered["quality"],
            "lessons": rendered["lessons"],
            "exception_plan": omitted,
            "handoff_log": False,
            "execution_log": False,
        }
    if role == "project_assurance":
        return {
            "risks": rendered["risks"],
            "issues": rendered["issues"],
            "quality": rendered["quality"],
            "lessons": rendered["lessons"],
            "exception_plan": omitted,
            "handoff_log": True,
            "execution_log": True,
        }
    if role == "change_authority":
        return {
            "risks": rendered["risks"],
            "issues": rendered["issues"],
            "quality": rendered["quality"],
            "lessons": rendered["lessons"],
            "exception_plan": rendered["exception_plan"],
            "handoff_log": True,
            "execution_log": False,
        }
    if role == "project_executive":
        return {
            "risks": rendered["risks"],
            "issues": rendered["issues"],
            "quality": omitted,
            "lessons": rendered["lessons"],
            "exception_plan": rendered["exception_plan"],
            "handoff_log": True,
            "execution_log": False,
        }
    if role in {"senior_user", "senior_supplier"}:
        return {
            "risks": rendered["risks"],
            "issues": rendered["issues"],
            "quality": rendered["quality"],
            "lessons": rendered["lessons"],
            "exception_plan": omitted,
            "handoff_log": False,
            "execution_log": False,
        }
    if role == "project_support":
        return {
            "risks": omitted,
            "issues": rendered["issues"],
            "quality": rendered["quality"],
            "lessons": rendered["lessons"],
            "exception_plan": rendered["exception_plan"],
            "handoff_log": True,
            "execution_log": True,
        }
    return {
        "risks": rendered["risks"],
        "issues": rendered["issues"],
        "quality": rendered["quality"],
        "lessons": rendered["lessons"],
        "exception_plan": rendered["exception_plan"],
        "handoff_log": True,
        "execution_log": True,
    }


def role_scope_description(executor: Any, role: str, node: dict[str, Any] | None = None) -> str:
    node = node or executor._role_tree_node_for_role(role)
    if node.get("context_scope"):
        return str(node["context_scope"])
    return PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role, "controlled project work")


def active_flow_context(executor: Any, active_node: dict[str, Any]) -> str:
    node_id = str(active_node.get("node_id", "")) if active_node else ""
    flow = build_prince2_role_flow()
    edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
    incoming = [edge for edge in edges if edge.get("target_node") == node_id]
    outgoing = [edge for edge in edges if edge.get("source_node") == node_id]
    if not node_id:
        return "- active_flow_edges: none; context expansion requires formal PRINCE2 event."
    lines = [
        "- active_flow_rule: context moves only through approved PRINCE2 flow edges; fallback changes route, not context scope.",
        f"- active_flow_incoming: {', '.join(str(edge.get('edge_id')) for edge in incoming) if incoming else 'none'}",
        f"- active_flow_outgoing: {', '.join(str(edge.get('edge_id')) for edge in outgoing) if outgoing else 'none'}",
    ]
    for edge in incoming + outgoing:
        payload = edge.get("payload_scope", [])
        payload_text = ", ".join(str(item) for item in payload) if isinstance(payload, list) else str(payload)
        lines.append(
            f"- flow_edge {edge.get('edge_id')}: trigger={edge.get('trigger')} "
            f"type={edge.get('flow_type')} payload_scope={payload_text} "
            f"validation={edge.get('validation_condition')}"
        )
    return "\n".join(lines)


def prince2_role_automation_section(executor: Any, task: str, step: PlanStep) -> str:
    active_role = executor._role_for_step(task=task, step=step)
    active_node = executor._role_tree_node_for_step(task=task, step=step, role=active_role)
    context_rule = active_node.get("context_rule", {}) if active_node else {}
    context_include = context_rule.get("include", []) if isinstance(context_rule, dict) else []
    context_exclude = context_rule.get("exclude", []) if isinstance(context_rule, dict) else []
    lines = [
        f"- active_role: {active_role}",
        f"- active_role_node: {active_node.get('node_id', 'unbaselined') if active_node else 'unbaselined'}",
        f"- active_role_parent_node: {active_node.get('parent_id') or 'none' if active_node else 'none'}",
        f"- active_role_level: {active_node.get('level', 'unbaselined') if active_node else 'unbaselined'}",
        f"- active_role_responsibility: {PRINCE2_ROLE_AUTOMATION_RULES.get(active_role, 'controlled project work')}",
        f"- active_node_accountability_boundary: {active_node.get('accountability_boundary', 'static role fallback') if active_node else 'static role fallback'}",
        f"- active_node_delegated_authority: {active_node.get('delegated_authority', 'static role fallback') if active_node else 'static role fallback'}",
        f"- active_node_accountable_owner: {active_node.get('accountable_owner', 'user') if active_node else 'user'}",
        f"- active_node_tolerance_margin: {active_node.get('tolerance_margin_percent', 'unknown') if active_node else 'unknown'}",
        f"- active_node_tolerance_pressure: {active_node.get('tolerance_pressure_percent', 'unknown') if active_node else 'unknown'}",
        f"- active_node_tolerance_state: {active_node.get('tolerance_profile', {}).get('autonomy_state', 'unknown') if active_node and isinstance(active_node.get('tolerance_profile'), dict) else 'unknown'}",
        f"- active_node_tolerance_summary: margin={active_node.get('tolerance_margin_percent', 'unknown') if active_node else 'unknown'} pressure={active_node.get('tolerance_pressure_percent', 'unknown') if active_node else 'unknown'} tolerance_state={active_node.get('tolerance_profile', {}).get('autonomy_state', 'unknown') if active_node and isinstance(active_node.get('tolerance_profile'), dict) else 'unknown'}",
        "- automation_rule: plan via Project Manager, deliver via Team Manager, validate via Project Assurance, escalate exceptions or tolerance breaches via Change Authority.",
        "- governance_rule: do not bypass accountability; record evidence in handoff and use Project Executive for business/cost/benefit stop-go decisions.",
        f"- context_scope: {role_scope_description(executor, active_role, active_node)}",
        f"- context_include: {', '.join(str(item) for item in context_include) if context_include else 'static role fallback'}",
        f"- context_exclude: {', '.join(str(item) for item in context_exclude) if context_exclude else 'static role fallback'}",
        active_flow_context(executor, active_node),
    ]
    assignment = active_node.get("assignment", {}) if active_node else {}
    if not isinstance(assignment, dict) or not assignment:
        assignment = executor.project_handoff.prince2_roles.get(active_role, {})
    pools = active_node.get("assignment_pool", {}) if active_node and isinstance(active_node.get("assignment_pool"), dict) else {}
    if assignment:
        params = assignment.get("params", {})
        params_text = ",".join(f"{key}={value}" for key, value in sorted(params.items())) if isinstance(params, dict) else ""
        lines.append(
            f"- active_role_route: provider={assignment.get('provider', 'unknown')} "
            f"provider_model={assignment.get('provider_model', 'unknown')} "
            f"account={assignment.get('account') or 'none'}"
            + (f" params={params_text}" if params_text else "")
        )
    else:
        lines.append("- active_role_route: unassigned; use router default and preserve role accountability in reasoning.")
    for pool_name in ("reviewer", "fallback"):
        routes = pools.get(pool_name, []) if isinstance(pools.get(pool_name, []), list) else []
        if routes:
            rendered = []
            for route in routes:
                if not isinstance(route, dict):
                    continue
                rendered.append(
                    f"{route.get('provider', 'unknown')}:{route.get('provider_model', 'provider-default')}"
                    + (f":{route.get('account')}" if route.get("account") else "")
                )
            lines.append(f"- active_role_{pool_name}_pool: {', '.join(rendered) if rendered else 'none'}")
    return "\n".join(lines)


def prince2_node_context_packet(executor: Any, task: str, step: PlanStep) -> str:
    active_role = executor._role_for_step(task=task, step=step)
    active_node = executor._role_tree_node_for_step(task=task, step=step, role=active_role)
    runtime = executor.project_handoff.prince2_node_runtime if isinstance(executor.project_handoff.prince2_node_runtime, dict) else {}
    runtime_nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    runtime_node = None
    if active_node:
        node_id = str(active_node.get("node_id", "")).strip()
        runtime_node = next((item for item in runtime_nodes if str(item.get("node_id", "")).strip() == node_id), None)
    node = runtime_node or active_node or {}
    context_rule = node.get("context_rule", {}) if isinstance(node.get("context_rule"), dict) else {}
    assignment = node.get("assignment", {}) if isinstance(node.get("assignment"), dict) else {}
    flow = build_prince2_role_flow()
    edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
    node_id = str(node.get("node_id", "")).strip()
    incoming = [edge for edge in edges if str(edge.get("target_node", "")).strip() == node_id]
    outgoing = [edge for edge in edges if str(edge.get("source_node", "")).strip() == node_id]
    runtime_capabilities = detect_runtime_capabilities(executor.config.workspace_root)
    selected_backend = executor.shell._selected_shell_backend()
    lines = [
        f"- node_id: {node_id or 'unbaselined'}",
        f"- node_label: {node.get('label', 'unbaselined')}",
        f"- role_type: {node.get('role_type', active_role)}",
        f"- runtime_state: {node.get('state', 'unknown')}",
        f"- wait_status: {node.get('wait_status', 'none')}",
        f"- wait_reason: {node.get('wait_reason') or 'none'}",
        f"- wake_triggers: {', '.join(str(item) for item in node.get('wake_triggers', [])) if isinstance(node.get('wake_triggers', []), list) and node.get('wake_triggers', []) else 'none'}",
        f"- inbox_count: {node.get('inbox_count', 0)} outbox_count: {node.get('outbox_count', 0)}",
        f"- transcript_refs: {', '.join(str(item) for item in node.get('transcript_refs', [])) if isinstance(node.get('transcript_refs', []), list) and node.get('transcript_refs', []) else 'none'}",
        f"- tolerance_owner: {node.get('accountable_owner', 'user')}",
        f"- tolerance_margin_percent: {node.get('tolerance_margin_percent', 'unknown')}",
        f"- tolerance_pressure_percent: {node.get('tolerance_pressure_percent', 'unknown')}",
        f"- tolerance_autonomy_rule: {node.get('autonomy_rule', 'work autonomously within the margin; escalate when exceeded')}",
        f"- tolerance_state: {node.get('tolerance_profile', {}).get('autonomy_state', 'unknown') if isinstance(node.get('tolerance_profile'), dict) else 'unknown'}",
        f"- tolerance_summary: margin={node.get('tolerance_margin_percent', 'unknown')} pressure={node.get('tolerance_pressure_percent', 'unknown')} tolerance_state={node.get('tolerance_profile', {}).get('autonomy_state', 'unknown') if isinstance(node.get('tolerance_profile'), dict) else 'unknown'}",
        f"- provider: {assignment.get('provider', 'unknown') if assignment else 'unassigned'}",
        f"- provider_model: {assignment.get('provider_model', 'unknown') if assignment else 'unassigned'}",
        f"- account: {assignment.get('account') or 'none' if assignment else 'none'}",
        f"- responsibility_domain: {node.get('responsibility_domain', PRINCE2_ROLE_AUTOMATION_RULES.get(active_role, 'controlled project work'))}",
        f"- context_scope: {node.get('context_scope', PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(active_role, 'controlled project work'))}",
        f"- accountability_boundary: {node.get('accountability_boundary', 'static role fallback')}",
        f"- delegated_authority: {node.get('delegated_authority', 'static role fallback')}",
        f"- context_include: {', '.join(str(item) for item in context_rule.get('include', [])) if isinstance(context_rule.get('include', []), list) and context_rule.get('include', []) else 'none'}",
        f"- context_exclude: {', '.join(str(item) for item in context_rule.get('exclude', [])) if isinstance(context_rule.get('exclude', []), list) and context_rule.get('exclude', []) else 'none'}",
        f"- communication_incoming_edges: {', '.join(str(edge.get('edge_id')) for edge in incoming) if incoming else 'none'}",
        f"- communication_outgoing_edges: {', '.join(str(edge.get('edge_id')) for edge in outgoing) if outgoing else 'none'}",
        "- communication_commands: roles active [--json] | roles control [--json] | roles queues [--json] | roles messages [node_id] | role message <source_node> <target_node> <edge_id> payload=<scope1,scope2> | role wait <node_id> reason=<text> | role wake <node_id> trigger=<name> | role tick <node_id> | roles tick [max_nodes]",
        f"- workspace: {executor.config.workspace_root}",
        f"- os_family: {runtime_capabilities.get('os_family', 'unknown')}",
        f"- recommended_shell: {runtime_capabilities.get('recommended_shell', 'unknown')}",
        f"- shell_backend_selected: {selected_backend.get('selected') or 'unknown'}",
        f"- core_agent_capabilities: shell=true files=true git=true wet_run_required=true",
        f"- model_actions: {', '.join(sorted(ALLOWED_MODEL_ACTIONS))}",
        "- file_operations: read_file, inspect_file, inspect_metadata_file, write_file, apply_patch, search_replace_file, insert_text_file, delete_range_file, delete_backward_file, replace_range_file, convert_encoding_file, normalize_line_endings_file, copy_path_file, move_path_file, delete_path_file, chmod_path_file, chown_path_file, patch_file, patch_files, preview_patch_files, list_files, search_files",
        "- git_operations: git_status, git_diff, git_log, git_show, git_file_history, git_commit",
        "- shell_operations: shell, shell_session_create, shell_session_send, shell_session_close",
        f"- project_task: {executor.project_handoff.task or 'none'}",
        f"- project_status: {executor.project_handoff.status or 'idle'}",
        f"- current_step: {executor.project_handoff.current_step_id or 'none'} [{executor.project_handoff.current_step_status or 'none'}]",
    ]
    return "\n".join(lines)


def model_context_files_section(executor: Any) -> str:
    status = executor.git.status()
    porcelain = executor.git.status_porcelain()
    dirty_state = "unknown"
    status_preview = status.stdout or status.error
    if porcelain.ok:
        dirty_state = "dirty" if porcelain.stdout.strip() else "clean"
    elif status.ok:
        dirty_state = "dirty" if status.stdout and any(line and not line.startswith("##") for line in status.stdout.splitlines()) else "clean"
    view = executor.project_handoff.stage_view()
    backlog = view["backlog_statuses"]
    git_boundary = view["git_boundary"]
    lines = [
        f"- handoff_file: {executor.config.handoff_path.name}",
        f"- memory_file: {executor.config.memory_path.name}",
        f"- trace_file: {executor.config.trace_path.name}",
        f"- recovery_state: {view['recovery_state']}",
        f"- backlog_status: ready={backlog['ready']} planned={backlog['planned']} in_progress={backlog['in_progress']} blocked={backlog['blocked']} done={backlog['done']}",
        f"- git_boundary: baseline={git_boundary['baseline']} current={git_boundary['current']}",
        f"- git_dirty_state: {dirty_state}",
        f"- git_status: {bounded_context(status_preview or 'No git status available.', 1200, label='git_status')}",
        "- context_boundaries: sections are truncated with explicit markers; consult files through read_file when exact full context is needed.",
    ]
    return "\n".join(lines)
