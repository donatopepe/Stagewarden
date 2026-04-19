from __future__ import annotations

import re
from dataclasses import dataclass

from .project_handoff import ProjectHandoff


@dataclass(slots=True)
class PlanStep:
    id: str
    title: str
    instruction: str
    validation: str
    status: str = "planned"
    wet_run_required: bool = True


class Planner:
    def create_plan(self, task: str, *, project_handoff: ProjectHandoff | None = None) -> list[PlanStep]:
        chunks = self._extract_chunks(task)
        steps: list[PlanStep] = []

        if not chunks:
            chunks = [
                "inspect the codebase or workspace relevant to the task",
                "implement the requested changes",
                "validate the result with a direct check",
            ]

        for index, chunk in enumerate(chunks, start=1):
            title = self._title_from_chunk(chunk, index)
            validation = self._validation_for_chunk(chunk)
            steps.append(
                PlanStep(
                    id=f"step-{index}",
                    title=title,
                    instruction=chunk.strip(),
                    validation=validation,
                    status="planned",
                    wet_run_required=True,
                )
            )

        self._apply_handoff_context(steps, task=task, project_handoff=project_handoff)
        self._promote_ready_step(steps)
        return self._compress_completed_prefix(steps)

    def _apply_handoff_context(
        self,
        steps: list[PlanStep],
        *,
        task: str,
        project_handoff: ProjectHandoff | None,
    ) -> None:
        if not project_handoff or not steps:
            return
        if not project_handoff.task or project_handoff.task.strip() != task.strip():
            return

        status_by_step = self._parse_plan_status(project_handoff.plan_status)
        for step in steps:
            previous_status = status_by_step.get(step.id)
            if previous_status in {"pending", "planned", "ready", "in_progress", "completed", "failed"}:
                step.status = self._normalize_status(previous_status)

        if project_handoff.status not in {"executing", "planned", "exception"}:
            return

        current_step_id = project_handoff.current_step_id
        if not current_step_id:
            self._apply_register_context(steps, project_handoff=project_handoff)
            return
        for step in steps:
            if step.id != current_step_id:
                continue
            if step.status == "completed":
                break
            observation = project_handoff.latest_observation.strip()
            continuation_note = (
                f"continue from persisted handoff context for: {step.instruction}"
            )
            if observation:
                continuation_note += f" | latest_observation={observation[:160]}"
            step.instruction = continuation_note
            if not step.title.lower().startswith("resume"):
                step.title = f"Resume {step.title}"
            break

        self._apply_register_context(steps, project_handoff=project_handoff)

    def _apply_register_context(self, steps: list[PlanStep], *, project_handoff: ProjectHandoff) -> None:
        target = next((step for step in steps if step.status in {"ready", "in_progress", "failed"}), None)
        if target is None:
            return

        notes: list[str] = []
        if project_handoff.risk_register:
            open_risks = [
                item.get("risk", "").strip()
                for item in project_handoff.risk_register
                if item.get("status", "open").strip().lower() != "closed" and item.get("risk")
            ]
            if open_risks:
                notes.append(f"open_risks={'; '.join(open_risks[:2])}")

        if project_handoff.issue_register:
            open_issues = [
                item.get("summary", "").strip()
                for item in project_handoff.issue_register
                if item.get("status", "open").strip().lower() != "closed" and item.get("summary")
            ]
            if open_issues:
                notes.append(f"open_issues={'; '.join(open_issues[:2])}")

        if project_handoff.quality_register:
            latest_quality = next(
                (
                    item
                    for item in reversed(project_handoff.quality_register)
                    if item.get("evidence") or item.get("status")
                ),
                None,
            )
            if latest_quality:
                evidence = latest_quality.get("evidence", "").strip()
                status = latest_quality.get("status", "").strip()
                if evidence or status:
                    notes.append(f"quality_baseline={status}:{evidence}".strip(":"))

        if project_handoff.lessons_log:
            latest_lesson = next(
                (
                    item.get("lesson", "").strip()
                    for item in reversed(project_handoff.lessons_log)
                    if item.get("lesson")
                ),
                "",
            )
            if latest_lesson:
                notes.append(f"lesson={latest_lesson}")

        if project_handoff.exception_plan and project_handoff.status == "exception":
            notes.append(f"exception_plan={'; '.join(project_handoff.exception_plan[:2])}")

        if notes:
            target.instruction = f"{target.instruction} | {' | '.join(notes)}"
            target.validation = f"{target.validation} Use PRINCE2 register context to close open risks, issues, and quality gaps."

    def _extract_chunks(self, task: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", task).strip()
        parts = re.split(r"[.;]\s+|\s+\band\b\s+", normalized)
        cleaned = [part.strip(" -") for part in parts if len(part.strip(" -")) > 8]

        if len(cleaned) == 1:
            sentence = cleaned[0]
            return [
                f"analyze the requirements for: {sentence}",
                f"implement: {sentence}",
                f"validate that the implementation satisfies the request: {sentence}",
            ]

        return cleaned

    def _title_from_chunk(self, chunk: str, index: int) -> str:
        words = chunk.split()
        return f"{index}. {' '.join(words[:6]).capitalize()}"

    def _validation_for_chunk(self, chunk: str) -> str:
        lower = chunk.lower()
        if "test" in lower or "validate" in lower:
            return "A real wet-run command or observable result confirms the step passed; dry-run alone is not valid."
        if "implement" in lower or "build" in lower or "create" in lower:
            return "The target files or behavior exist and a real wet-run verifies the change."
        if "analyze" in lower or "inspect" in lower:
            return "The agent can state concrete findings and, where possible, verify them with a real command."
        return "The step yields a concrete artifact or wet-run observation."

    def _compress_completed_prefix(self, steps: list[PlanStep]) -> list[PlanStep]:
        completed_prefix: list[PlanStep] = []
        remaining = list(steps)
        while remaining and remaining[0].status == "completed":
            completed_prefix.append(remaining.pop(0))

        if len(completed_prefix) < 2:
            return steps

        closed_summary = "; ".join(step.title for step in completed_prefix)
        archived = PlanStep(
            id="stage-archive-1",
            title=f"Closed stages {completed_prefix[0].id}-{completed_prefix[-1].id}",
            instruction=f"historical completed stages compressed from handoff context: {closed_summary}",
            validation="Historical handoff stages already completed and closed under PRINCE2 stage control.",
            status="completed",
            wet_run_required=False,
        )
        return [archived, *remaining]

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

    def _promote_ready_step(self, steps: list[PlanStep]) -> None:
        if any(step.status == "in_progress" for step in steps):
            return
        if any(step.status == "ready" for step in steps):
            return
        for step in steps:
            if step.status in {"planned", "pending"}:
                step.status = "ready"
                return

    def _normalize_status(self, status: str) -> str:
        value = status.strip().lower()
        if value == "pending":
            return "planned"
        if value in {"planned", "ready", "in_progress", "completed", "failed"}:
            return value
        return "planned"
