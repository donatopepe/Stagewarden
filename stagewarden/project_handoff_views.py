from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import AgentConfig
from .json_schema_registry import json_schema
from .memory import MemoryStore
from .textcodec import read_text_utf8, write_text_utf8

from .role_tree import prince2_role_mnemonic, prince2_role_team_name

from .prince2 import PRINCE2_THEME_NAMES
from .role_tree import prince2_node_description, prince2_status_color


def _project_handoff_cls():
    from .project_handoff import ProjectHandoff

    return ProjectHandoff


class _ProjectHandoffProxy:
    def __call__(self, *args: object, **kwargs: object) -> object:
        return _project_handoff_cls()(*args, **kwargs)

    def __getattr__(self, name: str) -> object:
        return getattr(_project_handoff_cls(), name)


ProjectHandoff = _ProjectHandoffProxy()


def summary(handoff: Any, limit: int = 6) -> str:
    if not handoff.entries:
        return "No active handoff context."
    goal = handoff.goal_view()
    budget = handoff.project_budget_view()
    question = handoff.user_question_view()
    lines = [
        f"task={handoff.task or 'unknown'}",
        f"goal={goal['status']}:{goal['objective'] or 'none'}",
        f"project_budget={budget['status']}:{budget['budget_usd'] if budget['budget_usd'] is not None else 'none'}",
        f"user_question={question['status']}",
        f"status={handoff.status}",
        f"plan_status={handoff.plan_status or 'unknown'}",
        f"current_step={handoff.current_step_id or 'none'}",
        f"git_head={handoff.git_head or 'unknown'}",
        f"project_brief_fields={len(handoff.project_brief)}",
        "registers="
        f"risks:{len(handoff.risk_register)} issues:{len(handoff.issue_register)} "
        f"quality:{len(handoff.quality_register)} lessons:{len(handoff.lessons_log)} "
        f"backlog:{len(handoff.implementation_backlog)}",
        f"prince2_roles={len(handoff.prince2_roles)}",
        f"prince2_role_tree_baseline={'approved' if handoff.prince2_role_tree_baseline else 'missing'}",
        f"prince2_node_runtime={handoff.prince2_node_runtime_summary().get('status', 'missing')}",
    ]
    for role, assignment in sorted(handoff.prince2_roles.items()):
        lines.append(
            f"role={role} provider={assignment.get('provider', 'unknown')} "
            f"provider_model={assignment.get('provider_model', 'unknown')} "
            f"account={assignment.get('account') or 'none'}"
        )
    for entry in handoff.entries[-limit:]:
        lines.append(
            f"[{entry.phase}] iter={entry.iteration} step={entry.step_id or '-'} "
            f"status={entry.step_status or '-'} model={entry.model or '-'}"
        )
    return "\n".join(lines)


def detailed_summary(handoff: Any, limit: int = 8) -> str:
    if not handoff.entries:
        return "No handoff log entries."
    lines = []
    for entry in handoff.entries[-limit:]:
        details = ""
        observation = str(entry.details.get("observation", "")).strip()
        if observation:
            details = f" observation={observation[:160]}"
        lines.append(
            f"[{entry.phase}] iter={entry.iteration} step={entry.step_id or '-'} "
            f"status={entry.step_status or '-'} model={entry.model or '-'} "
            f"action={entry.action_type or '-'} head={entry.git_head or 'unknown'}{details}"
        )
    return "\n".join(lines)


def _pending_question_text(question: dict[str, Any]) -> str:
    pending = question.get("pending", {}) if isinstance(question, dict) else {}
    if not isinstance(pending, dict):
        return "none"
    return str(pending.get("question") or "none")


def stage_view(handoff: Any) -> dict[str, object]:
    status_by_step = handoff._parse_plan_status(handoff.plan_status)
    closed_steps = [step_id for step_id, status in status_by_step.items() if status == "completed"]
    active_step = None
    if handoff.current_step_id and handoff.current_step_status in {"pending", "in_progress", "failed", "exception", "waiting"}:
        active_step = {
            "id": handoff.current_step_id,
            "title": handoff.current_step_title,
            "status": handoff.current_step_status,
            "latest_observation": handoff.latest_observation,
        }
    git_boundary = {
        "baseline": handoff.git_head_baseline or "unknown",
        "current": handoff.git_head or "unknown",
    }
    pid_boundary = {
        "project_status": handoff.status or "unknown",
        "plan_status": handoff.plan_status or "unknown",
        "updated_at": handoff.updated_at,
    }
    boundary_decision = handoff._boundary_decision(status_by_step)
    register_statuses = handoff._register_status_summary()
    backlog_statuses = handoff._implementation_backlog_status_summary()
    recovery_state = handoff._recovery_state(status_by_step, backlog_statuses)
    stage_health = handoff._stage_health(boundary_decision, active_step, register_statuses, backlog_statuses)
    next_action = handoff._next_action(boundary_decision, active_step, stage_health, backlog_statuses, recovery_state)
    budget_view = handoff.project_budget_view()
    question_view = handoff.user_question_view()
    return {
        "closed_steps": closed_steps,
        "active_step": active_step,
        "git_boundary": git_boundary,
        "pid_boundary": pid_boundary,
        "boundary_decision": boundary_decision,
        "register_statuses": register_statuses,
        "backlog_statuses": backlog_statuses,
        "recovery_state": recovery_state,
        "stage_health": stage_health,
        "next_action": next_action,
        "project_budget": budget_view,
        "user_question": question_view,
        "session_state": "waiting_for_user" if handoff.status == "waiting" and handoff.waiting_reason == "clarification" else "suspended" if handoff.status == "waiting" else handoff.status,
        "session_recoverable": handoff.status == "waiting",
        "node_runtime_summary": handoff.prince2_node_runtime_summary(),
    }


def rendered_stage_view(handoff: Any) -> str:
    view = stage_view(handoff)
    closed_steps = view["closed_steps"]
    active_step = view["active_step"]
    git_boundary = view["git_boundary"]
    pid_boundary = view["pid_boundary"]
    boundary_decision = view["boundary_decision"]
    register_statuses = view["register_statuses"]
    backlog_statuses = view["backlog_statuses"]
    recovery_state = view["recovery_state"]
    stage_health = view["stage_health"]
    next_action = view["next_action"]
    budget = view["project_budget"]
    question = view["user_question"]
    session_state = view["session_state"]
    session_recoverable = bool(view["session_recoverable"])
    lines = ["Stage view:"]
    if closed_steps:
        lines.append(f"- closed_stages: {', '.join(closed_steps)}")
    else:
        lines.append("- closed_stages: none")
    if active_step:
        lines.append(
            f"- active_stage: {active_step['id']} [{active_step['status']}] "
            f"{active_step['title'] or 'untitled'}"
        )
        observation = str(active_step.get("latest_observation", "")).strip()
        if observation:
            lines.append(f"- active_observation: {observation[:200]}")
    else:
        lines.append("- active_stage: none")
    lines.append(f"- git_boundary: baseline={git_boundary['baseline']} current={git_boundary['current']}")
    lines.append(
        f"- pid_boundary: project_status={pid_boundary['project_status']} "
        f"plan_status={pid_boundary['plan_status']} updated_at={pid_boundary['updated_at']}"
    )
    lines.append(f"- stage_health: {stage_health}")
    lines.append(
        f"- project_budget: status={budget['status']} "
        f"budget_usd={budget['budget_usd'] if budget['budget_usd'] is not None else 'none'} "
        f"spend_usd={budget['spend_usd']} "
        f"remaining_usd={budget['remaining_usd'] if budget['remaining_usd'] is not None else 'none'}"
    )
    lines.append(
        f"- user_question: status={question['status']} "
        f"waiting_reason={question['waiting_reason']} "
        f"question={_pending_question_text(question)}"
    )
    lines.append(f"- session_state: {session_state}")
    lines.append(f"- session_recoverable: {str(session_recoverable).lower()}")
    lines.append(f"- recovery_state: {recovery_state}")
    lines.append(f"- boundary_decision: {boundary_decision}")
    lines.append(f"- next_action: {next_action}")
    node_runtime = view["node_runtime_summary"]
    lines.append(
        "- node_runtime: "
        f"status={node_runtime['status']} nodes={node_runtime['nodes']} "
        f"ready={node_runtime['ready']} waiting={node_runtime['waiting']} "
        f"running={node_runtime['running']} blocked={node_runtime['blocked']}"
    )
    lines.append(
        "- registers: "
        f"risks={len(handoff.risk_register)} issues={len(handoff.issue_register)} "
        f"quality={len(handoff.quality_register)} lessons={len(handoff.lessons_log)} "
        f"backlog={len(handoff.implementation_backlog)}"
    )
    lines.append(
        "- register_status: "
        f"risks_open={register_statuses['risks_open']} risks_closed={register_statuses['risks_closed']} "
        f"issues_open={register_statuses['issues_open']} issues_closed={register_statuses['issues_closed']} "
        f"quality_open={register_statuses['quality_open']} quality_accepted={register_statuses['quality_accepted']}"
    )
    lines.append(
        "- backlog_status: "
        f"ready={backlog_statuses['ready']} planned={backlog_statuses['planned']} "
        f"in_progress={backlog_statuses['in_progress']} blocked={backlog_statuses['blocked']} "
        f"done={backlog_statuses['done']}"
    )
    if handoff.prince2_roles:
        lines.append("- prince2_roles:")
        for role, assignment in sorted(handoff.prince2_roles.items()):
            params = assignment.get("params", {})
            params_text = ",".join(f"{key}={value}" for key, value in sorted(params.items())) if isinstance(params, dict) else ""
            lines.append(
                f"  {role}: provider={assignment.get('provider', 'unknown')} "
                f"provider_model={assignment.get('provider_model', 'unknown')} "
                f"account={assignment.get('account') or 'none'}"
                + (f" params={params_text}" if params_text else "")
            )
    if handoff.exception_plan:
        lines.append(f"- exception_plan: {' | '.join(handoff.exception_plan[:3])}")
    return "\n".join(lines)


