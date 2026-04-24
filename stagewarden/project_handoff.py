from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class HandoffEntry:
    timestamp: str
    phase: str
    iteration: int
    task: str
    summary: str
    step_id: str | None = None
    step_title: str | None = None
    step_status: str | None = None
    model: str | None = None
    action_type: str | None = None
    git_head: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "phase": self.phase,
            "iteration": self.iteration,
            "task": self.task,
            "summary": self.summary,
            "step_id": self.step_id,
            "step_title": self.step_title,
            "step_status": self.step_status,
            "model": self.model,
            "action_type": self.action_type,
            "git_head": self.git_head,
            "details": dict(self.details),
        }


@dataclass(slots=True)
class ProjectHandoff:
    task: str = ""
    project_brief: dict[str, str] = field(default_factory=dict)
    status: str = "idle"
    current_step_id: str | None = None
    current_step_title: str | None = None
    current_step_status: str | None = None
    latest_observation: str = ""
    plan_status: str = ""
    git_head: str | None = None
    git_head_baseline: str | None = None
    risk_register: list[dict[str, str]] = field(default_factory=list)
    issue_register: list[dict[str, str]] = field(default_factory=list)
    quality_register: list[dict[str, str]] = field(default_factory=list)
    lessons_log: list[dict[str, str]] = field(default_factory=list)
    exception_plan: list[str] = field(default_factory=list)
    implementation_backlog: list[dict[str, str]] = field(default_factory=list)
    prince2_roles: dict[str, dict[str, Any]] = field(default_factory=dict)
    prince2_role_tree_baseline: dict[str, Any] = field(default_factory=dict)
    prince2_node_runtime: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=_utc_now)
    entries: list[HandoffEntry] = field(default_factory=list)

    def start_run(self, *, task: str, plan_status: str, git_head: str | None) -> None:
        self.task = task
        self.status = "initiating"
        self.current_step_id = None
        self.current_step_title = None
        self.current_step_status = "pending"
        self.latest_observation = "Task received."
        self.plan_status = plan_status
        self.git_head = git_head
        self.git_head_baseline = git_head
        self.updated_at = _utc_now()
        self.entries.append(
            HandoffEntry(
                timestamp=self.updated_at,
                phase="start",
                iteration=0,
                task=task,
                summary="Project context initialized.",
                git_head=git_head,
                details={"plan_status": plan_status},
            )
        )

    def record_plan(self, *, task: str, plan_status: str, checklist: dict[str, Any], git_head: str | None) -> None:
        self.status = "planned"
        self.plan_status = plan_status
        self.git_head = git_head
        self._seed_risk_register(checklist.get("risks", []))
        self.updated_at = _utc_now()
        self.entries.append(
            HandoffEntry(
                timestamp=self.updated_at,
                phase="plan",
                iteration=0,
                task=task,
                summary="Plan approved for controlled execution.",
                git_head=git_head,
                details={"plan_status": plan_status, "controls": checklist.get("controls", [])},
            )
        )

    def record_action(
        self,
        *,
        phase: str,
        summary: str,
        task: str = "",
        git_head: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.git_head = git_head or self.git_head
        self.updated_at = _utc_now()
        self.entries.append(
            HandoffEntry(
                timestamp=self.updated_at,
                phase=phase,
                iteration=max((entry.iteration for entry in self.entries), default=0),
                task=task or self.task,
                summary=summary[:500],
                git_head=git_head,
                details=dict(details or {}),
            )
        )

    def sync_implementation_backlog(self, items: list[dict[str, str]]) -> None:
        backlog: list[dict[str, str]] = []
        seen_active = False
        blocked_mode = self.status == "exception" or any(
            str(entry.get("status", "open")).strip().lower() != "closed" and str(entry.get("severity", "")).strip().lower() == "high"
            for entry in self.issue_register
        )
        for item in items:
            step_id = str(item.get("step_id", "")).strip()
            if not step_id:
                continue
            raw_status = str(item.get("status", "pending")).strip().lower()
            backlog_status = "planned"
            if raw_status in {"completed", "done"}:
                backlog_status = "done"
            elif raw_status == "failed":
                backlog_status = "blocked" if blocked_mode else "ready"
            elif raw_status == "in_progress":
                backlog_status = "in_progress"
                seen_active = True
            elif raw_status == "pending":
                backlog_status = "ready" if not seen_active else "planned"
            backlog.append(
                {
                    "step_id": step_id,
                    "title": str(item.get("title", "")).strip()[:160],
                    "status": backlog_status,
                    "validation": str(item.get("validation", "")).strip()[:240],
                }
            )
        self.implementation_backlog = backlog
        self.updated_at = _utc_now()

    def sync_prince2_roles(self, roles: dict[str, dict[str, Any]]) -> None:
        normalized: dict[str, dict[str, Any]] = {}
        for role, assignment in roles.items():
            if not isinstance(assignment, dict):
                continue
            provider = str(assignment.get("provider", "")).strip()
            provider_model = str(assignment.get("provider_model", "")).strip()
            if not role or not provider or not provider_model:
                continue
            params = assignment.get("params", {})
            normalized[str(role)] = {
                "role": str(role),
                "label": str(assignment.get("label", role)).strip() or str(role),
                "mode": str(assignment.get("mode", "manual")).strip() or "manual",
                "provider": provider,
                "provider_model": provider_model,
                "params": dict(params) if isinstance(params, dict) else {},
                "account": str(assignment["account"]) if assignment.get("account") else None,
                "source": str(assignment.get("source", "manual")).strip() or "manual",
            }
        self.prince2_roles = normalized
        self.updated_at = _utc_now()

    def sync_prince2_role_tree_baseline(self, baseline: dict[str, Any]) -> None:
        if not isinstance(baseline, dict):
            self.prince2_role_tree_baseline = {}
            self.prince2_node_runtime = {}
            self.updated_at = _utc_now()
            return
        self.prince2_role_tree_baseline = dict(baseline)
        self.prince2_node_runtime = self._materialize_prince2_node_runtime(dict(baseline))
        self.updated_at = _utc_now()

    def begin_step(
        self,
        *,
        iteration: int,
        task: str,
        step_id: str,
        step_title: str,
        step_status: str,
        git_head: str | None,
    ) -> None:
        self.status = "executing"
        self.current_step_id = step_id
        self.current_step_title = step_title
        self.current_step_status = step_status
        self.git_head = git_head
        self.updated_at = _utc_now()
        self.entries.append(
            HandoffEntry(
                timestamp=self.updated_at,
                phase="step_start",
                iteration=iteration,
                task=task,
                summary="Step handed off for execution.",
                step_id=step_id,
                step_title=step_title,
                step_status=step_status,
                git_head=git_head,
            )
        )

    def complete_step(
        self,
        *,
        iteration: int,
        task: str,
        step_id: str,
        step_title: str,
        step_status: str,
        model: str,
        action_type: str,
        observation: str,
        git_head: str | None,
    ) -> None:
        self.current_step_id = step_id
        self.current_step_title = step_title
        self.current_step_status = step_status
        self.latest_observation = observation
        self.git_head = git_head
        self.updated_at = _utc_now()
        self.entries.append(
            HandoffEntry(
                timestamp=self.updated_at,
                phase="step_result",
                iteration=iteration,
                task=task,
                summary="Step outcome recorded in handoff context.",
                step_id=step_id,
                step_title=step_title,
                step_status=step_status,
                model=model,
                action_type=action_type,
                git_head=git_head,
                details={"observation": observation[:1000]},
            )
        )

    def record_git_snapshot(
        self,
        *,
        iteration: int,
        task: str,
        message: str,
        git_head: str | None,
    ) -> None:
        self.git_head = git_head
        self.updated_at = _utc_now()
        self.entries.append(
            HandoffEntry(
                timestamp=self.updated_at,
                phase="git_snapshot",
                iteration=iteration,
                task=task,
                summary=message,
                git_head=git_head,
            )
        )

    def latest_git_snapshot(self) -> dict[str, str] | None:
        for entry in reversed(self.entries):
            if entry.phase != "git_snapshot":
                continue
            return {
                "summary": entry.summary,
                "git_head": entry.git_head or "unknown",
                "timestamp": entry.timestamp,
            }
        return None

    def close_run(self, *, task: str, success: bool, plan_status: str, git_head: str | None, outcome: str) -> None:
        self.status = "closed" if success else "exception"
        self.current_step_status = "completed" if success else "exception"
        self.plan_status = plan_status
        self.latest_observation = outcome
        self.git_head = git_head
        if not success:
            self._build_exception_plan()
        self.updated_at = _utc_now()
        self.entries.append(
            HandoffEntry(
                timestamp=self.updated_at,
                phase="finish",
                iteration=max((entry.iteration for entry in self.entries), default=0),
                task=task,
                summary=outcome,
                step_status=self.current_step_status,
                git_head=git_head,
                details={"plan_status": plan_status, "success": success},
            )
        )

    def summary(self, limit: int = 6) -> str:
        if not self.entries:
            return "No active handoff context."
        lines = [
            f"task={self.task or 'unknown'}",
            f"status={self.status}",
            f"plan_status={self.plan_status or 'unknown'}",
            f"current_step={self.current_step_id or 'none'}",
            f"git_head={self.git_head or 'unknown'}",
            f"project_brief_fields={len(self.project_brief)}",
            "registers="
            f"risks:{len(self.risk_register)} issues:{len(self.issue_register)} "
            f"quality:{len(self.quality_register)} lessons:{len(self.lessons_log)} "
            f"backlog:{len(self.implementation_backlog)}",
            f"prince2_roles={len(self.prince2_roles)}",
            f"prince2_role_tree_baseline={'approved' if self.prince2_role_tree_baseline else 'missing'}",
            f"prince2_node_runtime={self.prince2_node_runtime_summary().get('status', 'missing')}",
        ]
        for role, assignment in sorted(self.prince2_roles.items()):
            lines.append(
                f"role={role} provider={assignment.get('provider', 'unknown')} "
                f"provider_model={assignment.get('provider_model', 'unknown')} "
                f"account={assignment.get('account') or 'none'}"
            )
        for entry in self.entries[-limit:]:
            lines.append(
                f"[{entry.phase}] iter={entry.iteration} step={entry.step_id or '-'} "
                f"status={entry.step_status or '-'} model={entry.model or '-'}"
            )
        return "\n".join(lines)

    def detailed_summary(self, limit: int = 8) -> str:
        if not self.entries:
            return "No handoff log entries."
        lines = []
        for entry in self.entries[-limit:]:
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

    def stage_view(self) -> dict[str, object]:
        status_by_step = self._parse_plan_status(self.plan_status)
        closed_steps = [step_id for step_id, status in status_by_step.items() if status == "completed"]
        active_step = None
        if self.current_step_id and self.current_step_status in {"pending", "in_progress", "failed", "exception"}:
            active_step = {
                "id": self.current_step_id,
                "title": self.current_step_title,
                "status": self.current_step_status,
                "latest_observation": self.latest_observation,
            }
        git_boundary = {
            "baseline": self.git_head_baseline or "unknown",
            "current": self.git_head or "unknown",
        }
        pid_boundary = {
            "project_status": self.status or "unknown",
            "plan_status": self.plan_status or "unknown",
            "updated_at": self.updated_at,
        }
        boundary_decision = self._boundary_decision(status_by_step)
        register_statuses = self._register_status_summary()
        backlog_statuses = self._implementation_backlog_status_summary()
        recovery_state = self._recovery_state(status_by_step, backlog_statuses)
        stage_health = self._stage_health(boundary_decision, active_step, register_statuses, backlog_statuses)
        next_action = self._next_action(boundary_decision, active_step, stage_health, backlog_statuses, recovery_state)
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
            "node_runtime_summary": self.prince2_node_runtime_summary(),
        }

    def rendered_stage_view(self) -> str:
        view = self.stage_view()
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
        lines.append(
            f"- git_boundary: baseline={git_boundary['baseline']} current={git_boundary['current']}"
        )
        lines.append(
            f"- pid_boundary: project_status={pid_boundary['project_status']} "
            f"plan_status={pid_boundary['plan_status']} updated_at={pid_boundary['updated_at']}"
        )
        lines.append(f"- stage_health: {stage_health}")
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
            f"risks={len(self.risk_register)} issues={len(self.issue_register)} "
            f"quality={len(self.quality_register)} lessons={len(self.lessons_log)} "
            f"backlog={len(self.implementation_backlog)}"
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
        if self.prince2_roles:
            lines.append("- prince2_roles:")
            for role, assignment in sorted(self.prince2_roles.items()):
                params = assignment.get("params", {})
                params_text = ",".join(f"{key}={value}" for key, value in sorted(params.items())) if isinstance(params, dict) else ""
                lines.append(
                    f"  {role}: provider={assignment.get('provider', 'unknown')} "
                    f"provider_model={assignment.get('provider_model', 'unknown')} "
                    f"account={assignment.get('account') or 'none'}"
                    + (f" params={params_text}" if params_text else "")
                )
        if self.exception_plan:
            lines.append(f"- exception_plan: {' | '.join(self.exception_plan[:3])}")
        return "\n".join(lines)

    def rendered_register_status_summary(self) -> str:
        summary = self._register_status_summary()
        clean = (
            summary["risks_open"] == 0
            and summary["issues_open"] == 0
            and summary["quality_open"] == 0
            and not self.exception_plan
        )
        state = "clean" if clean else "residual"
        return (
            f"governance={state} "
            f"risks_open={summary['risks_open']} risks_closed={summary['risks_closed']} "
            f"issues_open={summary['issues_open']} issues_closed={summary['issues_closed']} "
            f"quality_open={summary['quality_open']} quality_accepted={summary['quality_accepted']} "
            f"exception_plan_items={len(self.exception_plan)}"
        )

    def rendered_stage_health(self) -> str:
        view = self.stage_view()
        return str(view["stage_health"])

    def rendered_next_action(self) -> str:
        view = self.stage_view()
        return str(view["next_action"])

    def rendered_operational_posture(self) -> str:
        view = self.stage_view()
        active_step = view["active_step"]
        backlog_statuses = view["backlog_statuses"]
        active_stage = "none"
        if isinstance(active_step, dict):
            active_stage = f"{active_step.get('id', 'unknown')} [{active_step.get('status', 'unknown')}]"
        git_boundary = view["git_boundary"]
        return "\n".join(
            [
                "Operational posture:",
                f"- governance: {self.rendered_register_status_summary()}",
                f"- stage_health: {view['stage_health']}",
                f"- recovery_state: {view['recovery_state']}",
                f"- next_action: {view['next_action']}",
                f"- active_stage: {active_stage}",
                f"- implementation_backlog_open: {backlog_statuses['ready'] + backlog_statuses['planned'] + backlog_statuses['in_progress'] + backlog_statuses['blocked']}",
                f"- implementation_backlog_blocked: {backlog_statuses['blocked']}",
                f"- git_boundary: baseline={git_boundary['baseline']} current={git_boundary['current']}",
                f"- boundary_decision: {view['boundary_decision']}",
            ]
        )

    def rendered_risks(self) -> str:
        lines = ["Risk register:"]
        if not self.risk_register:
            lines.append("- none")
            return "\n".join(lines)
        for item in self.risk_register:
            lines.append(f"- [{item.get('status', 'unknown')}] {item.get('risk', '')}")
        return "\n".join(lines)

    def rendered_issues(self) -> str:
        lines = ["Issue register:"]
        if not self.issue_register:
            lines.append("- none")
            return "\n".join(lines)
        for item in self.issue_register:
            lines.append(
                f"- [{item.get('severity', 'unknown')}] {item.get('step_id', '-')} :: {item.get('summary', '')}"
            )
        return "\n".join(lines)

    def rendered_quality(self) -> str:
        lines = ["Quality register:"]
        if not self.quality_register:
            lines.append("- none")
            return "\n".join(lines)
        for item in self.quality_register:
            lines.append(
                f"- [{item.get('status', 'unknown')}] {item.get('step_id', '-')} :: {item.get('evidence', '')}"
            )
        return "\n".join(lines)

    def rendered_exception_plan(self) -> str:
        lines = ["Exception plan:"]
        if not self.exception_plan:
            lines.append("- none")
            return "\n".join(lines)
        for item in self.exception_plan:
            lines.append(f"- {item}")
        return "\n".join(lines)

    def rendered_lessons(self) -> str:
        lines = ["Lessons log:"]
        if not self.lessons_log:
            lines.append("- none")
            return "\n".join(lines)
        for item in self.lessons_log:
            lines.append(
                f"- [{item.get('type', 'lesson')}] {item.get('step_id', '-')} :: {item.get('lesson', '')}"
            )
        return "\n".join(lines)

    def rendered_implementation_backlog(self) -> str:
        lines = ["Implementation backlog:"]
        if not self.implementation_backlog:
            lines.append("- none")
            return "\n".join(lines)
        for item in self.implementation_backlog:
            normalized_status = self._normalize_backlog_status(str(item.get("status", "")))
            lines.append(
                f"- [{normalized_status}] {item.get('step_id', '-')} :: "
                f"{item.get('title', '')} | validation={item.get('validation', '')}"
            )
        return "\n".join(lines)

    def rendered_project_brief(self) -> str:
        lines = ["Project brief:"]
        if not self.project_brief:
            lines.append("- none")
            return "\n".join(lines)
        for key in sorted(self.project_brief):
            lines.append(f"- {key}: {self.project_brief[key]}")
        return "\n".join(lines)

    def prince2_node_runtime_report(self) -> dict[str, Any]:
        if not self.prince2_node_runtime:
            return {
                "command": "roles runtime",
                "status": "missing",
                "message": "No materialized PRINCE2 node runtime. Approve a role-tree baseline first.",
                "summary": self.prince2_node_runtime_summary(),
                "runtime": {},
            }
        return {
            "command": "roles runtime",
            "status": "materialized",
            "summary": self.prince2_node_runtime_summary(),
            "runtime": dict(self.prince2_node_runtime),
        }

    def rendered_prince2_node_runtime(self) -> str:
        report = self.prince2_node_runtime_report()
        if report["status"] == "missing":
            return "PRINCE2 node runtime: missing\n- action: run /project start, /roles tree approve, or /project tree approve first."
        summary = report["summary"] if isinstance(report["summary"], dict) else {}
        runtime = report["runtime"] if isinstance(report["runtime"], dict) else {}
        nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
        lines = [
            "PRINCE2 node runtime:",
            f"- status: {summary.get('status', 'unknown')}",
            f"- nodes: {summary.get('nodes', 0)}",
            f"- ready: {summary.get('ready', 0)} waiting={summary.get('waiting', 0)} running={summary.get('running', 0)} blocked={summary.get('blocked', 0)}",
            f"- materialized_at: {runtime.get('materialized_at', 'unknown')}",
            f"- baseline_source: {runtime.get('baseline_source', 'unknown')}",
            f"- wait_triggers: {summary.get('wait_triggers', 0)} message_queues={summary.get('message_queues', 0)}",
        ]
        for node in nodes:
            lines.append(
                f"- {node.get('label', node.get('node_id', 'node'))} [{node.get('node_id', 'unknown')}]: "
                f"state={node.get('state', 'unknown')} "
                f"inbox={node.get('inbox_count', 0)} outbox={node.get('outbox_count', 0)} "
                f"wait={node.get('wait_status', 'none')} "
                f"provider={((node.get('assignment') or {}).get('provider') if isinstance(node.get('assignment'), dict) else None) or 'none'} "
                f"provider_model={((node.get('assignment') or {}).get('provider_model') if isinstance(node.get('assignment'), dict) else None) or 'none'}"
            )
        return "\n".join(lines)

    def prince2_node_messages_report(self, node_id: str | None = None) -> dict[str, Any]:
        runtime = self.prince2_node_runtime if isinstance(self.prince2_node_runtime, dict) else {}
        nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
        if not runtime or not nodes:
            return {
                "command": "roles messages",
                "status": "missing",
                "message": "No materialized PRINCE2 node runtime. Approve a role-tree baseline first.",
                "nodes": [],
            }
        selected: list[dict[str, Any]] = []
        for node in nodes:
            if node_id and str(node.get("node_id", "")).strip() != node_id:
                continue
            selected.append(
                {
                    "node_id": str(node.get("node_id", "")),
                    "label": str(node.get("label", node.get("node_id", ""))),
                    "state": str(node.get("state", "unknown")),
                    "wait_status": str(node.get("wait_status", "none")),
                    "inbox": [dict(item) for item in node.get("inbox", []) if isinstance(item, dict)],
                    "outbox": [dict(item) for item in node.get("outbox", []) if isinstance(item, dict)],
                }
            )
        return {
            "command": "roles messages",
            "status": "ok",
            "node_filter": node_id,
            "count": len(selected),
            "nodes": selected,
        }

    def rendered_prince2_node_messages(self, node_id: str | None = None) -> str:
        report = self.prince2_node_messages_report(node_id=node_id)
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
                f"- {node.get('label')} [{node.get('node_id')}]: state={node.get('state')} wait={node.get('wait_status')} "
                f"inbox={len(node.get('inbox', []))} outbox={len(node.get('outbox', []))}"
            )
            for item in node.get("inbox", []):
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"  inbox {item.get('message_id')} {item.get('source_node')} -> {item.get('target_node')} "
                    f"edge={item.get('edge_id')} payload={','.join(item.get('payload_scope', []))}"
                )
            for item in node.get("outbox", []):
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"  outbox {item.get('message_id')} {item.get('source_node')} -> {item.get('target_node')} "
                    f"edge={item.get('edge_id')} payload={','.join(item.get('payload_scope', []))}"
                )
        return "\n".join(lines)

    def send_prince2_node_message(
        self,
        *,
        source_node: str,
        target_node: str,
        edge_id: str,
        payload_scope: list[str],
        evidence_refs: list[str] | None = None,
        summary: str | None = None,
    ) -> dict[str, Any]:
        runtime = self.prince2_node_runtime if isinstance(self.prince2_node_runtime, dict) else {}
        baseline = self.prince2_role_tree_baseline if isinstance(self.prince2_role_tree_baseline, dict) else {}
        flow = baseline.get("flow", {}) if isinstance(baseline.get("flow"), dict) else {}
        edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
        if not runtime:
            raise ValueError("No materialized PRINCE2 node runtime. Approve a role-tree baseline first.")
        nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
        source = next((node for node in nodes if str(node.get("node_id", "")).strip() == source_node), None)
        target = next((node for node in nodes if str(node.get("node_id", "")).strip() == target_node), None)
        if source is None:
            raise ValueError(f"Source node '{source_node}' not found in PRINCE2 node runtime.")
        if target is None:
            raise ValueError(f"Target node '{target_node}' not found in PRINCE2 node runtime.")
        edge = next(
            (
                item
                for item in edges
                if str(item.get("edge_id", "")).strip() == edge_id
                and str(item.get("source_node", "")).strip() == source_node
                and str(item.get("target_node", "")).strip() == target_node
            ),
            None,
        )
        if edge is None:
            raise ValueError(
                f"Unauthorized PRINCE2 flow edge '{edge_id}' for {source_node} -> {target_node}."
            )
        clean_payload = [str(item).strip() for item in payload_scope if str(item).strip()]
        if not clean_payload:
            raise ValueError("Message payload scope cannot be empty.")
        allowed_payload = {str(item).strip() for item in edge.get("payload_scope", []) if str(item).strip()}
        invalid_payload = [item for item in clean_payload if item not in allowed_payload]
        if invalid_payload:
            raise ValueError(
                "Payload scope exceeds authorized PRINCE2 flow edge: " + ", ".join(invalid_payload)
            )
        evidence = [str(item).strip() for item in (evidence_refs or []) if str(item).strip()]
        message_id = f"msg-{len(self.entries) + len(clean_payload) + len(evidence) + 1}-{_utc_now().replace(':', '').replace('-', '')}"
        message = {
            "message_id": message_id,
            "timestamp": _utc_now(),
            "source_node": source_node,
            "target_node": target_node,
            "edge_id": edge_id,
            "flow_type": str(edge.get("flow_type", "")),
            "payload_scope": clean_payload,
            "expected_evidence": [str(item) for item in edge.get("expected_evidence", []) if str(item).strip()],
            "evidence_refs": evidence,
            "validation_condition": str(edge.get("validation_condition", "")),
            "decision_authority": str(edge.get("decision_authority", "")),
            "return_path": str(edge.get("return_path", "")),
            "status": "queued",
            "summary": (summary or f"{edge_id} message").strip()[:240],
        }
        source.setdefault("outbox", [])
        target.setdefault("inbox", [])
        if not isinstance(source["outbox"], list):
            source["outbox"] = []
        if not isinstance(target["inbox"], list):
            target["inbox"] = []
        source["outbox"].append(dict(message))
        target["inbox"].append(dict(message))
        source["outbox_count"] = len(source["outbox"])
        target["inbox_count"] = len(target["inbox"])
        source["last_transition_at"] = message["timestamp"]
        target["last_transition_at"] = message["timestamp"]
        if str(target.get("state", "idle")).strip().lower() in {"idle", "waiting"}:
            target["state"] = "ready"
        if str(target.get("wait_status", "none")).strip().lower() != "none":
            target["wait_status"] = "message_received"
        self.prince2_node_runtime["nodes"] = nodes
        self.updated_at = _utc_now()
        return message

    def set_prince2_node_waiting(
        self,
        *,
        node_id: str,
        reason: str,
        wake_triggers: list[str] | None = None,
    ) -> dict[str, Any]:
        node = self._prince2_runtime_node(node_id)
        clean_reason = str(reason).strip()
        if not clean_reason:
            raise ValueError("Wait reason cannot be empty.")
        node["state"] = "waiting"
        node["wait_status"] = "waiting_for_trigger"
        node["wait_reason"] = clean_reason[:240]
        if wake_triggers is not None:
            node["wake_triggers"] = [str(item).strip() for item in wake_triggers if str(item).strip()]
        node["last_transition_at"] = _utc_now()
        self.updated_at = _utc_now()
        return dict(node)

    def wake_prince2_node(
        self,
        *,
        node_id: str,
        trigger: str,
    ) -> dict[str, Any]:
        node = self._prince2_runtime_node(node_id)
        clean_trigger = str(trigger).strip()
        if not clean_trigger:
            raise ValueError("Wake trigger cannot be empty.")
        allowed = [str(item).strip() for item in node.get("wake_triggers", []) if str(item).strip()]
        inbox = [dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]
        trigger_allowed = clean_trigger in allowed
        message_allowed = clean_trigger == "message_received" and bool(inbox)
        if not trigger_allowed and not message_allowed:
            raise ValueError(
                f"Wake trigger '{clean_trigger}' is not authorized for node '{node_id}'."
            )
        node["state"] = "ready"
        node["wait_status"] = "none"
        node["wait_reason"] = None
        node["last_transition_at"] = _utc_now()
        self.updated_at = _utc_now()
        return dict(node)

    def tick_prince2_node(self, *, node_id: str) -> dict[str, Any]:
        node = self._prince2_runtime_node(node_id)
        state = str(node.get("state", "idle")).strip().lower()
        if state == "waiting":
            raise ValueError(f"Node '{node_id}' is waiting and cannot tick until woken.")
        inbox = [dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]
        now = _utc_now()
        if inbox:
            message = inbox.pop(0)
            message["status"] = "consumed"
            message["consumed_at"] = now
            node["inbox"] = inbox
            node["inbox_count"] = len(inbox)
            node.setdefault("transcript_refs", [])
            if not isinstance(node["transcript_refs"], list):
                node["transcript_refs"] = []
            node["transcript_refs"].append(f"message:{message.get('message_id', 'unknown')}")
            node["state"] = "running"
            node["wait_status"] = "none"
            node["wait_reason"] = None
            node["last_transition_at"] = now
            self.updated_at = now
            return {
                "node_id": node_id,
                "state": "running",
                "consumed_message": dict(message),
                "remaining_inbox": len(inbox),
            }
        if state in {"ready", "running"}:
            node["state"] = "completed"
            node["wait_status"] = "none"
            node["wait_reason"] = None
            node["last_transition_at"] = now
            self.updated_at = now
            return {
                "node_id": node_id,
                "state": "completed",
                "consumed_message": None,
                "remaining_inbox": 0,
            }
        if state == "completed":
            return {
                "node_id": node_id,
                "state": "completed",
                "consumed_message": None,
                "remaining_inbox": len(inbox),
            }
        raise ValueError(f"Node '{node_id}' is not ready to tick from state '{state}'.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "_format": "stagewarden_project_handoff",
            "_version": 1,
            "task": self.task,
            "project_brief": dict(self.project_brief),
            "status": self.status,
            "current_step_id": self.current_step_id,
            "current_step_title": self.current_step_title,
            "current_step_status": self.current_step_status,
            "latest_observation": self.latest_observation,
            "plan_status": self.plan_status,
            "git_head": self.git_head,
            "git_head_baseline": self.git_head_baseline,
            "risk_register": list(self.risk_register),
            "issue_register": list(self.issue_register),
            "quality_register": list(self.quality_register),
            "lessons_log": list(self.lessons_log),
            "exception_plan": list(self.exception_plan),
            "implementation_backlog": list(self.implementation_backlog),
            "prince2_roles": {role: dict(assignment) for role, assignment in self.prince2_roles.items()},
            "prince2_role_tree_baseline": dict(self.prince2_role_tree_baseline),
            "prince2_node_runtime": dict(self.prince2_node_runtime),
            "updated_at": self.updated_at,
            "entries": [entry.as_dict() for entry in self.entries],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_utf8(path, dumps_ascii(self.as_dict(), indent=2))

    def record_issue(self, *, step_id: str, severity: str, summary: str) -> None:
        self.issue_register.append(
            {
                "step_id": step_id,
                "severity": severity,
                "summary": summary[:240],
                "status": "open",
                "recorded_at": _utc_now(),
            }
        )

    def record_quality(self, *, step_id: str, status: str, evidence: str) -> None:
        self.quality_register.append(
            {"step_id": step_id, "status": status, "evidence": evidence[:240], "recorded_at": _utc_now()}
        )

    def record_lesson(self, *, step_id: str, lesson_type: str, lesson: str) -> None:
        self.lessons_log.append(
            {"step_id": step_id, "type": lesson_type, "lesson": lesson[:240], "recorded_at": _utc_now()}
        )

    def update_project_brief(self, updates: dict[str, str]) -> None:
        for key, value in updates.items():
            clean_key = str(key).strip().lower()
            clean_value = str(value).strip()
            if not clean_key:
                continue
            if clean_value:
                self.project_brief[clean_key] = clean_value[:1000]
            elif clean_key in self.project_brief:
                del self.project_brief[clean_key]
        self.updated_at = _utc_now()

    def clear_project_brief(self, field_name: str | None = None) -> None:
        if field_name is None:
            self.project_brief = {}
        else:
            self.project_brief.pop(field_name.strip().lower(), None)
        self.updated_at = _utc_now()

    def close_issues_for_step(self, *, step_id: str, resolution: str) -> None:
        for item in self.issue_register:
            if str(item.get("step_id", "")).strip() != step_id:
                continue
            if str(item.get("status", "open")).strip().lower() == "closed":
                continue
            item["status"] = "closed"
            item["resolved_at"] = _utc_now()
            item["resolution"] = resolution[:240]

    def close_all_open_issues(self, *, resolution: str) -> None:
        for item in self.issue_register:
            if str(item.get("status", "open")).strip().lower() == "closed":
                continue
            item["status"] = "closed"
            item["resolved_at"] = _utc_now()
            item["resolution"] = resolution[:240]

    def close_all_open_risks(self, *, resolution: str) -> None:
        for item in self.risk_register:
            if str(item.get("status", "open")).strip().lower() == "closed":
                continue
            item["status"] = "closed"
            item["resolved_at"] = _utc_now()
            item["resolution"] = resolution[:240]

    def finalize_quality_register(self, *, resolution: str) -> None:
        for item in self.quality_register:
            status = str(item.get("status", "")).strip().lower()
            if status in {"accepted", "closed"}:
                continue
            item["status"] = "accepted"
            item["accepted_at"] = _utc_now()
            item["resolution"] = resolution[:240]

    def clear_exception_plan_if_recovered(self) -> None:
        if not self.exception_plan:
            return
        open_issues = [
            item
            for item in self.issue_register
            if str(item.get("status", "open")).strip().lower() != "closed"
        ]
        if not open_issues:
            self.exception_plan = []

    def _seed_risk_register(self, risks: list[Any]) -> None:
        if self.risk_register:
            return
        for item in risks:
            text = str(item).strip()
            if not text:
                continue
            self.risk_register.append(
                {"risk": text[:240], "status": "open", "recorded_at": _utc_now()}
            )

    def _build_exception_plan(self) -> None:
        if self.exception_plan:
            return
        current_step = self.current_step_id or "unknown-step"
        self.exception_plan = [
            f"review boundary for {current_step}",
            "inspect latest issue register and failed observations",
            "prepare controlled corrective action with wet-run validation",
        ]

    def _register_status_summary(self) -> dict[str, int]:
        risks_open = sum(1 for item in self.risk_register if str(item.get("status", "open")).strip().lower() != "closed")
        risks_closed = len(self.risk_register) - risks_open
        issues_open = sum(1 for item in self.issue_register if str(item.get("status", "open")).strip().lower() != "closed")
        issues_closed = len(self.issue_register) - issues_open
        quality_accepted = sum(
            1 for item in self.quality_register if str(item.get("status", "")).strip().lower() in {"accepted", "closed"}
        )
        quality_open = len(self.quality_register) - quality_accepted
        return {
            "risks_open": risks_open,
            "risks_closed": risks_closed,
            "issues_open": issues_open,
            "issues_closed": issues_closed,
            "quality_open": quality_open,
            "quality_accepted": quality_accepted,
        }

    def _stage_health(
        self,
        boundary_decision: str,
        active_step: dict[str, object] | None,
        register_statuses: dict[str, int],
        backlog_statuses: dict[str, int],
    ) -> str:
        if self.status == "exception" or boundary_decision.startswith("review_boundary:exception"):
            return "exception"
        if backlog_statuses["blocked"] > 0:
            return "blocked"
        if register_statuses["issues_open"] > 0 or self.exception_plan:
            return "at_risk"
        if active_step:
            return "active"
        if boundary_decision == "close_project":
            return "ready_to_close"
        return "stable"

    def _next_action(
        self,
        boundary_decision: str,
        active_step: dict[str, object] | None,
        stage_health: str,
        backlog_statuses: dict[str, int],
        recovery_state: str,
    ) -> str:
        if recovery_state == "recovery_active":
            return "execute recovery lane and confirm wet-run before re-baseline"
        if recovery_state == "recovery_cleared":
            return "clear exception controls and resume planned stages"
        if stage_health == "exception":
            return "execute exception plan and re-baseline the current stage"
        if stage_health == "blocked":
            return "resolve blocking issues and promote the next ready stage"
        if boundary_decision == "review_boundary:open_issues":
            return "close remaining open issues before project closure"
        if boundary_decision == "close_project":
            return "authorize project closure"
        if active_step:
            return f"continue {active_step.get('id', 'current-step')}"
        if backlog_statuses["ready"] > 0:
            next_ready = next(
                (item.get("step_id", "next-step") for item in self.implementation_backlog if str(item.get("status", "")).strip().lower() == "ready"),
                "next-step",
            )
            return f"start {next_ready}"
        if stage_health == "stable":
            return "review current handoff and confirm next stage"
        return "review boundary and decide next controlled action"

    def _parse_plan_status(self, value: str) -> dict[str, str]:
        statuses: dict[str, str] = {}
        for item in (value or "").split(","):
            key, separator, status = item.partition(":")
            if not separator:
                continue
            clean_key = key.strip()
            clean_status = status.strip()
            if clean_key and clean_status:
                statuses[clean_key] = clean_status
        return statuses

    def _boundary_decision(self, status_by_step: dict[str, str]) -> str:
        if not status_by_step:
            return "review_boundary:no_plan_status"
        open_issues = [
            item
            for item in self.issue_register
            if str(item.get("status", "open")).strip().lower() != "closed"
        ]
        if self.status == "exception" and self.exception_plan:
            return "review_boundary:exception_plan"
        values = list(status_by_step.values())
        if any(status in {"failed", "exception"} for status in values):
            return "review_boundary:exception_path"
        if all(status == "completed" for status in values):
            if open_issues:
                return "review_boundary:open_issues"
            return "close_project"
        if any(status in {"pending", "planned", "ready", "in_progress"} for status in values):
            return "continue_current_stage"
        return "review_boundary:manual_check"

    def _recovery_state(self, status_by_step: dict[str, str], backlog_statuses: dict[str, int]) -> str:
        recovery_statuses = {
            step_id: status
            for step_id, status in status_by_step.items()
            if step_id.startswith("recovery-step-")
        }
        if recovery_statuses:
            values = list(recovery_statuses.values())
            if any(status in {"ready", "in_progress", "planned", "pending"} for status in values):
                return "recovery_active"
            if all(status == "completed" for status in values):
                return "recovery_cleared"
        if self.status == "exception" and self.exception_plan:
            return "exception_active"
        if backlog_statuses["blocked"] > 0:
            return "exception_active"
        return "none"

    def _implementation_backlog_status_summary(self) -> dict[str, int]:
        counts = {"ready": 0, "planned": 0, "in_progress": 0, "blocked": 0, "done": 0}
        for item in self.implementation_backlog:
            status = self._normalize_backlog_status(str(item.get("status", "")))
            if status in counts:
                counts[status] += 1
        return counts

    def _normalize_backlog_status(self, raw: str) -> str:
        status = raw.strip().lower()
        if status in {"completed", "done", "closed", "accepted"}:
            return "done"
        if status in {"failed", "blocked"}:
            return "blocked"
        if status in {"in_progress", "active", "executing"}:
            return "in_progress"
        if status in {"ready", "pending"}:
            return "ready"
        if status in {"planned", "queued"}:
            return "planned"
        if status in {"exception"}:
            return "blocked"
        return status or "planned"

    def prince2_node_runtime_summary(self) -> dict[str, int | str]:
        runtime = self.prince2_node_runtime if isinstance(self.prince2_node_runtime, dict) else {}
        nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
        counts = {
            "command": "roles runtime",
            "status": "missing" if not runtime else str(runtime.get("status", "materialized")),
            "nodes": len(nodes),
            "ready": 0,
            "waiting": 0,
            "running": 0,
            "blocked": 0,
            "escalated": 0,
            "idle": 0,
            "completed": 0,
            "message_queues": 0,
            "wait_triggers": 0,
        }
        for node in nodes:
            state = str(node.get("state", "idle")).strip().lower() or "idle"
            if state in counts:
                counts[state] += 1
            wait_status = str(node.get("wait_status", "none")).strip().lower()
            if wait_status not in {"", "none"}:
                counts["waiting"] += 0 if state == "waiting" else 1
            counts["message_queues"] += int(node.get("inbox_count", 0) or 0) + int(node.get("outbox_count", 0) or 0)
            counts["wait_triggers"] += len(node.get("wake_triggers", [])) if isinstance(node.get("wake_triggers"), list) else 0
        return counts

    def _prince2_runtime_node(self, node_id: str) -> dict[str, Any]:
        runtime = self.prince2_node_runtime if isinstance(self.prince2_node_runtime, dict) else {}
        if not runtime:
            raise ValueError("No materialized PRINCE2 node runtime. Approve a role-tree baseline first.")
        nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
        node = next((item for item in nodes if str(item.get("node_id", "")).strip() == node_id), None)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found in PRINCE2 node runtime.")
        self.prince2_node_runtime["nodes"] = nodes
        return node

    def _materialize_prince2_node_runtime(self, baseline: dict[str, Any]) -> dict[str, Any]:
        tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
        flow = baseline.get("flow", {}) if isinstance(baseline.get("flow"), dict) else {}
        nodes = [node for node in tree.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
        existing_runtime = self.prince2_node_runtime if isinstance(self.prince2_node_runtime, dict) else {}
        existing_nodes = {
            str(node.get("node_id")): node
            for node in existing_runtime.get("nodes", [])
            if isinstance(node, dict) and node.get("node_id")
        }
        materialized_nodes: list[dict[str, Any]] = []
        materialized_at = _utc_now()
        for node in nodes:
            node_id = str(node.get("node_id", "")).strip()
            if not node_id:
                continue
            previous = existing_nodes.get(node_id, {})
            assignment = dict(node.get("assignment", {})) if isinstance(node.get("assignment"), dict) else {}
            wake_triggers = previous.get("wake_triggers")
            if not isinstance(wake_triggers, list) or not wake_triggers:
                wake_triggers = list((node.get("context_rule") or {}).get("expansion_events", [])) if isinstance(node.get("context_rule"), dict) else []
            context_rule = dict(node.get("context_rule", {})) if isinstance(node.get("context_rule"), dict) else {}
            inbox = [dict(item) for item in previous.get("inbox", []) if isinstance(item, dict)] if isinstance(previous.get("inbox", []), list) else []
            outbox = [dict(item) for item in previous.get("outbox", []) if isinstance(item, dict)] if isinstance(previous.get("outbox", []), list) else []
            transcript_refs = [str(item) for item in previous.get("transcript_refs", [])] if isinstance(previous.get("transcript_refs", []), list) else []
            default_state = "ready" if assignment else "idle"
            wait_status = str(previous.get("wait_status", "none")).strip().lower() or "none"
            wait_reason = str(previous.get("wait_reason", "")).strip() or None
            materialized_nodes.append(
                {
                    "node_id": node_id,
                    "role_type": str(node.get("role_type", "")),
                    "label": str(node.get("label", node_id)),
                    "parent_id": str(node.get("parent_id")) if node.get("parent_id") not in {None, ""} else None,
                    "level": str(node.get("level", "")),
                    "state": str(previous.get("state", default_state)).strip().lower() or default_state,
                    "runtime_status": "active_actor",
                    "wait_status": wait_status,
                    "wait_reason": wait_reason,
                    "wake_triggers": wake_triggers,
                    "context_rule": context_rule,
                    "accountability_boundary": str(node.get("accountability_boundary", "")),
                    "delegated_authority": str(node.get("delegated_authority", "")),
                    "context_scope": str(node.get("context_scope", "")),
                    "responsibility_domain": str(node.get("responsibility_domain", "")),
                    "assignment": assignment,
                    "incoming_edges": [
                        str(edge.get("edge_id", ""))
                        for edge in edges
                        if str(edge.get("target_node", "")).strip() == node_id and str(edge.get("edge_id", "")).strip()
                    ],
                    "outgoing_edges": [
                        str(edge.get("edge_id", ""))
                        for edge in edges
                        if str(edge.get("source_node", "")).strip() == node_id and str(edge.get("edge_id", "")).strip()
                    ],
                    "inbox": inbox,
                    "outbox": outbox,
                    "inbox_count": len(inbox),
                    "outbox_count": len(outbox),
                    "transcript_refs": transcript_refs,
                    "last_transition_at": str(previous.get("last_transition_at", materialized_at)),
                }
            )
        return {
            "command": "roles runtime",
            "status": "materialized" if materialized_nodes else "missing",
            "rule": "approved PRINCE2 role-tree nodes are materialized as active runtime actors with scoped context, local wait state, and governed message queues",
            "materialized_at": materialized_at,
            "baseline_source": str(baseline.get("source", "unknown")),
            "baseline_status": str(baseline.get("status", "unknown")),
            "nodes": materialized_nodes,
        }

    @classmethod
    def load(cls, path: Path) -> "ProjectHandoff":
        if not path.exists():
            return cls()
        payload = loads_text(read_text_utf8(path))
        context = cls(
            task=str(payload.get("task", "")),
            project_brief={
                str(key).strip().lower(): str(value).strip()
                for key, value in payload.get("project_brief", {}).items()
                if str(key).strip() and value is not None
            }
            if isinstance(payload.get("project_brief", {}), dict)
            else {},
            status=str(payload.get("status", "idle")),
            current_step_id=str(payload["current_step_id"]) if payload.get("current_step_id") else None,
            current_step_title=str(payload["current_step_title"]) if payload.get("current_step_title") else None,
            current_step_status=str(payload["current_step_status"]) if payload.get("current_step_status") else None,
            latest_observation=str(payload.get("latest_observation", "")),
            plan_status=str(payload.get("plan_status", "")),
            git_head=str(payload["git_head"]) if payload.get("git_head") else None,
            git_head_baseline=str(payload["git_head_baseline"]) if payload.get("git_head_baseline") else None,
            risk_register=[dict(item) for item in payload.get("risk_register", []) if isinstance(item, dict)],
            issue_register=[dict(item) for item in payload.get("issue_register", []) if isinstance(item, dict)],
            quality_register=[dict(item) for item in payload.get("quality_register", []) if isinstance(item, dict)],
            lessons_log=[dict(item) for item in payload.get("lessons_log", []) if isinstance(item, dict)],
            exception_plan=[str(item) for item in payload.get("exception_plan", [])],
            implementation_backlog=[dict(item) for item in payload.get("implementation_backlog", []) if isinstance(item, dict)],
            prince2_roles={
                str(key): dict(value)
                for key, value in payload.get("prince2_roles", {}).items()
                if isinstance(value, dict)
            },
            prince2_role_tree_baseline=dict(payload.get("prince2_role_tree_baseline", {}))
            if isinstance(payload.get("prince2_role_tree_baseline", {}), dict)
            else {},
            prince2_node_runtime=dict(payload.get("prince2_node_runtime", {}))
            if isinstance(payload.get("prince2_node_runtime", {}), dict)
            else {},
            updated_at=str(payload.get("updated_at", _utc_now())),
        )
        for item in payload.get("entries", []):
            context.entries.append(
                HandoffEntry(
                    timestamp=str(item.get("timestamp", _utc_now())),
                    phase=str(item.get("phase", "")),
                    iteration=int(item.get("iteration", 0)),
                    task=str(item.get("task", context.task)),
                    summary=str(item.get("summary", "")),
                    step_id=str(item["step_id"]) if item.get("step_id") else None,
                    step_title=str(item["step_title"]) if item.get("step_title") else None,
                    step_status=str(item["step_status"]) if item.get("step_status") else None,
                    model=str(item["model"]) if item.get("model") else None,
                    action_type=str(item["action_type"]) if item.get("action_type") else None,
                    git_head=str(item["git_head"]) if item.get("git_head") else None,
                    details=dict(item.get("details", {})),
                )
            )
        return context
