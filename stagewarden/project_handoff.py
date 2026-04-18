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
    status: str = "idle"
    current_step_id: str | None = None
    current_step_title: str | None = None
    current_step_status: str | None = None
    latest_observation: str = ""
    plan_status: str = ""
    git_head: str | None = None
    git_head_baseline: str | None = None
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

    def close_run(self, *, task: str, success: bool, plan_status: str, git_head: str | None, outcome: str) -> None:
        self.status = "closed" if success else "exception"
        self.current_step_status = "completed" if success else "exception"
        self.plan_status = plan_status
        self.latest_observation = outcome
        self.git_head = git_head
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
        ]
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "_format": "stagewarden_project_handoff",
            "_version": 1,
            "task": self.task,
            "status": self.status,
            "current_step_id": self.current_step_id,
            "current_step_title": self.current_step_title,
            "current_step_status": self.current_step_status,
            "latest_observation": self.latest_observation,
            "plan_status": self.plan_status,
            "git_head": self.git_head,
            "git_head_baseline": self.git_head_baseline,
            "updated_at": self.updated_at,
            "entries": [entry.as_dict() for entry in self.entries],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_utf8(path, dumps_ascii(self.as_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "ProjectHandoff":
        if not path.exists():
            return cls()
        payload = loads_text(read_text_utf8(path))
        context = cls(
            task=str(payload.get("task", "")),
            status=str(payload.get("status", "idle")),
            current_step_id=str(payload["current_step_id"]) if payload.get("current_step_id") else None,
            current_step_title=str(payload["current_step_title"]) if payload.get("current_step_title") else None,
            current_step_status=str(payload["current_step_status"]) if payload.get("current_step_status") else None,
            latest_observation=str(payload.get("latest_observation", "")),
            plan_status=str(payload.get("plan_status", "")),
            git_head=str(payload["git_head"]) if payload.get("git_head") else None,
            git_head_baseline=str(payload["git_head_baseline"]) if payload.get("git_head_baseline") else None,
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