def rendered_register_status_summary(handoff: Any) -> str:
    summary = handoff._register_status_summary()
    clean = (
        summary["risks_open"] == 0
        and summary["issues_open"] == 0
        and summary["quality_open"] == 0
        and not handoff.exception_plan
    )
    state = "clean" if clean else "residual"
    return (
        f"governance={state} "
        f"risks_open={summary['risks_open']} risks_closed={summary['risks_closed']} "
        f"issues_open={summary['issues_open']} issues_closed={summary['issues_closed']} "
        f"quality_open={summary['quality_open']} quality_accepted={summary['quality_accepted']} "
        f"exception_plan_items={len(handoff.exception_plan)}"
    )


def rendered_stage_health(handoff: Any) -> str:
    return str(stage_view(handoff)["stage_health"])


def rendered_next_action(handoff: Any) -> str:
    return str(stage_view(handoff)["next_action"])


def rendered_operational_posture(handoff: Any) -> str:
    view = stage_view(handoff)
    active_step = view["active_step"]
    backlog_statuses = view["backlog_statuses"]
    active_stage = "none"
    if isinstance(active_step, dict):
        active_stage = f"{active_step.get('id', 'unknown')} [{active_step.get('status', 'unknown')}]"
    git_boundary = view["git_boundary"]
    return "\n".join(
        [
            "Operational posture:",
            f"- governance: {rendered_register_status_summary(handoff)}",
            f"- stage_health: {view['stage_health']}",
            f"- session_state: {view['session_state']}",
            f"- session_recoverable: {str(bool(view['session_recoverable'])).lower()}",
            f"- recovery_state: {view['recovery_state']}",
            f"- next_action: {view['next_action']}",
            f"- active_stage: {active_stage}",
            f"- implementation_backlog_open: {backlog_statuses['ready'] + backlog_statuses['planned'] + backlog_statuses['in_progress'] + backlog_statuses['blocked']}",
            f"- implementation_backlog_blocked: {backlog_statuses['blocked']}",
            f"- git_boundary: baseline={git_boundary['baseline']} current={git_boundary['current']}",
            f"- boundary_decision: {view['boundary_decision']}",
        ]
    )


def rendered_risks(handoff: Any) -> str:
    lines = ["Risk register:"]
    if not handoff.risk_register:
        lines.append("- none")
        return "\n".join(lines)
    for item in handoff.risk_register:
        lines.append(f"- [{item.get('status', 'unknown')}] {item.get('risk', '')}")
    return "\n".join(lines)


def rendered_issues(handoff: Any) -> str:
    lines = ["Issue register:"]
    if not handoff.issue_register:
        lines.append("- none")
        return "\n".join(lines)
    for item in handoff.issue_register:
        lines.append(f"- [{item.get('severity', 'unknown')}] {item.get('step_id', '-')} :: {item.get('summary', '')}")
    return "\n".join(lines)


def rendered_quality(handoff: Any) -> str:
    lines = ["Quality register:"]
    if not handoff.quality_register:
        lines.append("- none")
        return "\n".join(lines)
    for item in handoff.quality_register:
        lines.append(f"- [{item.get('status', 'unknown')}] {item.get('step_id', '-')} :: {item.get('evidence', '')}")
    return "\n".join(lines)


def rendered_exception_plan(handoff: Any) -> str:
    lines = ["Exception plan:"]
    if not handoff.exception_plan:
        lines.append("- none")
        return "\n".join(lines)
    for item in handoff.exception_plan:
        lines.append(f"- {item}")
    return "\n".join(lines)


def rendered_lessons(handoff: Any) -> str:
    lines = ["Lessons log:"]
    if not handoff.lessons_log:
        lines.append("- none")
        return "\n".join(lines)
    for item in handoff.lessons_log:
        lines.append(f"- [{item.get('type', 'lesson')}] {item.get('step_id', '-')} :: {item.get('lesson', '')}")
    return "\n".join(lines)


def rendered_implementation_backlog(handoff: Any) -> str:
    lines = ["Implementation backlog:"]
    if not handoff.implementation_backlog:
        lines.append("- none")
        return "\n".join(lines)
    for item in handoff.implementation_backlog:
        normalized_status = handoff._normalize_backlog_status(str(item.get("status", "")))
        lines.append(
            f"- [{normalized_status}] {item.get('step_id', '-')} :: "
            f"{item.get('title', '')} | validation={item.get('validation', '')}"
        )
    return "\n".join(lines)


def rendered_project_brief(handoff: Any) -> str:
    lines = ["Project brief:"]
    if not handoff.project_brief:
        lines.append("- none")
        return "\n".join(lines)
    for key in sorted(handoff.project_brief):
        lines.append(f"- {key}: {handoff.project_brief[key]}")
    return "\n".join(lines)


def prince2_node_runtime_report(handoff: Any) -> dict[str, Any]:
    if not handoff.prince2_node_runtime:
        return {
            "command": "roles runtime",
            "status": "missing",
            "message": "No materialized PRINCE2 node runtime. Approve a role-tree baseline first.",
            "summary": handoff.prince2_node_runtime_summary(),
            "runtime": {},
        }
    return {
        "command": "roles runtime",
        "status": "materialized",
        "summary": handoff.prince2_node_runtime_summary(),
        "runtime": dict(handoff.prince2_node_runtime),
    }


