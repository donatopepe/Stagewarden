from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .prince2 import PRINCE2_THEME_NAMES, Prince2AgentPolicy, Prince2ToleranceProfile
from .role_tree import prince2_node_description, prince2_status_color
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
    goal: dict[str, Any] = field(default_factory=dict)
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

    def goal_view(self) -> dict[str, Any]:
        if not isinstance(self.goal, dict) or not self.goal:
            return {
                "status": "missing",
                "goal_id": None,
                "objective": "",
                "token_budget": None,
                "tokens_used": 0,
                "token_budget_remaining": None,
                "budget_used_percentage": None,
                "time_used_seconds": 0,
                "created_at": None,
                "updated_at": None,
                "terminal": False,
                "next_action": "Set a project goal with `goal set <objective> [--tokens N]`.",
            }
        status = str(self.goal.get("status", "active")).strip().lower() or "active"
        token_budget = self.goal.get("token_budget")
        tokens_used = int(self.goal.get("tokens_used", 0) or 0)
        remaining = None
        used_percentage = None
        if isinstance(token_budget, int) and token_budget > 0:
            remaining = max(token_budget - tokens_used, 0)
            used_percentage = round((tokens_used / token_budget) * 100, 2)
        next_action = "Continue controlled execution."
        if status == "paused":
            next_action = "Resume with `goal status active` or clear with `goal clear`."
        elif status == "budget_limited":
            next_action = "Review scope, raise budget with `goal set <objective> --tokens N`, pause, or mark complete."
        elif status == "complete":
            next_action = "Goal complete; start a new goal if more work is needed."
        return {
            "status": status,
            "goal_id": self.goal.get("goal_id"),
            "objective": str(self.goal.get("objective", "")),
            "token_budget": token_budget,
            "tokens_used": tokens_used,
            "token_budget_remaining": remaining,
            "budget_used_percentage": used_percentage,
            "time_used_seconds": int(self.goal.get("time_used_seconds", 0) or 0),
            "created_at": self.goal.get("created_at"),
            "updated_at": self.goal.get("updated_at"),
            "terminal": status in {"budget_limited", "complete"},
            "next_action": next_action,
        }

    def set_goal(self, *, objective: str, token_budget: int | None = None) -> dict[str, Any]:
        clean_objective = " ".join(str(objective).split()).strip()
        if not clean_objective:
            raise ValueError("Goal objective cannot be empty.")
        if token_budget is not None and token_budget <= 0:
            raise ValueError("Goal token budget must be a positive integer.")
        now = _utc_now()
        previous = self.goal_view()
        goal_id = str(previous.get("goal_id") or f"goal-{now.replace(':', '').replace('+', 'Z')}")
        self.goal = {
            "goal_id": goal_id,
            "objective": clean_objective[:1000],
            "status": "active",
            "token_budget": token_budget,
            "tokens_used": int(previous.get("tokens_used", 0) or 0),
            "time_used_seconds": int(previous.get("time_used_seconds", 0) or 0),
            "created_at": previous.get("created_at") or now,
            "updated_at": now,
        }
        self.updated_at = now
        self.record_action(
            phase="goal_set",
            summary=f"Goal set: {clean_objective[:160]}",
            task=self.task,
            details={"goal": self.goal_view()},
        )
        return self.goal_view()

    def update_goal_status(self, status: str) -> dict[str, Any]:
        clean_status = str(status).strip().lower()
        if clean_status not in {"active", "paused", "budget_limited", "complete"}:
            raise ValueError("Goal status must be one of: active, paused, budget_limited, complete.")
        if not self.goal:
            raise ValueError("No goal is set.")
        self.goal["status"] = clean_status
        self.goal["updated_at"] = _utc_now()
        self.updated_at = str(self.goal["updated_at"])
        self.record_action(
            phase="goal_status",
            summary=f"Goal status changed to {clean_status}.",
            task=self.task,
            details={"goal": self.goal_view()},
        )
        return self.goal_view()

    def record_goal_token_usage(
        self,
        *,
        model: str,
        step_id: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        current_usage: int | None = None,
    ) -> dict[str, Any]:
        if not self.goal:
            return self.goal_view()
        input_count = int(input_tokens or 0)
        output_count = int(output_tokens or 0)
        total = input_count + output_count
        if total <= 0:
            total = int(current_usage or 0)
        if total <= 0:
            return self.goal_view()
        previous = self.goal_view()
        self.goal["tokens_used"] = int(previous.get("tokens_used", 0) or 0) + total
        self.goal["updated_at"] = _utc_now()
        budget = self.goal.get("token_budget")
        if isinstance(budget, int) and budget > 0 and int(self.goal["tokens_used"]) >= budget:
            self.goal["status"] = "budget_limited"
        self.updated_at = str(self.goal["updated_at"])
        self.record_action(
            phase="goal_usage",
            summary=f"Goal token usage recorded: +{total} tokens via {model}.",
            task=self.task,
            details={
                "model": model,
                "step_id": step_id,
                "input_tokens": input_count or None,
                "output_tokens": output_count or None,
                "current_usage": current_usage,
                "tokens_added": total,
                "goal": self.goal_view(),
            },
        )
        return self.goal_view()

    def clear_goal(self) -> dict[str, Any]:
        previous = self.goal_view()
        self.goal = {}
        self.updated_at = _utc_now()
        self.record_action(
            phase="goal_clear",
            summary="Goal cleared.",
            task=self.task,
            details={"previous_goal": previous},
        )
        return previous

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
            f"goal={self.goal_view()['status']}:{self.goal_view()['objective'] or 'none'}",
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
        if self.current_step_id and self.current_step_status in {"pending", "in_progress", "failed", "exception", "waiting"}:
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
            "session_state": "suspended" if self.status == "waiting" else self.status,
            "session_recoverable": self.status == "waiting",
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
        lines.append(
            f"- git_boundary: baseline={git_boundary['baseline']} current={git_boundary['current']}"
        )
        lines.append(
            f"- pid_boundary: project_status={pid_boundary['project_status']} "
            f"plan_status={pid_boundary['plan_status']} updated_at={pid_boundary['updated_at']}"
        )
        lines.append(f"- stage_health: {stage_health}")
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
                lines.append(
                    "  decision_kpis="
                    + ", ".join(f"{key}={decision_kpis.get(key, 0)}" for key in sorted(decision_kpis))
                )
            lines.append(
                f"  thread_tokens total={node.get('thread_token_count', 0)} "
                f"business_case={node.get('business_case_token_count', 0)} child_count={node.get('child_count', 0)}"
            )
            kpi_tokens = node.get("kpi_token_counts", {}) if isinstance(node.get("kpi_token_counts", {}), dict) else {}
            if isinstance(kpi_tokens, dict) and kpi_tokens:
                lines.append(
                    "  kpi_tokens="
                    + ", ".join(f"{theme}:{kpi_tokens.get(theme, 0)}" for theme in PRINCE2_THEME_NAMES)
                )
            lines.append(f"  switch_hint=role switch {node.get('node_id', 'unknown')}")
        return "\n".join(lines)

    def prince2_node_active_report(self) -> dict[str, Any]:
        runtime = self.prince2_node_runtime if isinstance(self.prince2_node_runtime, dict) else {}
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
            state = self._node_tolerance_state(node)
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

    def rendered_prince2_node_active(self) -> str:
        report = self.prince2_node_active_report()
        if report["status"] == "missing":
            return "PRINCE2 active nodes: missing\n- action: run /project start, /roles tree approve, or /project tree approve first."
        lines = ["PRINCE2 active nodes:"]
        nodes = [node for node in report.get("nodes", []) if isinstance(node, dict)]
        if not nodes:
            lines.append("- none")
            return "\n".join(lines)
        for node in nodes:
            status_color = prince2_status_color(node, runtime_state=str(node.get("state", "")))
            lines.append(
                f"- {node.get('label')} [{node.get('node_id')}]: state={node.get('state')} "
                f"color={status_color} "
                f"owner={node.get('accountable_owner', 'user')} "
                f"margin={node.get('tolerance_margin_percent', 'unknown')} "
                f"pressure={node.get('tolerance_pressure_percent', 'unknown')} "
                f"tolerance_state={node.get('tolerance_state', node.get('state'))} "
                f"wait={node.get('wait_status')} inbox={node.get('inbox_count')} outbox={node.get('outbox_count')} "
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
                f"business_case={node.get('business_case_token_count', 0)} child_count={node.get('child_count', 0)}"
            )
            lines.append(f"  switch_hint=role switch {node.get('node_id', 'unknown')}")
        return "\n".join(lines)

    def prince2_node_queue_report(self) -> dict[str, Any]:
        runtime = self.prince2_node_runtime if isinstance(self.prince2_node_runtime, dict) else {}
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

    def rendered_prince2_node_queues(self) -> str:
        report = self.prince2_node_queue_report()
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

    def prince2_node_control_report(self) -> dict[str, Any]:
        runtime = self.prince2_node_runtime if isinstance(self.prince2_node_runtime, dict) else {}
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
                "summary": self.prince2_node_runtime_summary(),
                "critical_nodes": [],
            }
        active = self.prince2_node_active_report()
        queues = self.prince2_node_queue_report()
        active_nodes = [node for node in active.get("nodes", []) if isinstance(node, dict)]
        queue_rows = {
            str(item.get("node_id", "")): item
            for item in queues.get("queues", [])
            if isinstance(item, dict)
        }
        critical_nodes: list[dict[str, Any]] = []
        waiting_nodes = 0
        blocked_nodes = 0
        escalated_nodes = 0
        inbox_nodes = 0
        for node in active_nodes:
            node_id = str(node.get("node_id", ""))
            state = self._node_tolerance_state(node)
            wait_status = str(node.get("wait_status", "none")).strip().lower() or "none"
            inbox_count = int(node.get("inbox_count", 0) or 0)
            outbox_count = int(node.get("outbox_count", 0) or 0)
            reasons: list[str] = []
            severity = "monitor"
            if state == "escalated":
                escalated_nodes += 1
                severity = "exception"
                margin = self._node_tolerance_margin(node)
                pressure = self._node_tolerance_pressure(node)
                antagonist_pressure = self._node_antagonist_pressure(node)
                reasons.append(
                    f"tolerance pressure {pressure:.2f}% exceeds margin {margin:.2f}%"
                )
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
                child_ids = [str(item.get("node_id", "")) for item in nodes if str(item.get("parent_id", "")).strip() == node_id and str(item.get("node_id", "")).strip()]
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
                        "tolerance_margin_percent": self._node_tolerance_margin(node),
                        "tolerance_pressure_percent": self._node_tolerance_pressure(node),
                        "autonomy_rule": str(node.get("autonomy_rule", "")),
                        "queue_state": str(queue_row.get("state", state)),
                        "child_ids": child_ids,
                        "child_count": len(child_ids),
                        "business_case_token_count": int(node.get("business_case_token_count", 0) or 0),
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
        summary = self.prince2_node_runtime_summary()
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

    def rendered_prince2_node_control(self) -> str:
        report = self.prince2_node_control_report()
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
                f"  - {node.get('label')} [{node.get('node_id')}]: severity={node.get('severity')} "
                f"state={node.get('state')} wait={node.get('wait_status')} "
                f"owner={node.get('accountable_owner', 'user')} margin={node.get('tolerance_margin_percent', 'unknown')} "
                f"pressure={node.get('tolerance_pressure_percent', 'unknown')} "
                f"inbox={node.get('inbox_count')} outbox={node.get('outbox_count')} "
                f"reasons={'; '.join(str(item) for item in node.get('reasons', []))}"
            )
            lines.append(
                f"    thread_tokens total={node.get('thread_token_count', 0)} "
                f"business_case={node.get('business_case_token_count', 0)} child_count={node.get('child_count', 0)}"
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
        message_tokens = max(1, len(" ".join(clean_payload + evidence + [message["summary"]]).split()))
        self._bump_node_thread_tokens(source, amount=max(1, message_tokens // 2), bucket=self._node_flow_bucket(str(edge.get("flow_type", ""))))
        self._bump_node_thread_tokens(target, amount=message_tokens, bucket="business_case")
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
        state = self._node_tolerance_state(node)
        if state == "escalated":
            spawned_child = self._spawn_prince2_escalation_child(
                node_id=node_id,
                reason="tolerance_margin_exceeded",
            )
            antagonist_profile = self._node_antagonist_profile(node)
            node["state"] = "escalated"
            node["wait_status"] = "none"
            node["wait_reason"] = None
            node["last_transition_at"] = _utc_now()
            self.updated_at = _utc_now()
            return {
                "node_id": node_id,
                "state": "escalated",
                "reason": "tolerance_margin_exceeded",
                "escalation_target": str(node.get("escalation_target", "board.executive")),
                "antagonist_name": antagonist_profile.get("antagonist_name", "unknown"),
                "antagonist_pressure_percent": antagonist_profile.get("decision_kpis", {}).get("antagonist_pressure_percent", 0.0)
                if isinstance(antagonist_profile.get("decision_kpis", {}), dict)
                else 0.0,
                "devil_advocate": antagonist_profile.get("devil_advocate", ""),
                "evidence_signals": list(antagonist_profile.get("evidence_signals", []))
                if isinstance(antagonist_profile.get("evidence_signals", []), list)
                else [],
                "evidence_refs": list(antagonist_profile.get("evidence_refs", []))
                if isinstance(antagonist_profile.get("evidence_refs", []), list)
                else [],
                "decision_kpis": dict(antagonist_profile.get("decision_kpis", {}))
                if isinstance(antagonist_profile.get("decision_kpis", {}), dict)
                else {},
                "spawned_child": spawned_child,
                "consumed_message": None,
                "remaining_inbox": len([dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]),
            }
        if state == "completed":
            return {
                "node_id": node_id,
                "state": "completed",
                "consumed_message": None,
                "remaining_inbox": len([dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]),
            }
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

    def tick_prince2_runtime(self, *, max_nodes: int | None = None) -> dict[str, Any]:
        runtime = self.prince2_node_runtime if isinstance(self.prince2_node_runtime, dict) else {}
        if not runtime:
            raise ValueError("No materialized PRINCE2 node runtime. Approve a role-tree baseline first.")
        nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
        if not nodes:
            raise ValueError("No materialized PRINCE2 nodes are available to tick.")
        limit = max_nodes if isinstance(max_nodes, int) and max_nodes > 0 else len(nodes)
        processed = 0
        woken = 0
        progressed = 0
        escalated = 0
        spawned_children = 0
        skipped = 0
        results: list[dict[str, Any]] = []
        for node in nodes:
            if processed >= limit:
                break
            node_id = str(node.get("node_id", "")).strip()
            if not node_id:
                continue
            processed += 1
            state = str(node.get("state", "idle")).strip().lower() or "idle"
            inbox = [dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]
            if state == "waiting" and inbox:
                allowed = [str(item).strip() for item in node.get("wake_triggers", []) if str(item).strip()]
                if "message_received" in allowed:
                    woke_node = self.wake_prince2_node(node_id=node_id, trigger="message_received")
                    state = str(woke_node.get("state", "ready")).strip().lower() or "ready"
                    woken += 1
                    results.append(
                        {
                            "node_id": node_id,
                            "action": "wake",
                            "state": state,
                            "reason": "message_received",
                        }
                    )
                else:
                    skipped += 1
                    results.append(
                        {
                            "node_id": node_id,
                            "action": "skip",
                            "state": state,
                            "reason": "message_waiting_without_authorized_trigger",
                        }
                    )
                    continue
            tolerance_state = self._node_tolerance_state(node)
            if tolerance_state == "escalated":
                tick = self.tick_prince2_node(node_id=node_id)
                escalated += 1
                spawned_child = tick.get("spawned_child") if isinstance(tick.get("spawned_child"), dict) else None
                if spawned_child is not None:
                    spawned_children += 1
                results.append(
                    {
                        "node_id": node_id,
                        "action": "escalate",
                        "state": tick.get("state", "escalated"),
                        "reason": tick.get("reason", "tolerance_margin_exceeded"),
                        "margin_percent": self._node_tolerance_margin(node),
                        "pressure_percent": self._node_tolerance_pressure(node),
                        "spawned_child": spawned_child,
                    }
                )
                continue
            if state in {"ready", "running", "completed"}:
                tick = self.tick_prince2_node(node_id=node_id)
                if tick.get("state") == "escalated":
                    escalated += 1
                    spawned_child = tick.get("spawned_child") if isinstance(tick.get("spawned_child"), dict) else None
                    if spawned_child is not None:
                        spawned_children += 1
                    results.append(
                        {
                            "node_id": node_id,
                            "action": "escalate",
                            "state": tick.get("state", "escalated"),
                            "reason": tick.get("reason", "tolerance_margin_exceeded"),
                            "margin_percent": self._node_tolerance_margin(node),
                            "pressure_percent": self._node_tolerance_pressure(node),
                            "spawned_child": spawned_child,
                        }
                    )
                    continue
                progressed += 1
                results.append(
                    {
                        "node_id": node_id,
                        "action": "tick",
                        "state": tick.get("state", state),
                        "consumed_message": tick.get("consumed_message"),
                        "remaining_inbox": tick.get("remaining_inbox", 0),
                    }
                )
                continue
            skipped += 1
            results.append(
                {
                    "node_id": node_id,
                    "action": "skip",
                    "state": state,
                    "reason": "not_ready",
                }
            )
        self.updated_at = _utc_now()
        return {
            "command": "roles tick",
            "processed": processed,
            "woken": woken,
            "progressed": progressed,
            "escalated": escalated,
            "spawned_children": spawned_children,
            "skipped": skipped,
            "max_nodes": limit,
            "results": results,
            "summary": self.prince2_node_runtime_summary(),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "_format": "stagewarden_project_handoff",
            "_version": 1,
            "task": self.task,
            "goal": dict(self.goal),
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
        if self.status == "waiting":
            return "waiting"
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
        if self.status == "waiting":
            return "resume suspended session when connectivity returns"
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
        if self.status == "waiting":
            return "network_wait"
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
            state = self._node_runtime_state(node)
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

    def _node_tolerance_margin(self, node: dict[str, Any]) -> float:
        try:
            margin = float(node.get("tolerance_margin_percent", 25.0) or 25.0)
        except (TypeError, ValueError):
            return 25.0
        if margin <= 0:
            return 25.0
        return min(margin, 100.0)

    def _node_tolerance_pressure(self, node: dict[str, Any]) -> float:
        try:
            pressure = float(node.get("tolerance_pressure_percent", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
        if pressure < 0:
            return 0.0
        return min(pressure, 100.0)

    def _node_tolerance_state(self, node: dict[str, Any]) -> str:
        state = str(node.get("state", "idle")).strip().lower() or "idle"
        if state == "completed":
            return state
        if state in {"escalated", "blocked"}:
            return state
        margin = self._node_tolerance_margin(node)
        antagonist_pressure = self._node_antagonist_pressure(node) * 0.25
        pressure = max(self._node_tolerance_pressure(node), antagonist_pressure)
        if pressure > margin:
            return "escalated"
        return state

    def _node_thread_token_profile(self, node: dict[str, Any]) -> dict[str, Any]:
        text_parts = [
            str(node.get("label", "")),
            str(node.get("description", "")),
            str(node.get("accountability_boundary", "")),
            str(node.get("delegated_authority", "")),
            str(node.get("responsibility_domain", "")),
            str(node.get("context_scope", "")),
            str(node.get("autonomy_rule", "")),
        ]
        business_case_tokens = sum(len(part.split()) for part in text_parts if part.strip())
        if business_case_tokens <= 0:
            business_case_tokens = 1
        tolerance_profile = node.get("tolerance_profile", {})
        theme_scores = tolerance_profile.get("theme_scores", {}) if isinstance(tolerance_profile, dict) else {}
        kpi_token_counts: dict[str, int] = {}
        for theme in PRINCE2_THEME_NAMES:
            try:
                score = float(theme_scores.get(theme, 0.0))
            except (TypeError, ValueError):
                score = 0.0
            kpi_token_counts[theme] = max(0, int(round(business_case_tokens * score)))
        token_budget = node.get("token_budget")
        try:
            token_budget_value = int(token_budget) if token_budget not in {None, ""} else None
        except (TypeError, ValueError):
            token_budget_value = None
        return {
            "business_case_token_count": business_case_tokens,
            "kpi_token_counts": kpi_token_counts,
            "thread_token_count": business_case_tokens + sum(kpi_token_counts.values()),
            "token_budget": token_budget_value,
        }

    def _node_antagonist_evidence(self, node: dict[str, Any]) -> dict[str, Any]:
        context_rule = node.get("context_rule", {}) if isinstance(node.get("context_rule"), dict) else {}
        include = [str(item).strip() for item in context_rule.get("include", []) if str(item).strip()]
        exclude = [str(item).strip() for item in context_rule.get("exclude", []) if str(item).strip()]
        inbox = [dict(item) for item in node.get("inbox", []) if isinstance(item, dict)] if isinstance(node.get("inbox", []), list) else []
        outbox = [dict(item) for item in node.get("outbox", []) if isinstance(item, dict)] if isinstance(node.get("outbox", []), list) else []
        transcript_refs = [str(item).strip() for item in node.get("transcript_refs", []) if str(item).strip()] if isinstance(node.get("transcript_refs", []), list) else []
        text_fragments = [
            str(node.get("label", "")),
            str(node.get("description", "")),
            str(node.get("accountability_boundary", "")),
            str(node.get("delegated_authority", "")),
            str(node.get("responsibility_domain", "")),
            str(node.get("context_scope", "")),
            str(node.get("autonomy_rule", "")),
            str(node.get("wait_reason", "")),
            str(node.get("spawn_reason", "")),
            str(node.get("spawn_source", "")),
        ]
        text_fragments.extend(include)
        text_fragments.extend(exclude)
        text_fragments.extend(transcript_refs)
        for message in inbox + outbox:
            text_fragments.extend(
                [
                    str(message.get("summary", "")),
                    str(message.get("validation_condition", "")),
                    str(message.get("decision_authority", "")),
                    str(message.get("return_path", "")),
                    " ".join(str(scope) for scope in message.get("payload_scope", []) if str(scope).strip())
                    if isinstance(message.get("payload_scope", []), list)
                    else "",
                    " ".join(str(scope) for scope in message.get("expected_evidence", []) if str(scope).strip())
                    if isinstance(message.get("expected_evidence", []), list)
                    else "",
                    " ".join(str(scope) for scope in message.get("evidence_refs", []) if str(scope).strip())
                    if isinstance(message.get("evidence_refs", []), list)
                    else "",
                ]
            )
        joined = " ".join(fragment for fragment in text_fragments if fragment).lower()
        signal_patterns = {
            "failure": ("error", "failed", "failure", "traceback", "exception", "crash", "broken"),
            "control": ("denied", "unauthorized", "blocked", "reject", "forbidden", "permission"),
            "drift": ("drift", "slip", "creep", "mismatch", "regression", "stale", "missing"),
            "capacity": ("overrun", "budget", "limit", "token", "pressure", "backlog", "queue", "timeout", "stalled", "deadlock", "overload"),
            "risk": ("risk", "threat", "anti-benefit", "objection", "adversary", "attack", "hacker"),
            "coordination": ("handoff", "dependency", "upstream", "downstream", "blocked", "waiting"),
        }
        evidence_signals: list[str] = []
        for label, needles in signal_patterns.items():
            if any(needle in joined for needle in needles):
                evidence_signals.append(label)
        for message in inbox + outbox:
            combined = " ".join(
                str(part)
                for part in (
                    message.get("summary", ""),
                    message.get("detail", ""),
                    message.get("validation_condition", ""),
                    message.get("decision_authority", ""),
                    message.get("return_path", ""),
                )
                if str(part).strip()
            ).lower()
            for label, needles in signal_patterns.items():
                if any(needle in combined for needle in needles) and label not in evidence_signals:
                    evidence_signals.append(label)
        if not evidence_signals:
            if str(node.get("wait_status", "")).strip().lower() != "none":
                evidence_signals.append("waiting")
            elif inbox or outbox:
                evidence_signals.append("queue_pressure")
        evidence_refs: list[str] = []
        for ref in transcript_refs:
            if ref and ref not in evidence_refs:
                evidence_refs.append(ref)
        for message in inbox + outbox:
            refs = message.get("evidence_refs", [])
            if isinstance(refs, list):
                for ref in refs:
                    ref_text = str(ref).strip()
                    if ref_text and ref_text not in evidence_refs:
                        evidence_refs.append(ref_text)
        if not evidence_refs:
            evidence_refs.extend([f"context:{item}" for item in exclude[:2]])
        return {
            "evidence_signals": evidence_signals,
            "evidence_refs": evidence_refs,
            "log_signal_count": len(evidence_signals),
            "evidence_ref_count": len(evidence_refs),
            "signal_summary": ", ".join(evidence_signals) if evidence_signals else "none",
        }

    def _node_antagonist_profile(self, node: dict[str, Any]) -> dict[str, Any]:
        role_type = str(node.get("role_type", "")).strip() or "project_manager"
        label = str(node.get("label", node.get("node_id", "node"))).strip() or "Node"
        context_rule = node.get("context_rule", {}) if isinstance(node.get("context_rule"), dict) else {}
        include = [str(item).strip() for item in context_rule.get("include", []) if str(item).strip()]
        exclude = [str(item).strip() for item in context_rule.get("exclude", []) if str(item).strip()]
        evidence = self._node_antagonist_evidence(node)
        role_shadows = {
            "project_executive": ("benefit erosion", "business case drift", "sponsor fatigue"),
            "senior_user": ("adoption resistance", "unmet acceptance criteria", "benefit leakage"),
            "senior_supplier": ("technical debt", "integration failure", "supplier slippage"),
            "project_manager": ("scope creep", "dependency slip", "exception overload"),
            "project_assurance": ("false assurance", "evidence gaps", "conflict of interest"),
            "change_authority": ("change saturation", "unbounded change", "impact underestimation"),
            "project_support": ("traceability loss", "record corruption", "missing evidence"),
            "team_manager": ("delivery defects", "schedule slip", "resource contention"),
        }
        risk_sources = [f"role-risk:{item}" for item in role_shadows.get(role_type, ("risk drift", "anti-benefit drift"))]
        risk_sources.extend(f"context-exclude:{item}" for item in exclude[:2])
        risk_sources.extend(f"log-signal:{item}" for item in evidence.get("evidence_signals", [])[:4])
        risk_sources.extend(f"log-ref:{item}" for item in evidence.get("evidence_refs", [])[:2])
        anti_benefits = [f"anti-benefit:{item}" for item in include[:2]]
        if not anti_benefits:
            anti_benefits = [f"anti-benefit:{label.lower()} drift"]
        risk_count = len(risk_sources)
        anti_benefit_count = len(anti_benefits)
        evidence_pressure_percent = min(
            40.0,
            round((int(evidence.get("log_signal_count", 0) or 0) * 7.5) + (int(evidence.get("evidence_ref_count", 0) or 0) * 2.5), 2),
        )
        antagonist_pressure_percent = min(100.0, round((risk_count * 12.5) + (anti_benefit_count * 8.0) + evidence_pressure_percent, 2))
        spawn_source = str(node.get("spawn_source", "")).strip().lower()
        if spawn_source == "escalation" and antagonist_pressure_percent > 0:
            antagonist_pressure_percent = min(18.0, round(antagonist_pressure_percent * 0.5, 2))
        decision_kpis = {
            "risk_count": risk_count,
            "anti_benefit_count": anti_benefit_count,
            "threat_count": risk_count + anti_benefit_count + int(evidence.get("log_signal_count", 0) or 0),
            "log_signal_count": int(evidence.get("log_signal_count", 0) or 0),
            "evidence_ref_count": int(evidence.get("evidence_ref_count", 0) or 0),
            "antagonist_pressure_percent": antagonist_pressure_percent,
            "tolerance_margin_percent": self._node_tolerance_margin(node),
            "tolerance_pressure_percent": self._node_tolerance_pressure(node),
            "evidence_pressure_percent": evidence_pressure_percent,
        }
        devil_advocate = (
            f"Challenge the plan with {evidence.get('signal_summary', 'no log signals')} "
            f"against {', '.join(risk_sources[:3]) if risk_sources else 'role risk'}."
        )
        return {
            "antagonist_name": f"{label} Antagonist",
            "role_type": role_type,
            "risk_sources": risk_sources,
            "anti_benefits": anti_benefits,
            "evidence_signals": list(evidence.get("evidence_signals", [])),
            "evidence_refs": list(evidence.get("evidence_refs", [])),
            "countermeasures": [
                f"mitigate {item.split(':', 1)[-1]}" if ":" in item else f"mitigate {item}"
                for item in risk_sources[:3]
            ] or [f"mitigate {label.lower()} threats"],
            "decision_kpis": decision_kpis,
            "devil_advocate": devil_advocate,
            "decision_questions": [
                f"What log evidence contradicts the optimistic reading of {label}?",
                "Which queued messages or transcript refs still lack closure?",
                "What is the cheapest failure path if this node keeps assuming success?",
            ],
            "decision_process": (
                "Treat risks, anti-benefits, and wet-run log evidence as first-class inputs. "
                "Always play devil's advocate against the current plan using runtime signals, "
                "queued messages, transcript refs, and role-specific failure modes. "
                "Spawned recovery children start with attenuated antagonist pressure; "
                "if pressure exceeds tolerance, escalate and spawn recovery work."
            ),
        }

    def _node_antagonist_pressure(self, node: dict[str, Any]) -> float:
        profile = node.get("antagonist_profile", {})
        if isinstance(profile, dict):
            decision_kpis = profile.get("decision_kpis", {})
            if isinstance(decision_kpis, dict):
                try:
                    pressure = float(decision_kpis.get("antagonist_pressure_percent", 0.0) or 0.0)
                except (TypeError, ValueError):
                    pressure = 0.0
                if pressure < 0:
                    return 0.0
                return min(pressure, 100.0)
        return 0.0

    def _node_flow_bucket(self, flow_type: str) -> str:
        clean = str(flow_type).strip().lower()
        if clean in {"authorization", "board_decision"}:
            return "business_case"
        if clean in {"assurance", "quality"}:
            return "quality"
        if clean in {"exception"}:
            return "change"
        if clean in {"delegation"}:
            return "plans"
        if clean in {"record"}:
            return "organization"
        return "progress"

    def _bump_node_thread_tokens(self, node: dict[str, Any], *, amount: int, bucket: str | None = None) -> None:
        if amount <= 0:
            return
        node["thread_token_count"] = int(node.get("thread_token_count", 0) or 0) + amount
        if bucket == "business_case":
            node["business_case_token_count"] = int(node.get("business_case_token_count", 0) or 0) + amount
        kpi_counts = node.get("kpi_token_counts", {})
        if isinstance(kpi_counts, dict) and bucket in PRINCE2_THEME_NAMES:
            kpi_counts[bucket] = int(kpi_counts.get(bucket, 0) or 0) + amount
            node["kpi_token_counts"] = kpi_counts

    def _spawn_prince2_escalation_child(self, *, node_id: str, reason: str) -> dict[str, Any] | None:
        baseline = self.prince2_role_tree_baseline if isinstance(self.prince2_role_tree_baseline, dict) else {}
        tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
        nodes = [node for node in tree.get("nodes", []) if isinstance(node, dict)]
        parent = next((node for node in nodes if str(node.get("node_id", "")).strip() == node_id), None)
        if parent is None:
            return None
        existing_child = next(
            (
                node
                for node in nodes
                if str(node.get("parent_id", "")).strip() == node_id
                and str(node.get("spawn_source", "")).strip().lower() == "escalation"
            ),
            None,
        )
        if existing_child is not None:
            runtime_nodes = [node for node in (self.prince2_node_runtime or {}).get("nodes", []) if isinstance(node, dict)]
            runtime_child = next(
                (node for node in runtime_nodes if str(node.get("node_id", "")).strip() == str(existing_child.get("node_id", ""))),
                None,
            )
            return dict(runtime_child or existing_child)
        existing_ids = {str(node.get("node_id", "")).strip() for node in nodes if str(node.get("node_id", "")).strip()}
        base_child_id = f"{node_id}.escalation"
        child_id = base_child_id
        suffix = 2
        while child_id in existing_ids:
            child_id = f"{base_child_id}_{suffix}"
            suffix += 1
        parent_label = str(parent.get("label", node_id)).strip() or node_id
        parent_role = str(parent.get("role_type", "project_manager")).strip() or "project_manager"
        parent_profile = parent.get("tolerance_profile", {}) if isinstance(parent.get("tolerance_profile", {}), dict) else {}
        thread_profile = self._node_thread_token_profile(parent)
        child = {
            "node_id": child_id,
            "role_type": parent_role,
            "label": f"{parent_label} Escalation Child",
            "description": f"Auto-generated escalation child for {parent_label} after {reason.replace('_', ' ')}.",
            "parent_id": node_id,
            "level": f"delegated_{str(parent.get('level', 'node')).strip() or 'node'}",
            "state": "ready" if parent.get("assignment") else "idle",
            "runtime_status": "active_actor",
            "wait_status": "none",
            "wait_reason": None,
            "wake_triggers": list((parent.get("context_rule") or {}).get("expansion_events", [])) if isinstance(parent.get("context_rule"), dict) else [],
            "context_rule": dict(parent.get("context_rule", {})) if isinstance(parent.get("context_rule"), dict) else {},
            "accountability_boundary": f"escalation recovery lane under {parent_label}",
            "delegated_authority": f"supports {parent_label} within approved tolerances after escalation.",
            "context_scope": str(parent.get("context_scope", "")) or "escalation recovery",
            "responsibility_domain": str(parent.get("responsibility_domain", "")) or "controlled project work",
            "accountable_owner": str(parent.get("accountable_owner", "user")) or "user",
            "tolerance_margin_percent": float(parent.get("tolerance_margin_percent", 25.0) or 25.0),
            "tolerance_pressure_percent": 0.0,
            "autonomy_rule": str(parent.get("autonomy_rule", "")) or "work autonomously within the margin and escalate when pressure exceeds the limit.",
            "escalation_target": str(parent.get("escalation_target", "board.executive")),
            "tolerance_profile": dict(parent_profile),
            "assignment": dict(parent.get("assignment", {})) if isinstance(parent.get("assignment", {}), dict) else {},
            "fallback_pool": list(parent.get("fallback_pool", [])) if isinstance(parent.get("fallback_pool", []), list) else [],
            "readiness": "escalation_spawned",
            "spawn_source": "escalation",
            "spawn_reason": reason,
            "spawned_from": node_id,
            "spawned_at": _utc_now(),
            "business_case_token_count": thread_profile["business_case_token_count"],
            "kpi_token_counts": dict(thread_profile["kpi_token_counts"]),
            "thread_token_count": thread_profile["thread_token_count"],
            "token_budget": thread_profile["token_budget"],
        }
        nodes.append(child)
        tree["nodes"] = nodes
        baseline["tree"] = tree
        baseline["status"] = "approved"
        baseline["source"] = "escalation_spawn"
        baseline["approved_at"] = _utc_now()
        self.sync_prince2_role_tree_baseline(baseline)
        runtime_nodes = [node for node in (self.prince2_node_runtime or {}).get("nodes", []) if isinstance(node, dict)]
        return next((dict(node) for node in runtime_nodes if str(node.get("node_id", "")).strip() == child_id), dict(child))

    def _node_runtime_state(self, node: dict[str, Any]) -> str:
        return self._node_tolerance_state(node)

    def _materialize_prince2_node_runtime(self, baseline: dict[str, Any]) -> dict[str, Any]:
        tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
        flow = baseline.get("flow", {}) if isinstance(baseline.get("flow"), dict) else {}
        nodes = [node for node in tree.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
        child_ids_by_parent: dict[str, list[str]] = {}
        for raw_node in nodes:
            parent_id = str(raw_node.get("parent_id", "")).strip()
            node_id = str(raw_node.get("node_id", "")).strip()
            if not parent_id or not node_id:
                continue
            child_ids_by_parent.setdefault(parent_id, []).append(node_id)
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
            thread_tokens = self._node_thread_token_profile(node)
            antagonist_profile = self._node_antagonist_profile(node)
            child_ids = list(child_ids_by_parent.get(node_id, []))
            materialized_nodes.append(
                {
                    "node_id": node_id,
                    "role_type": str(node.get("role_type", "")),
                    "label": str(node.get("label", node_id)),
                    "description": str(node.get("description", prince2_node_description(node))),
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
                    "accountable_owner": str(node.get("accountable_owner", "user")) or "user",
                    "tolerance_margin_percent": float(node.get("tolerance_margin_percent", 25.0) or 25.0),
                    "tolerance_pressure_percent": float(node.get("tolerance_pressure_percent", 0.0) or 0.0),
                    "autonomy_rule": str(node.get("autonomy_rule", "")),
                    "escalation_target": str(node.get("escalation_target", "board.executive")),
                    "tolerance_profile": dict(node.get("tolerance_profile", {}))
                    if isinstance(node.get("tolerance_profile", {}), dict)
                    else {},
                    "assignment": assignment,
                    "spawn_source": str(node.get("spawn_source", "")),
                    "spawn_reason": str(node.get("spawn_reason", "")),
                    "spawned_from": str(node.get("spawned_from", "")),
                    "spawned_at": str(node.get("spawned_at", "")),
                    "child_ids": child_ids,
                    "child_count": len(child_ids),
                    "business_case_token_count": int(previous.get("business_case_token_count", thread_tokens["business_case_token_count"]) or thread_tokens["business_case_token_count"]),
                    "kpi_token_counts": dict(previous.get("kpi_token_counts", thread_tokens["kpi_token_counts"]))
                    if isinstance(previous.get("kpi_token_counts", thread_tokens["kpi_token_counts"]), dict)
                    else dict(thread_tokens["kpi_token_counts"]),
                    "thread_token_count": int(previous.get("thread_token_count", thread_tokens["thread_token_count"]) or thread_tokens["thread_token_count"]),
                    "token_budget": thread_tokens["token_budget"],
                    "antagonist_profile": dict(antagonist_profile),
                    "antagonist_name": str(antagonist_profile.get("antagonist_name", f"{node.get('label', node_id)} Antagonist")),
                    "antagonist_pressure_percent": float(antagonist_profile.get("decision_kpis", {}).get("antagonist_pressure_percent", 0.0) or 0.0)
                    if isinstance(antagonist_profile.get("decision_kpis", {}), dict)
                    else 0.0,
                    "devil_advocate": str(antagonist_profile.get("devil_advocate", "")),
                    "evidence_signals": list(antagonist_profile.get("evidence_signals", []))
                    if isinstance(antagonist_profile.get("evidence_signals", []), list)
                    else [],
                    "evidence_refs": list(antagonist_profile.get("evidence_refs", []))
                    if isinstance(antagonist_profile.get("evidence_refs", []), list)
                    else [],
                    "decision_kpis": dict(antagonist_profile.get("decision_kpis", {}))
                    if isinstance(antagonist_profile.get("decision_kpis", {}), dict)
                    else {},
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
            goal=dict(payload.get("goal", {})) if isinstance(payload.get("goal", {}), dict) else {},
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
