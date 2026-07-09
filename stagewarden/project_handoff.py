from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import project_handoff_state as _project_handoff_state
from . import project_handoff_views as _project_handoff_views
from . import project_handoff_runtime as _project_handoff_runtime
from .textcodec import utc_now


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
    project_budget: dict[str, Any] = field(default_factory=dict)
    user_question: dict[str, Any] = field(default_factory=dict)
    user_question_log: list[dict[str, Any]] = field(default_factory=list)
    project_brief: dict[str, str] = field(default_factory=dict)
    status: str = "idle"
    waiting_reason: str = ""
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
    goal_loop_context: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=utc_now)
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
        self.updated_at = utc_now()
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
        self.updated_at = utc_now()
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
        self.updated_at = utc_now()
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
        self.updated_at = utc_now()

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
        self.updated_at = utc_now()

    def sync_prince2_role_tree_baseline(self, baseline: dict[str, Any]) -> None:
        if not isinstance(baseline, dict):
            self.prince2_role_tree_baseline = {}
            self.prince2_node_runtime = {}
            self.updated_at = utc_now()
            return
        self.prince2_role_tree_baseline = dict(baseline)
        self.prince2_node_runtime = self._materialize_prince2_node_runtime(dict(baseline))
        self.updated_at = utc_now()

    def _project_budget_spend_usd(self) -> float:
        return _project_handoff_state._project_budget_spend_usd(self)

    def project_brief_view(self) -> dict[str, Any]:
        return _project_handoff_state.project_brief_view(self)

    def project_budget_view(self) -> dict[str, Any]:
        return _project_handoff_state.project_budget_view(self)

    def set_project_budget(self, *, budget_usd: float, currency: str = "USD") -> dict[str, Any]:
        return _project_handoff_state.set_project_budget(self, budget_usd=budget_usd, currency=currency)

    def update_project_budget_status(self, status: str) -> dict[str, Any]:
        return _project_handoff_state.update_project_budget_status(self, status)

    def clear_project_budget(self) -> dict[str, Any]:
        return _project_handoff_state.clear_project_budget(self)

    def ask_user(
        self,
        *,
        question: str,
        reason: str = "clarification",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _project_handoff_state.ask_user(self, question=question, reason=reason, context=context)

    def answer_user_question(self, *, answer: str) -> dict[str, Any]:
        return _project_handoff_state.answer_user_question(self, answer=answer)

    def user_question_view(self) -> dict[str, Any]:
        return _project_handoff_state.user_question_view(self)

    def goal_view(self) -> dict[str, Any]:
        return _project_handoff_state.goal_view(self)

    def set_goal(self, *, objective: str, token_budget: int | None = None) -> dict[str, Any]:
        return _project_handoff_state.set_goal(self, objective=objective, token_budget=token_budget)

    def update_goal_status(self, status: str) -> dict[str, Any]:
        return _project_handoff_state.update_goal_status(self, status)

    def record_goal_token_usage(
        self,
        *,
        model: str,
        step_id: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        current_usage: int | None = None,
    ) -> dict[str, Any]:
        return _project_handoff_state.record_goal_token_usage(
            self,
            model=model,
            step_id=step_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            current_usage=current_usage,
        )

    def clear_goal(self) -> dict[str, Any]:
        return _project_handoff_state.clear_goal(self)

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
        self.updated_at = utc_now()
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
        self.updated_at = utc_now()
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

    def record_product_checkpoint(
        self,
        *,
        iteration: int,
        task: str,
        step_id: str,
        step_title: str,
        product_description: str,
        acceptance_criteria: str,
        quality_gate_evidence: str,
        checkpoint_status: str,
        model: str,
        action_type: str,
        git_head: str | None,
    ) -> None:
        self.current_step_id = step_id
        self.current_step_title = step_title
        self.current_step_status = checkpoint_status
        self.git_head = git_head
        self.updated_at = utc_now()
        summary = (
            f"Product description: {product_description[:220]}\n"
            f"Checkpoint summary: {checkpoint_status}; quality evidence captured for controlled handoff."
        )
        self.entries.append(
            HandoffEntry(
                timestamp=self.updated_at,
                phase="product_checkpoint",
                iteration=iteration,
                task=task,
                summary=summary[:500],
                step_id=step_id,
                step_title=step_title,
                step_status=checkpoint_status,
                model=model,
                action_type=action_type,
                git_head=git_head,
                details={
                    "product_id": step_id,
                    "product_description": product_description[:1000],
                    "acceptance_criteria": acceptance_criteria[:1000],
                    "quality_gate_evidence": quality_gate_evidence[:1000],
                    "checkpoint_status": checkpoint_status,
                },
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
        self.updated_at = utc_now()
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
        self.updated_at = utc_now()
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
        return _project_handoff_views.summary(self, limit=limit)

    def detailed_summary(self, limit: int = 8) -> str:
        return _project_handoff_views.detailed_summary(self, limit=limit)

    def stage_view(self) -> dict[str, object]:
        return _project_handoff_views.stage_view(self)

    def rendered_stage_view(self) -> str:
        return _project_handoff_views.rendered_stage_view(self)

    def rendered_register_status_summary(self) -> str:
        return _project_handoff_views.rendered_register_status_summary(self)

    def rendered_stage_health(self) -> str:
        return _project_handoff_views.rendered_stage_health(self)

    def rendered_next_action(self) -> str:
        return _project_handoff_views.rendered_next_action(self)

    def rendered_operational_posture(self) -> str:
        return _project_handoff_views.rendered_operational_posture(self)

    def rendered_risks(self) -> str:
        return _project_handoff_views.rendered_risks(self)

    def rendered_issues(self) -> str:
        return _project_handoff_views.rendered_issues(self)

    def rendered_quality(self) -> str:
        return _project_handoff_views.rendered_quality(self)

    def rendered_exception_plan(self) -> str:
        return _project_handoff_views.rendered_exception_plan(self)

    def rendered_lessons(self) -> str:
        return _project_handoff_views.rendered_lessons(self)

    def rendered_implementation_backlog(self) -> str:
        return _project_handoff_views.rendered_implementation_backlog(self)

    def rendered_project_brief(self) -> str:
        return _project_handoff_views.rendered_project_brief(self)

    def prince2_node_runtime_report(self) -> dict[str, Any]:
        return _project_handoff_views.prince2_node_runtime_report(self)

    def rendered_prince2_node_runtime(self) -> str:
        return _project_handoff_views.rendered_prince2_node_runtime(self)

    def prince2_node_active_report(self) -> dict[str, Any]:
        return _project_handoff_views.prince2_node_active_report(self)

    def rendered_prince2_node_active(self) -> str:
        return _project_handoff_views.rendered_prince2_node_active(self)

    def prince2_node_queue_report(self) -> dict[str, Any]:
        return _project_handoff_views.prince2_node_queue_report(self)

    def rendered_prince2_node_queues(self) -> str:
        return _project_handoff_views.rendered_prince2_node_queues(self)

    def prince2_node_control_report(self) -> dict[str, Any]:
        return _project_handoff_views.prince2_node_control_report(self)

    def rendered_prince2_node_control(self) -> str:
        return _project_handoff_views.rendered_prince2_node_control(self)

    def prince2_node_messages_report(self, node_id: str | None = None) -> dict[str, Any]:
        return _project_handoff_views.prince2_node_messages_report(self, node_id=node_id)

    def rendered_prince2_node_messages(self, node_id: str | None = None) -> str:
        return _project_handoff_views.rendered_prince2_node_messages(self, node_id=node_id)


def _bind_runtime_method(name: str):
    def _wrapper(self: ProjectHandoff, *args: Any, **kwargs: Any):
        return getattr(_project_handoff_runtime, name)(self, *args, **kwargs)

    return _wrapper


for _method_name in (
    "send_prince2_node_message",
    "set_prince2_node_waiting",
    "wake_prince2_node",
    "tick_prince2_node",
    "tick_prince2_runtime",
    "as_dict",
    "save",
    "record_issue",
    "record_quality",
    "record_lesson",
    "update_project_brief",
    "clear_project_brief",
    "close_issues_for_step",
    "close_all_open_issues",
    "close_all_open_risks",
    "finalize_quality_register",
    "clear_exception_plan_if_recovered",
    "_seed_risk_register",
    "_build_exception_plan",
    "_register_status_summary",
    "_stage_health",
    "_next_action",
    "_parse_plan_status",
    "_boundary_decision",
    "_recovery_state",
    "_implementation_backlog_status_summary",
    "_normalize_backlog_status",
    "prince2_node_runtime_summary",
    "_prince2_runtime_node",
    "_node_tolerance_margin",
    "_node_tolerance_pressure",
    "_node_tolerance_state",
    "_node_model_pricing",
    "_node_thread_token_profile",
    "_node_antagonist_evidence",
    "_node_antagonist_profile",
    "_node_antagonist_pressure",
    "_node_flow_bucket",
    "_bump_node_thread_tokens",
    "_spawn_prince2_escalation_child",
    "_node_runtime_state",
    "_materialize_prince2_node_runtime",
):
    setattr(ProjectHandoff, _method_name, _bind_runtime_method(_method_name))

ProjectHandoff.load = classmethod(_project_handoff_runtime.load_project_handoff)