def rendered_prince2_node_runtime(handoff: Any) -> str:
    report = prince2_node_runtime_report(handoff)
    if report["status"] == "missing":
        return "PRINCE2 node runtime: missing\n- action: run /project start, /roles tree approve, or /project tree approve first."
    summary = report["summary"] if isinstance(report["summary"], dict) else {}
    runtime = report["runtime"] if isinstance(report["runtime"], dict) else {}
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    stage_view_data = stage_view(handoff)
    lines = [
        "PRINCE2 node runtime:",
        f"- status: {summary.get('status', 'unknown')}",
        f"- nodes: {summary.get('nodes', 0)}",
        f"- ready: {summary.get('ready', 0)} waiting={summary.get('waiting', 0)} running={summary.get('running', 0)} blocked={summary.get('blocked', 0)}",
        f"- materialized_at: {runtime.get('materialized_at', 'unknown')}",
        f"- baseline_source: {runtime.get('baseline_source', 'unknown')}",
        f"- wait_triggers: {summary.get('wait_triggers', 0)} message_queues={summary.get('message_queues', 0)}",
        f"- session_state: {stage_view_data['session_state']}",
        f"- session_recoverable: {str(bool(stage_view_data['session_recoverable'])).lower()}",
    ]
    for node in nodes:
        status_color = prince2_status_color(node, runtime_state=str(node.get("state", "")))
        lines.append(
            f"- {node.get('label', node.get('node_id', 'node'))} [{node.get('node_id', 'unknown')}]: "
            f"state={node.get('state', 'unknown')} "
            f"color={status_color} "
            f"owner={node.get('accountable_owner', 'user')} "
            f"margin={node.get('tolerance_margin_percent', 'unknown')} "
            f"pressure={node.get('tolerance_pressure_percent', 'unknown')} "
            f"inbox={node.get('inbox_count', 0)} outbox={node.get('outbox_count', 0)} "
            f"wait={node.get('wait_status', 'none')} "
            f"provider={((node.get('assignment') or {}).get('provider') if isinstance(node.get('assignment'), dict) else None) or 'none'} "
            f"provider_model={((node.get('assignment') or {}).get('provider_model') if isinstance(node.get('assignment'), dict) else None) or 'none'} "
            f"spawn_source={node.get('spawn_source', 'none') or 'none'}"
        )
        lines.append(f"  description={node.get('description') or prince2_node_description(node)}")
        lines.append(
            f"  antagonist={node.get('antagonist_name', 'unknown')} "
            f"pressure={node.get('antagonist_pressure_percent', 0)}"
        )
        if node.get("devil_advocate"):
            lines.append(f"  devil_advocate={node.get('devil_advocate')}")
        evidence_signals = [str(item) for item in node.get("evidence_signals", []) if str(item).strip()]
        if evidence_signals:
            lines.append(f"  evidence_signals={', '.join(evidence_signals)}")
        decision_kpis = node.get("decision_kpis", {}) if isinstance(node.get("decision_kpis", {}), dict) else {}
        if isinstance(decision_kpis, dict) and decision_kpis:
            lines.append("  decision_kpis=" + ", ".join(f"{key}={decision_kpis.get(key, 0)}" for key in sorted(decision_kpis)))
        lines.append(
            f"  thread_tokens total={node.get('thread_token_count', 0)} "
            f"business_case={node.get('business_case_token_count', 0)} "
            f"input={node.get('business_case_input_token_count', 0)} "
            f"output={node.get('business_case_output_token_count', 0)} "
            f"cost_usd={node.get('business_case_cost_usd', 0)} child_count={node.get('child_count', 0)}"
        )
        pricing = node.get("pricing", {}) if isinstance(node.get("pricing", {}), dict) else {}
        if pricing:
            lines.append(
                f"  pricing input_usd={pricing.get('cost_per_input_token_usd', 'none')} "
                f"output_usd={pricing.get('cost_per_output_token_usd', 'none')} "
                f"source={pricing.get('source', 'unknown')}"
            )
        kpi_tokens = node.get("kpi_token_counts", {}) if isinstance(node.get("kpi_token_counts", {}), dict) else {}
        if isinstance(kpi_tokens, dict) and kpi_tokens:
            lines.append("  kpi_tokens=" + ", ".join(f"{theme}:{kpi_tokens.get(theme, 0)}" for theme in PRINCE2_THEME_NAMES))
        lines.append(f"  switch_hint=role switch {node.get('node_id', 'unknown')}")
    return "\n".join(lines)


def prince2_node_active_report(handoff: Any) -> dict[str, Any]:
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    if not runtime or not nodes:
        return {
            "command": "roles active",
            "status": "missing",
            "message": "No materialized PRINCE2 node runtime. Approve a role-tree baseline first.",
            "nodes": [],
        }
    active_nodes = []
    for node in nodes:
        state = handoff._node_tolerance_state(node)
        if state == "completed":
            continue
        active_nodes.append(
            {
                "node_id": str(node.get("node_id", "")),
                "label": str(node.get("label", node.get("node_id", ""))),
                "state": state or "idle",
                "tolerance_state": state or "idle",
                "wait_status": str(node.get("wait_status", "none")),
                "inbox_count": int(node.get("inbox_count", 0) or 0),
                "outbox_count": int(node.get("outbox_count", 0) or 0),
                "provider": ((node.get("assignment") or {}).get("provider") if isinstance(node.get("assignment"), dict) else None) or "none",
                "provider_model": ((node.get("assignment") or {}).get("provider_model") if isinstance(node.get("assignment"), dict) else None) or "none",
                "last_transition_at": str(node.get("last_transition_at", "")),
                "business_case_token_count": int(node.get("business_case_token_count", 0) or 0),
                "business_case_input_token_count": int(node.get("business_case_input_token_count", 0) or 0),
                "business_case_output_token_count": int(node.get("business_case_output_token_count", 0) or 0),
                "business_case_input_cost_usd": float(node.get("business_case_input_cost_usd", 0.0) or 0.0),
                "business_case_output_cost_usd": float(node.get("business_case_output_cost_usd", 0.0) or 0.0),
                "business_case_cost_usd": float(node.get("business_case_cost_usd", 0.0) or 0.0),
                "pricing": dict(node.get("pricing", {})) if isinstance(node.get("pricing", {}), dict) else {},
                "thread_token_count": int(node.get("thread_token_count", 0) or 0),
                "child_count": int(node.get("child_count", 0) or 0),
                "spawn_source": str(node.get("spawn_source", "")),
                "spawn_reason": str(node.get("spawn_reason", "")),
                "antagonist_name": str(node.get("antagonist_name", "")),
                "antagonist_pressure_percent": float(node.get("antagonist_pressure_percent", 0.0) or 0.0),
                "decision_kpis": dict(node.get("decision_kpis", {})) if isinstance(node.get("decision_kpis", {}), dict) else {},
            }
        )
    return {
        "command": "roles active",
        "status": "ok",
        "count": len(active_nodes),
        "nodes": active_nodes,
    }


def rendered_prince2_node_active(handoff: Any) -> str:
    report = prince2_node_active_report(handoff)
    if report["status"] == "missing":
        return "PRINCE2 active nodes: missing\n- action: run /project start, /roles tree approve, or /project tree approve first."
    stage_view_data = stage_view(handoff)
    lines = ["PRINCE2 active nodes:"]
    lines.append(f"- session_state: {stage_view_data['session_state']}")
    lines.append(f"- session_recoverable: {str(bool(stage_view_data['session_recoverable'])).lower()}")
    nodes = [node for node in report.get("nodes", []) if isinstance(node, dict)]
    if not nodes:
        lines.append("- none")
        return "\n".join(lines)
    for node in nodes:
        status_color = prince2_status_color(node, runtime_state=str(node.get("state", "")))
        lines.append(
            f"- {node.get('label')} [{node.get('node_id')}]: mnemonic={node.get('mnemonic', 'none')} "
            f"team={node.get('team_name', 'none')} state={node.get('state')} "
            f"color={status_color} "
            f"owner={node.get('accountable_owner', 'user')} "
            f"margin={node.get('tolerance_margin_percent', 'unknown')} "
            f"pressure={node.get('tolerance_pressure_percent', 'unknown')} "
            f"tolerance_state={node.get('tolerance_state', node.get('state'))} "
            f"wait={node.get('wait_status')} inbox={node.get('inbox_count')} outbox={node.get('outbox_count')} "
            f"mode={node.get('mode', 'manual')} "
            f"provider={node.get('provider')} provider_model={node.get('provider_model')} "
            f"spawn_source={node.get('spawn_source', 'none') or 'none'}"
        )
        lines.append(f"  description={node.get('description') or prince2_node_description(node)}")
        lines.append(
            f"  antagonist={node.get('antagonist_name', 'unknown')} "
            f"pressure={node.get('antagonist_pressure_percent', 0)}"
        )
        lines.append(
            f"  thread_tokens total={node.get('thread_token_count', 0)} "
            f"business_case={node.get('business_case_token_count', 0)} "
            f"input={node.get('business_case_input_token_count', 0)} "
            f"output={node.get('business_case_output_token_count', 0)} "
            f"cost_usd={node.get('business_case_cost_usd', 0)} child_count={node.get('child_count', 0)}"
        )
        pricing = node.get("pricing", {}) if isinstance(node.get("pricing", {}), dict) else {}
        if pricing:
            lines.append(
                f"  pricing input_usd={pricing.get('cost_per_input_token_usd', 'none')} "
                f"output_usd={pricing.get('cost_per_output_token_usd', 'none')} "
                f"source={pricing.get('source', 'unknown')}"
            )
        lines.append(f"  switch_hint=role switch {node.get('node_id', 'unknown')}")
    return "\n".join(lines)


def prince2_node_queue_report(handoff: Any) -> dict[str, Any]:
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    if not runtime or not nodes:
        return {
            "command": "roles queues",
            "status": "missing",
            "message": "No materialized PRINCE2 node runtime. Approve a role-tree baseline first.",
            "queues": [],
            "summary": {"inbox_total": 0, "outbox_total": 0, "nodes_with_inbox": 0, "nodes_with_outbox": 0},
        }
    queues = []
    inbox_total = 0
    outbox_total = 0
    nodes_with_inbox = 0
    nodes_with_outbox = 0
    for node in nodes:
        inbox_count = int(node.get("inbox_count", 0) or 0)
        outbox_count = int(node.get("outbox_count", 0) or 0)
        inbox_total += inbox_count
        outbox_total += outbox_count
        if inbox_count:
            nodes_with_inbox += 1
        if outbox_count:
            nodes_with_outbox += 1
        queues.append(
            {
                "node_id": str(node.get("node_id", "")),
                "label": str(node.get("label", node.get("node_id", ""))),
                "state": str(node.get("state", "unknown")),
                "inbox_count": inbox_count,
                "outbox_count": outbox_count,
                "wait_status": str(node.get("wait_status", "none")),
            }
        )
    return {
        "command": "roles queues",
        "status": "ok",
        "summary": {
            "inbox_total": inbox_total,
            "outbox_total": outbox_total,
            "nodes_with_inbox": nodes_with_inbox,
            "nodes_with_outbox": nodes_with_outbox,
        },
        "queues": queues,
    }


def rendered_prince2_node_queues(handoff: Any) -> str:
    report = prince2_node_queue_report(handoff)
    if report["status"] == "missing":
        return "PRINCE2 node queues: missing\n- action: run /project start, /roles tree approve, or /project tree approve first."
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    lines = [
        "PRINCE2 node queues:",
        f"- inbox_total: {summary.get('inbox_total', 0)} outbox_total={summary.get('outbox_total', 0)}",
        f"- nodes_with_inbox: {summary.get('nodes_with_inbox', 0)} nodes_with_outbox={summary.get('nodes_with_outbox', 0)}",
    ]
    queues = [item for item in report.get("queues", []) if isinstance(item, dict)]
    if not queues:
        lines.append("- none")
        return "\n".join(lines)
    for item in queues:
        lines.append(
            f"- {item.get('label')} [{item.get('node_id')}]: state={item.get('state')} "
            f"wait={item.get('wait_status')} inbox={item.get('inbox_count')} outbox={item.get('outbox_count')}"
        )
    return "\n".join(lines)


def prince2_node_control_report(handoff: Any) -> dict[str, Any]:
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    if not runtime or not nodes:
        return {
            "command": "roles control",
            "status": "missing",
            "message": "No materialized PRINCE2 node runtime. Approve a role-tree baseline first.",
            "decision": {
                "next_action": "materialize_runtime",
                "board_signal": "missing_runtime",
                "reason": "No active runtime is available for stage control.",
            },
            "summary": handoff.prince2_node_runtime_summary(),
            "critical_nodes": [],
        }
    active = prince2_node_active_report(handoff)
    queues = prince2_node_queue_report(handoff)
    active_nodes = [node for node in active.get("nodes", []) if isinstance(node, dict)]
    queue_rows = {str(item.get("node_id", "")): item for item in queues.get("queues", []) if isinstance(item, dict)}
    critical_nodes: list[dict[str, Any]] = []
    waiting_nodes = 0
    blocked_nodes = 0
    escalated_nodes = 0
    inbox_nodes = 0
    for node in active_nodes:
        node_id = str(node.get("node_id", ""))
        state = handoff._node_tolerance_state(node)
        wait_status = str(node.get("wait_status", "none")).strip().lower() or "none"
        inbox_count = int(node.get("inbox_count", 0) or 0)
        outbox_count = int(node.get("outbox_count", 0) or 0)
        reasons: list[str] = []
        severity = "monitor"
        if state == "escalated":
            escalated_nodes += 1
            severity = "exception"
            margin = handoff._node_tolerance_margin(node)
            pressure = handoff._node_tolerance_pressure(node)
            antagonist_pressure = handoff._node_antagonist_pressure(node)
            reasons.append(f"tolerance pressure {pressure:.2f}% exceeds margin {margin:.2f}%")
            if antagonist_pressure > 0:
                reasons.append(
                    f"antagonist pressure {antagonist_pressure:.2f}% drives risks and anti-benefits above control limits"
                )
        if state == "blocked":
            blocked_nodes += 1
            severity = "exception"
            reasons.append("node blocked and requires intervention")
        if state == "waiting":
            waiting_nodes += 1
            severity = "warning" if severity != "exception" else severity
            reasons.append(f"node waiting for trigger: {wait_status}")
        if inbox_count > 0:
            inbox_nodes += 1
            if severity == "monitor":
                severity = "warning"
            reasons.append(f"{inbox_count} queued inbound message(s)")
        if outbox_count > 0 and not reasons:
            reasons.append(f"{outbox_count} outbound message(s) pending visibility")
        if reasons:
            queue_row = queue_rows.get(node_id, {})
            child_ids = [
                str(item.get("node_id", ""))
                for item in nodes
                if str(item.get("parent_id", "")).strip() == node_id and str(item.get("node_id", "")).strip()
            ]
            decision_kpis = dict(node.get("decision_kpis", {})) if isinstance(node.get("decision_kpis", {}), dict) else {}
            critical_nodes.append(
                {
                    "node_id": node_id,
                    "label": str(node.get("label", node_id)),
                    "state": state,
                    "wait_status": wait_status,
                    "inbox_count": inbox_count,
                    "outbox_count": outbox_count,
                    "severity": severity,
                    "reasons": reasons,
                    "provider": str(node.get("provider", "none")),
                    "provider_model": str(node.get("provider_model", "none")),
                    "accountable_owner": str(node.get("accountable_owner", "user")),
                    "tolerance_margin_percent": handoff._node_tolerance_margin(node),
                    "tolerance_pressure_percent": handoff._node_tolerance_pressure(node),
                    "autonomy_rule": str(node.get("autonomy_rule", "")),
                    "queue_state": str(queue_row.get("state", state)),
                    "child_ids": child_ids,
                    "child_count": len(child_ids),
                    "business_case_token_count": int(node.get("business_case_token_count", 0) or 0),
                    "business_case_input_token_count": int(node.get("business_case_input_token_count", 0) or 0),
                    "business_case_output_token_count": int(node.get("business_case_output_token_count", 0) or 0),
                    "business_case_input_cost_usd": float(node.get("business_case_input_cost_usd", 0.0) or 0.0),
                    "business_case_output_cost_usd": float(node.get("business_case_output_cost_usd", 0.0) or 0.0),
                    "business_case_cost_usd": float(node.get("business_case_cost_usd", 0.0) or 0.0),
                    "pricing": dict(node.get("pricing", {})) if isinstance(node.get("pricing", {}), dict) else {},
                    "thread_token_count": int(node.get("thread_token_count", 0) or 0),
                    "kpi_token_counts": dict(node.get("kpi_token_counts", {})) if isinstance(node.get("kpi_token_counts", {}), dict) else {},
                    "antagonist_name": str(node.get("antagonist_name", "")),
                    "antagonist_pressure_percent": float(node.get("antagonist_pressure_percent", 0.0) or 0.0),
                    "devil_advocate": str(node.get("devil_advocate", "")),
                    "evidence_signals": list(node.get("evidence_signals", [])) if isinstance(node.get("evidence_signals", []), list) else [],
                    "evidence_refs": list(node.get("evidence_refs", [])) if isinstance(node.get("evidence_refs", []), list) else [],
                    "decision_kpis": decision_kpis,
                }
            )
    summary = handoff.prince2_node_runtime_summary()
    queue_summary = queues.get("summary", {}) if isinstance(queues.get("summary"), dict) else {}
    completed = int(summary.get("completed", 0) or 0)
    total_nodes = int(summary.get("nodes", 0) or 0)
    active_count = int(active.get("count", 0) or 0)
    if escalated_nodes or blocked_nodes:
        decision = {
            "next_action": "escalate_board_decision",
            "board_signal": "exception",
            "reason": "At least one runtime node is blocked or escalated beyond local control.",
        }
    elif waiting_nodes:
        decision = {
            "next_action": "unblock_waiting_nodes",
            "board_signal": "attention",
            "reason": "Waiting nodes need authorized wake triggers or upstream decisions.",
        }
    elif int(queue_summary.get("inbox_total", 0) or 0) > 0:
        decision = {
            "next_action": "process_queued_work",
            "board_signal": "attention",
            "reason": "Inbound queues contain governed work that should be consumed before closing the stage.",
        }
    elif active_count and completed < total_nodes:
        decision = {
            "next_action": "continue_execution",
            "board_signal": "go",
            "reason": "Runtime is progressing within delegated control and can continue.",
        }
    else:
        decision = {
            "next_action": "stage_ready_for_gate",
            "board_signal": "review",
            "reason": "No active pressure remains; prepare the next gate or close the stage.",
        }
    return {
        "command": "roles control",
        "status": "ok",
        "summary": summary,
        "queue_summary": queue_summary,
        "decision": decision,
        "critical_nodes": critical_nodes,
        "active_nodes": active_count,
        "completed_nodes": completed,
        "waiting_nodes": waiting_nodes,
        "blocked_nodes": blocked_nodes,
        "escalated_nodes": escalated_nodes,
        "queued_inbox_nodes": inbox_nodes,
    }


def rendered_prince2_node_control(handoff: Any) -> str:
    report = prince2_node_control_report(handoff)
    if report["status"] == "missing":
        return "PRINCE2 control view: missing\n- action: run /project start, /roles tree approve, or /project tree approve first."
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    queue_summary = report.get("queue_summary", {}) if isinstance(report.get("queue_summary"), dict) else {}
    lines = [
        "PRINCE2 control view:",
        f"- board_signal: {decision.get('board_signal', 'unknown')} next_action={decision.get('next_action', 'unknown')}",
        f"- reason: {decision.get('reason', 'none')}",
        f"- nodes: {summary.get('nodes', 0)} active={report.get('active_nodes', 0)} completed={report.get('completed_nodes', 0)}",
        f"- waiting: {report.get('waiting_nodes', 0)} blocked={report.get('blocked_nodes', 0)} escalated={report.get('escalated_nodes', 0)}",
        f"- queues: inbox_total={queue_summary.get('inbox_total', 0)} outbox_total={queue_summary.get('outbox_total', 0)} inbox_nodes={report.get('queued_inbox_nodes', 0)}",
    ]
    critical_nodes = [item for item in report.get("critical_nodes", []) if isinstance(item, dict)]
    if not critical_nodes:
        lines.append("- critical_nodes: none")
        return "\n".join(lines)
    lines.append("- critical_nodes:")
    for node in critical_nodes:
        lines.append(
            f"  - {node.get('label')} [{node.get('node_id')}]: mnemonic={node.get('mnemonic', 'none')} "
            f"team={node.get('team_name', 'none')} severity={node.get('severity')} "
            f"state={node.get('state')} wait={node.get('wait_status')} "
            f"owner={node.get('accountable_owner', 'user')} margin={node.get('tolerance_margin_percent', 'unknown')} "
            f"pressure={node.get('tolerance_pressure_percent', 'unknown')} "
            f"inbox={node.get('inbox_count')} outbox={node.get('outbox_count')} "
            f"mode={node.get('mode', 'manual')} "
            f"reasons={'; '.join(str(item) for item in node.get('reasons', []))}"
        )
        lines.append(
            f"    thread_tokens total={node.get('thread_token_count', 0)} "
            f"business_case={node.get('business_case_token_count', 0)} "
            f"input={node.get('business_case_input_token_count', 0)} "
            f"output={node.get('business_case_output_token_count', 0)} "
            f"cost_usd={node.get('business_case_cost_usd', 0)} child_count={node.get('child_count', 0)}"
        )
        pricing = node.get("pricing", {}) if isinstance(node.get("pricing", {}), dict) else {}
        if pricing:
            lines.append(
                f"    pricing input_usd={pricing.get('cost_per_input_token_usd', 'none')} "
                f"output_usd={pricing.get('cost_per_output_token_usd', 'none')} "
                f"source={pricing.get('source', 'unknown')}"
            )
        lines.append(
            f"    antagonist={node.get('antagonist_name', 'unknown')} "
            f"pressure={node.get('antagonist_pressure_percent', 0)} "
            f"decision_kpis={node.get('decision_kpis', {})}"
        )
        if node.get("devil_advocate"):
            lines.append(f"    devil_advocate={node.get('devil_advocate')}")
        evidence_signals = [str(item) for item in node.get("evidence_signals", []) if str(item).strip()]
        if evidence_signals:
            lines.append(f"    evidence_signals={', '.join(evidence_signals)}")
        child_ids = [str(item) for item in node.get("child_ids", []) if str(item).strip()]
        if child_ids:
            lines.append(f"    child_ids={', '.join(child_ids)}")
        lines.append(f"    switch_hint=role switch {node.get('node_id', 'unknown')}")
    return "\n".join(lines)


def prince2_node_messages_report(handoff: Any, node_id: str | None = None) -> dict[str, Any]:
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    if not runtime or not nodes:
        return {
            "command": "roles messages",
            "status": "missing",
            "message": "No materialized PRINCE2 node runtime. Approve a role-tree baseline first.",
            "nodes": [],
    }
    baseline = handoff.prince2_role_tree_baseline if isinstance(handoff.prince2_role_tree_baseline, dict) else {}
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    baseline_nodes = {
        str(item.get("node_id", "")).strip(): item
        for item in tree.get("nodes", [])
        if isinstance(item, dict) and str(item.get("node_id", "")).strip()
    }
    selected: list[dict[str, Any]] = []
    for node in nodes:
        if node_id and str(node.get("node_id", "")).strip() != node_id:
            continue
        inbox = [dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]
        outbox = [dict(item) for item in node.get("outbox", []) if isinstance(item, dict)]
        transcript: list[dict[str, Any]] = []
        for item in inbox:
            entry = dict(item)
            entry["direction"] = "inbox"
            transcript.append(entry)
        for item in outbox:
            entry = dict(item)
            entry["direction"] = "outbox"
            transcript.append(entry)
        transcript.sort(key=lambda item: (str(item.get("timestamp", "")), str(item.get("message_id", "")), str(item.get("direction", ""))))
        role_type = str((baseline_nodes.get(str(node.get("node_id", "")).strip()) or {}).get("role_type") or node.get("role_type", "")).strip()
        selected.append(
            {
                "node_id": str(node.get("node_id", "")),
                "label": str(node.get("label", node.get("node_id", ""))),
                "role_type": role_type,
                "mnemonic": prince2_role_mnemonic(role_type) if role_type else str(node.get("mnemonic", "")),
                "team_name": prince2_role_team_name(role_type) if role_type else str(node.get("team_name", "")),
                "mode": str(node.get("mode", "manual")),
                "state": str(node.get("state", "unknown")),
                "wait_status": str(node.get("wait_status", "none")),
                "business_case_cost_usd": float(node.get("business_case_cost_usd", 0.0) or 0.0),
                "business_case_token_count": int(node.get("business_case_token_count", 0) or 0),
                "business_case_input_token_count": int(node.get("business_case_input_token_count", 0) or 0),
                "business_case_output_token_count": int(node.get("business_case_output_token_count", 0) or 0),
                "pricing": dict(node.get("pricing", {})) if isinstance(node.get("pricing", {}), dict) else {},
                "inbox": inbox,
                "outbox": outbox,
                "transcript": transcript,
            }
        )
    return {
        "command": "roles messages",
        "status": "ok",
        "node_filter": node_id,
        "count": len(selected),
        "nodes": selected,
    }


def rendered_prince2_node_messages(handoff: Any, node_id: str | None = None) -> str:
    report = prince2_node_messages_report(handoff, node_id=node_id)
    if report["status"] == "missing":
        return "PRINCE2 node messages: missing\n- action: run /project start, /roles tree approve, or /project tree approve first."
    lines = ["PRINCE2 node messages:"]
    if report.get("node_filter"):
        lines.append(f"- node_filter: {report['node_filter']}")
    nodes = [node for node in report.get("nodes", []) if isinstance(node, dict)]
    if not nodes:
        lines.append("- none")
        return "\n".join(lines)
    for node in nodes:
        lines.append(
            f"- {node.get('label')} [{node.get('node_id')}]: mnemonic={node.get('mnemonic') or 'none'} "
            f"team={node.get('team_name') or 'none'} mode={node.get('mode', 'manual')} "
            f"state={node.get('state')} wait={node.get('wait_status')} "
            f"inbox={len(node.get('inbox', []))} outbox={len(node.get('outbox', []))} "
            f"business_case_tokens={node.get('business_case_token_count', 0)} "
            f"cost_usd={node.get('business_case_cost_usd', 0.0)}"
        )
        pricing = node.get("pricing", {}) if isinstance(node.get("pricing", {}), dict) else {}
        if pricing:
            lines.append(
                f"  pricing input_usd={pricing.get('cost_per_input_token_usd', 'none')} "
                f"output_usd={pricing.get('cost_per_output_token_usd', 'none')} "
                f"source={pricing.get('source', 'unknown')}"
            )
        transcript = [item for item in node.get("transcript", []) if isinstance(item, dict)]
        if not transcript:
            lines.append("  chat: none")
            continue
        lines.append("  chat:")
        for item in transcript:
            direction = str(item.get("direction", "inbox")).lower()
            arrow = "<-" if direction == "inbox" else "->"
            summary = str(item.get("summary", "")).strip().replace(" ", "_")
            lines.append(
                f"    [{item.get('timestamp', 'unknown')}] {item.get('source_node')} {arrow} {item.get('target_node')} "
                f"edge={item.get('edge_id')} message={item.get('message_id')} status={item.get('status', 'queued')} "
                f"payload={','.join(item.get('payload_scope', []))}"
            )
            if summary:
                lines.append(f"      summary={summary}")
            evidence = ",".join(item.get("evidence_refs", []))
            if evidence:
                lines.append(f"      evidence={evidence}")
            expected = ",".join(item.get("expected_evidence", []))
            if expected:
                lines.append(f"      expected_evidence={expected}")
            validation = str(item.get("validation_condition", "")).strip()
            if validation:
                lines.append(f"      validation={validation}")
            authority = str(item.get("decision_authority", "")).strip()
            if authority:
                lines.append(f"      authority={authority}")
    return "\n".join(lines)


def _render_handoff(config: AgentConfig) -> str:
    handoff = ProjectHandoff.load(config.handoff_path)
    lines = [
        "Project handoff:",
        handoff.summary(),
        handoff.rendered_operational_posture(),
        handoff.rendered_stage_view(),
        handoff.rendered_prince2_node_runtime(),
        handoff.rendered_implementation_backlog(),
    ]
    if handoff.entries:
        lines.append("Recent handoff entries:")
        for entry in handoff.entries[-8:]:
            lines.append(
                f"- [{entry.phase}] iter={entry.iteration} step={entry.step_id or '-'} "
                f"status={entry.step_status or '-'} model={entry.model or '-'} "
                f"head={entry.git_head or 'unknown'}"
            )
    return "\n".join(lines)


def _handoff_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "handoff",
        "schema": json_schema("handoff"),
        "handoff": handoff.as_dict(),
        "goal": handoff.goal_view(),
        "stage_view": handoff.stage_view(),
        "node_runtime": handoff.prince2_node_runtime_report(),
        "next_action": handoff.rendered_next_action(),
    }


ACTION_PHASE_PREFIXES = (
    "project_",
    "role_",
    "model_",
    "account_",
    "permission_",
    "git_",
    "shell_",
    "sources_",
    "update_",
    "extension_",
    "web_",
    "download_",
    "checksum_",
    "compress_",
    "archive_",
)


def _is_handoff_action_entry(entry: HandoffEntry) -> bool:
    return (
        entry.phase.endswith("_approval")
        or entry.phase.endswith("_blocked")
        or entry.phase.startswith(ACTION_PHASE_PREFIXES)
    )


def _handoff_action_payload(entry: HandoffEntry) -> dict[str, object]:
    return {
        "timestamp": entry.timestamp,
        "phase": entry.phase,
        "task": entry.task,
        "summary": entry.summary,
        "git_head": entry.git_head,
        "details": dict(entry.details),
    }


def _latest_handoff_action(config: AgentConfig) -> dict[str, object] | None:
    handoff = ProjectHandoff.load(config.handoff_path)
    for entry in reversed(handoff.entries):
        if _is_handoff_action_entry(entry):
            return _handoff_action_payload(entry)
    return None


def _focus_snapshot(agent: Any, config: AgentConfig) -> dict[str, object]:
    from . import main as _main

    handoff = ProjectHandoff.load(config.handoff_path)
    prefs = _main._load_model_preferences(config)
    memory = MemoryStore.load(config.memory_path)
    model_report = _main._model_status_report(agent, config)
    active_model = next((item for item in model_report["models"] if item["preferred"]), None)
    if active_model is None:
        active_model = next((item for item in model_report["models"] if item["active"]), None)
    latest_attempt = memory.latest_attempt()
    latest_tool = memory.latest_tool_event()
    active_provider = None if active_model is None else active_model["provider"]
    latest_limit = None
    if active_provider:
        latest_limit = dict(prefs.provider_limit_snapshot_by_model or {}).get(str(active_provider))
    return {
        "task": handoff.task or "none",
        "current_step": handoff.current_step_id or "none",
        "current_step_status": handoff.current_step_status or "none",
        "session_state": handoff.status or "none",
        "session_recoverable": handoff.status in {"initiating", "planned", "executing", "waiting", "exception"},
        "next_action": handoff.rendered_next_action(),
        "boundary_decision": handoff.stage_view()["boundary_decision"],
        "active_provider": None if active_model is None else active_model["provider"],
        "active_provider_model": None if active_model is None else active_model["provider_model"],
        "active_account": "none"
        if active_model is None
        else ((prefs.active_account_by_model or {}).get(str(active_model["provider"])) or "none"),
        "active_provider_model_params": {} if active_model is None else dict(active_model["provider_model_params"]),
        "latest_model_attempt": None
        if latest_attempt is None
        else {
            "step": latest_attempt.step_id,
            "action": latest_attempt.action_type,
            "status": "ok" if latest_attempt.success else f"failed:{latest_attempt.error_type or 'unknown'}",
            "provider": latest_attempt.model,
            "provider_model": latest_attempt.variant or "provider-default",
        },
        "latest_tool_evidence": None
        if latest_tool is None
        else {
            "tool": latest_tool.tool,
            "action": latest_tool.action_type,
            "status": "ok" if latest_tool.success else f"failed:{latest_tool.error_type or 'unknown'}",
        },
        "active_limit": None
        if not isinstance(latest_limit, dict)
        else {
            "status": latest_limit.get("status"),
            "reason": latest_limit.get("reason"),
            "blocked_until": latest_limit.get("blocked_until"),
            "stale": bool(latest_limit.get("stale", False)),
        },
        "latest_handoff_action": _latest_handoff_action(config),
        "resume_ready": bool(handoff.task) and handoff.status in {"initiating", "planned", "executing", "waiting", "exception"},
    }


def _handoff_actions_report(config: AgentConfig, *, limit: int = 20) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    safe_limit = max(1, min(int(limit), 200))
    action_entries = [entry for entry in handoff.entries if _is_handoff_action_entry(entry)]
    selected = action_entries[-safe_limit:]
    return {
        "command": "handoff actions",
        "count": len(action_entries),
        "limit": safe_limit,
        "entries": [_handoff_action_payload(entry) for entry in selected],
    }


def _render_handoff_actions(config: AgentConfig, *, limit: int = 20) -> str:
    report = _handoff_actions_report(config, limit=limit)
    lines = [
        "Handoff actions:",
        f"- count: {report['count']}",
        f"- showing: {len(report['entries'])}/{report['count']}",
    ]
    entries = report["entries"]
    if not isinstance(entries, list) or not entries:
        lines.append("- none")
        return "\n".join(lines)
    for item in entries:
        if not isinstance(item, dict):
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        detail_keys = ", ".join(sorted(details)) if details else "none"
        lines.append(
            f"- [{item.get('phase')}] {item.get('summary')} "
            f"task={item.get('task') or 'none'} head={item.get('git_head') or 'unknown'} details={detail_keys}"
        )
    return "\n".join(lines)


def _parse_optional_limit(parts: list[str], *, default: int = 20) -> int:
    if len(parts) <= 2:
        return default
    try:
        return max(1, min(int(parts[2]), 200))
    except ValueError:
        return default


def _render_resume_show(config: AgentConfig) -> str:
    handoff = ProjectHandoff.load(config.handoff_path)
    from . import main as _main

    agent = _main._configure_readonly_agent_for_workspace(config)
    focus = _focus_snapshot(agent, config)
    lines = [
        "Resume target:",
        f"- task: {handoff.task or 'none'}",
        f"- current_step: {handoff.current_step_id or 'none'}",
        f"- current_step_status: {handoff.current_step_status or 'none'}",
        f"- session_state: {handoff.status or 'none'}",
        f"- session_recoverable: {str(handoff.status in {'initiating', 'planned', 'executing', 'waiting', 'exception'}).lower()}",
        f"- next_action: {handoff.rendered_next_action()}",
        f"- active_route: provider={focus['active_provider'] or 'none'} account={focus['active_account']} provider_model={focus['active_provider_model'] or 'none'}",
        f"- resume_ready: {str(bool(focus['resume_ready'])).lower()}",
        handoff.rendered_stage_view(),
    ]
    return "\n".join(lines)


def _resume_context_payload(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    memory = MemoryStore.load(config.memory_path)
    from . import main as _main

    agent = _main._configure_readonly_agent_for_workspace(config)
    focus = _focus_snapshot(agent, config)
    latest_attempt = memory.latest_attempt()
    latest_tool = memory.latest_tool_event()
    latest_snapshot = handoff.latest_git_snapshot()
    attempt_payload: dict[str, object] | None = None
    if latest_attempt is not None:
        attempt_payload = {
            "step": latest_attempt.step_id,
            "action": latest_attempt.action_type,
            "status": "ok" if latest_attempt.success else f"failed:{latest_attempt.error_type or 'unknown'}",
            "route": {
                "model": latest_attempt.model,
                "provider": latest_attempt.model,
                "account": latest_attempt.account or "none",
                "variant": latest_attempt.variant or "provider-default",
                "provider_model": latest_attempt.variant or "provider-default",
            },
            "observation": (latest_attempt.observation or "none").strip().replace("\n", " ")[:200],
        }
    tool_payload: dict[str, object] | None = None
    if latest_tool is not None:
        tool_payload = {
            "tool": latest_tool.tool,
            "action": latest_tool.action_type,
            "status": "ok" if latest_tool.success else f"failed:{latest_tool.error_type or 'unknown'}",
            "duration_ms": latest_tool.duration_ms or 0,
            "summary": latest_tool.summary,
        }
    snapshot_payload: dict[str, object] | None = None
    if latest_snapshot is not None:
        snapshot_payload = {
            "git_head": latest_snapshot["git_head"],
            "summary": latest_snapshot["summary"],
            "timestamp": latest_snapshot["timestamp"],
        }
    return {
        "command": "resume context",
        "schema": json_schema("resume context"),
        "task": handoff.task or "none",
        "current_step": handoff.current_step_id or "none",
        "current_step_status": handoff.current_step_status or "none",
        "session_state": handoff.status or "none",
        "session_recoverable": handoff.status in {"initiating", "planned", "executing", "waiting", "exception"},
        "active_route": {
            "provider": focus["active_provider"] or "none",
            "account": focus["active_account"],
            "provider_model": focus["active_provider_model"] or "none",
            "params": focus["active_provider_model_params"],
        },
        "resume_ready": bool(focus["resume_ready"]),
        "boundary_decision": focus["boundary_decision"],
        "latest_model_attempt": attempt_payload,
        "latest_tool_evidence": tool_payload,
        "latest_git_snapshot": snapshot_payload,
        "active_limit": focus["active_limit"],
    }


def _render_resume_context(config: AgentConfig) -> str:
    payload = _resume_context_payload(config)
    lines = [
        "Resume context:",
        f"- task: {payload['task']}",
        f"- current_step: {payload['current_step']}",
        f"- current_step_status: {payload['current_step_status']}",
        f"- session_state: {payload['session_state']}",
        f"- session_recoverable: {str(bool(payload['session_recoverable'])).lower()}",
        f"- boundary_decision: {payload['boundary_decision']}",
    ]
    route = payload["active_route"]
    lines.append(
        f"- active_route: provider={route['provider']} account={route['account']} provider_model={route['provider_model']}"
    )
    params = route.get("params")
    if isinstance(params, dict) and params:
        lines.append("- active_provider_model_params: " + ",".join(f"{key}={value}" for key, value in sorted(params.items())))
    attempt = payload["latest_model_attempt"]
    if isinstance(attempt, dict):
        route = attempt["route"]
        lines.extend(
            [
                f"- latest_model_attempt: step={attempt['step']} action={attempt['action']} status={attempt['status']}",
                (
                    f"- latest_route: provider={route['provider']} "
                    f"account={route['account']} provider_model={route['provider_model']}"
                ),
                f"- latest_observation: {attempt['observation']}",
            ]
        )
    else:
        lines.append("- latest_model_attempt: none")
    tool = payload["latest_tool_evidence"]
    if isinstance(tool, dict):
        lines.append(
            f"- latest_tool_evidence: tool={tool['tool']} action={tool['action']} "
            f"status={tool['status']} duration_ms={tool['duration_ms']}"
        )
    else:
        lines.append("- latest_tool_evidence: none")
    snapshot = payload["latest_git_snapshot"]
    if isinstance(snapshot, dict):
        lines.append(f"- latest_git_snapshot: {snapshot['git_head']} :: {snapshot['summary']}")
    else:
        lines.append("- latest_git_snapshot: none")
    active_limit = payload.get("active_limit")
    if isinstance(active_limit, dict):
        blocked = f" blocked_until={active_limit['blocked_until']}" if active_limit.get("blocked_until") else ""
        reason = f" reason={active_limit['reason']}" if active_limit.get("reason") else ""
        lines.append(f"- active_provider_limit: {active_limit['status'] or 'unknown'}{blocked}{reason}")
    else:
        lines.append("- active_provider_limit: none")
    lines.append(f"- resume_ready: {str(bool(payload['resume_ready'])).lower()}")
    return "\n".join(lines)


def _resume_show_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    from . import main as _main

    agent = _main._configure_readonly_agent_for_workspace(config)
    return {
        "command": "resume --show",
        "schema": json_schema("resume --show"),
        "task": handoff.task or "none",
        "current_step": handoff.current_step_id or "none",
        "current_step_status": handoff.current_step_status or "none",
        "session_state": handoff.status or "none",
        "session_recoverable": handoff.status in {"initiating", "planned", "executing", "waiting", "exception"},
        "next_action": handoff.rendered_next_action(),
        "stage_view": handoff.stage_view(),
        "focus": _focus_snapshot(agent, config),
    }


def _archive_and_clear_handoff(config: AgentConfig) -> str:
    if not config.handoff_path.exists():
        ProjectHandoff().save(config.handoff_path)
        return "No handoff existed. Created a fresh handoff context."
    archive = config.workspace_root / f".stagewarden_handoff.archive.{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    write_text_utf8(archive, read_text_utf8(config.handoff_path))
    ProjectHandoff().save(config.handoff_path)
    return f"Archived handoff to {archive.name}. Fresh handoff context created."


def _archive_and_clear_handoff_report(config: AgentConfig) -> dict[str, object]:
    if not config.handoff_path.exists():
        ProjectHandoff().save(config.handoff_path)
        return {
            "command": "resume --clear",
            "archived": False,
            "archive_path": None,
            "message": "No handoff existed. Created a fresh handoff context.",
        }
    archive = config.workspace_root / f".stagewarden_handoff.archive.{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    write_text_utf8(archive, read_text_utf8(config.handoff_path))
    ProjectHandoff().save(config.handoff_path)
    return {
        "command": "resume --clear",
        "archived": True,
        "archive_path": archive.name,
        "message": f"Archived handoff to {archive.name}. Fresh handoff context created.",
    }


def _load_handoff_into_agent(agent: Any, config: AgentConfig) -> ProjectHandoff:
    handoff = ProjectHandoff.load(config.handoff_path)
    agent.project_handoff = handoff
    agent.executor.project_handoff = handoff
    return handoff


def _handle_resume_command(command: str, agent: Any, config: AgentConfig) -> str | None:
    parts = command.split()
    if not parts or parts[0] != "resume":
        return None
    if len(parts) == 1:
        handoff = _load_handoff_into_agent(agent, config)
        if not handoff.task:
            return "No task in handoff to resume.\n" + _render_resume_show(config)
        resumed_step_id = handoff.current_step_id or "none"
        result = agent.run(handoff.task)
        return f"Resumed from handoff step {resumed_step_id}.\n{result.message}"
    if len(parts) == 2 and parts[1] == "--show":
        return _render_resume_show(config)
    if len(parts) == 2 and parts[1] == "context":
        return _render_resume_context(config)
    if len(parts) == 2 and parts[1] == "--clear":
        _load_handoff_into_agent(agent, config)
        return _archive_and_clear_handoff(config)
    return "Usage: resume | resume --show | resume context | resume --clear"


RUNTIME_HANDOFF_START = "<!-- STAGEWARDEN_RUNTIME_HANDOFF_START -->"
RUNTIME_HANDOFF_END = "<!-- STAGEWARDEN_RUNTIME_HANDOFF_END -->"


def _redact_handoff_markdown(value: str) -> str:
    redacted = re.sub(
        r"(?i)\b(access_token|refresh_token|id_token|auth_token|api_key|token)\b\s*[:=]\s*['\"]?[^'\"\s,}\]]+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        value,
    )
    redacted = re.sub(r"(?i)bearer\s+[a-z0-9._\-]{12,}", "Bearer [REDACTED]", redacted)
    redacted = re.sub(r"\b[a-zA-Z0-9_\-]{32,}\.[a-zA-Z0-9_\-]{16,}\.[a-zA-Z0-9_\-]{16,}\b", "[REDACTED_JWT]", redacted)
    return redacted


def _runtime_handoff_markdown(config: AgentConfig) -> str:
    handoff = ProjectHandoff.load(config.handoff_path)
    memory = MemoryStore.load(config.memory_path)
    view = handoff.stage_view()
    git_boundary = view["git_boundary"]
    pid_boundary = view["pid_boundary"]
    latest_attempt = memory.latest_attempt()
    latest_tool = memory.latest_tool_event()
    latest_snapshot = handoff.latest_git_snapshot()
    lines = [
        RUNTIME_HANDOFF_START,
        "## Runtime Handoff Export",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "### Current State",
        "",
        f"- task: {handoff.task or 'unknown'}",
        f"- project_status: {handoff.status}",
        f"- plan_status: {handoff.plan_status or 'unknown'}",
        f"- recovery_state: {view['recovery_state']}",
        f"- stage_health: {view['stage_health']}",
        f"- next_action: {view['next_action']}",
        f"- current_step: {handoff.current_step_id or 'none'}",
        f"- git_boundary: baseline={git_boundary['baseline']} current={git_boundary['current']}",
        f"- pid_boundary: project_status={pid_boundary['project_status']} updated_at={pid_boundary['updated_at']}",
        "",
        "### Registers",
        "",
        handoff.rendered_register_status_summary(),
        "",
        "### Execution Resume Context",
        "",
    ]
    if latest_attempt is None:
        lines.append("- latest_model_attempt: none")
    else:
        attempt_status = "ok" if latest_attempt.success else f"failed:{latest_attempt.error_type or 'unknown'}"
        lines.extend(
            [
                f"- latest_model_attempt: step={latest_attempt.step_id} action={latest_attempt.action_type} status={attempt_status}",
                (
                    f"- latest_route: provider={latest_attempt.model} "
                    f"account={latest_attempt.account or 'none'} "
                    f"provider_model={latest_attempt.variant or 'provider-default'}"
                ),
                f"- latest_observation: {(latest_attempt.observation or 'none').strip().replace(chr(10), ' ')[:200]}",
            ]
        )
    if latest_tool is None:
        lines.append("- latest_tool_evidence: none")
    else:
        tool_status = "ok" if latest_tool.success else f"failed:{latest_tool.error_type or 'unknown'}"
        lines.append(
            f"- latest_tool_evidence: tool={latest_tool.tool} action={latest_tool.action_type} "
            f"status={tool_status} duration_ms={latest_tool.duration_ms or 0}"
        )
    if latest_snapshot is None:
        lines.append("- latest_git_snapshot: none")
    else:
        lines.append(
            f"- latest_git_snapshot: {latest_snapshot['git_head']} :: {latest_snapshot['summary']}"
        )
    lines.extend(
        [
            "",
            "### Implementation Backlog",
            "",
            handoff.rendered_implementation_backlog(),
            "",
            "### Risks",
            "",
            handoff.rendered_risks(),
            "",
            "### Issues",
            "",
            handoff.rendered_issues(),
            "",
            "### Quality",
            "",
            handoff.rendered_quality(),
            "",
            "### Lessons",
            "",
            handoff.rendered_lessons(),
            "",
            "### Recent Entries",
            "",
        ]
    )
    if handoff.entries:
        for entry in handoff.entries[-8:]:
            lines.append(
                f"- [{entry.phase}] iter={entry.iteration} step={entry.step_id or '-'} "
                f"status={entry.step_status or '-'} model={entry.model or '-'} head={entry.git_head or 'unknown'}"
            )
    else:
        lines.append("- none")
    lines.extend(["", RUNTIME_HANDOFF_END, ""])
    return _redact_handoff_markdown("\n".join(lines))


def _export_handoff_markdown(config: AgentConfig) -> str:
    target = config.workspace_root / "HANDOFF.md"
    generated = _runtime_handoff_markdown(config)
    existing = read_text_utf8(target) if target.exists() else "# Stagewarden Handoff\n"
    if RUNTIME_HANDOFF_START in existing and RUNTIME_HANDOFF_END in existing:
        prefix, _marker, rest = existing.partition(RUNTIME_HANDOFF_START)
        _old, _end_marker, suffix = rest.partition(RUNTIME_HANDOFF_END)
        updated = prefix.rstrip() + "\n\n" + generated.rstrip() + "\n" + suffix.lstrip()
    else:
        updated = existing.rstrip() + "\n\n" + generated
    write_text_utf8(target, updated)
    return f"Exported runtime handoff to {target.name}."


def _export_handoff_markdown_report(config: AgentConfig) -> dict[str, object]:
    target = config.workspace_root / "HANDOFF.md"
    generated = _runtime_handoff_markdown(config)
    existing = read_text_utf8(target) if target.exists() else "# Stagewarden Handoff\n"
    if RUNTIME_HANDOFF_START in existing and RUNTIME_HANDOFF_END in existing:
        prefix, _marker, rest = existing.partition(RUNTIME_HANDOFF_START)
        _old, _end_marker, suffix = rest.partition(RUNTIME_HANDOFF_END)
        updated = prefix.rstrip() + "\n\n" + generated.rstrip() + "\n" + suffix.lstrip()
    else:
        updated = existing.rstrip() + "\n\n" + generated
    write_text_utf8(target, updated)
    return {
        "command": "handoff export",
        "target": target.name,
        "updated": True,
        "message": f"Exported runtime handoff to {target.name}.",
    }


def _render_boundary(config: AgentConfig) -> str:
    handoff = ProjectHandoff.load(config.handoff_path)
    return "\n".join(
        [
            "Boundary recommendation:",
            handoff.rendered_stage_view(),
        ]
    )


def _boundary_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "boundary",
        "schema": json_schema("boundary"),
        "stage_view": handoff.stage_view(),
    }


def _board_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    stage_view = handoff.stage_view()
    register_statuses = stage_view["register_statuses"]
    business_justification = "viable"
    if handoff.status == "exception":
        business_justification = "at_risk"
    if stage_view["boundary_decision"] == "review_boundary:open_issues":
        business_justification = "review_required"
    if stage_view["boundary_decision"] == "close_project":
        recommendation = "close"
    elif stage_view["recovery_state"] in {"exception_active", "recovery_active", "recovery_cleared"}:
        recommendation = "recover"
    elif register_statuses["issues_open"] > 0 or stage_view["boundary_decision"].startswith("review_boundary:"):
        recommendation = "review"
    else:
        recommendation = "continue"
    return {
        "command": "board",
        "schema": json_schema("board"),
        "task": handoff.task or "none",
        "business_justification": business_justification,
        "boundary_decision": stage_view["boundary_decision"],
        "open_issues": register_statuses["issues_open"],
        "open_risks": register_statuses["risks_open"],
        "quality_open": register_statuses["quality_open"],
        "quality_accepted": register_statuses["quality_accepted"],
        "recovery_state": stage_view["recovery_state"],
        "recommended_authorization": recommendation,
        "next_action": stage_view["next_action"],
        "stage_view": stage_view,
    }


def _render_board(config: AgentConfig) -> str:
    report = _board_report(config)
    lines = [
        "Board review:",
        f"- task: {report['task']}",
        f"- business_justification: {report['business_justification']}",
        f"- boundary_decision: {report['boundary_decision']}",
        f"- open_issues: {report['open_issues']}",
        f"- open_risks: {report['open_risks']}",
        f"- quality_open: {report['quality_open']}",
        f"- quality_accepted: {report['quality_accepted']}",
        f"- recovery_state: {report['recovery_state']}",
        f"- recommended_authorization: {report['recommended_authorization']}",
        f"- next_action: {report['next_action']}",
    ]
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


def _render_transcript(config: AgentConfig) -> str:
    try:
        return MemoryStore.load(config.memory_path).transcript_summary()
    except (OSError, ValueError, TypeError):
        return "No tool transcript."


def _transcript_report(config: AgentConfig) -> dict[str, object]:
    try:
        return {
            "command": "transcript",
            "schema": json_schema("transcript"),
            "report": MemoryStore.load(config.memory_path).transcript_report(),
        }
    except (OSError, ValueError, TypeError):
        return {
            "command": "transcript",
            "schema": json_schema("transcript"),
            "report": MemoryStore().transcript_report(),
        }


def _log_error_report(config: AgentConfig, *, limit: int = 20) -> dict[str, object]:
    memory = MemoryStore.load(config.memory_path)
    items: list[dict[str, object]] = []
    tokens = ("error", "failed", "traceback", "exception", "denied")

    for attempt in memory.attempts[-limit:]:
        observation = str(attempt.observation or "").strip()
        combined = " ".join(part for part in (attempt.action_type, observation, attempt.error_type or "") if part).lower()
        if attempt.success and not any(token in combined for token in tokens):
            continue
        if not attempt.success or any(token in combined for token in tokens):
            items.append(
                {
                    "kind": "attempt",
                    "step_id": attempt.step_id,
                    "iteration": attempt.iteration,
                    "model": attempt.model,
                    "action_type": attempt.action_type,
                    "error_type": attempt.error_type or ("attempt_failed" if not attempt.success else None),
                    "observation": observation[:240],
                }
            )

    for record in memory.tool_transcript[-limit:]:
        summary = str(record.summary or "").strip()
        detail = str(record.detail or "").strip()
        combined = " ".join(part for part in (record.tool, record.action_type, summary, detail, record.error_type or "") if part).lower()
        if record.success and not any(token in combined for token in tokens):
            continue
        if not record.success or any(token in combined for token in tokens):
            items.append(
                {
                    "kind": "tool_transcript",
                    "step_id": record.step_id,
                    "iteration": record.iteration,
                    "tool": record.tool,
                    "action_type": record.action_type,
                    "error_type": record.error_type or ("tool_failed" if not record.success else None),
                    "summary": summary[:120],
                    "detail": detail[:200],
                }
            )

    return {
        "command": "log errors",
        "schema": json_schema("health"),
        "status": "warning" if items else "ok",
        "count": len(items),
        "items": items,
    }
