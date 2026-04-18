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
    status: str = "pending"
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
                    wet_run_required=True,
                )
            )

        self._apply_handoff_context(steps, task=task, project_handoff=project_handoff)
        return steps

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
            if previous_status in {"pending", "in_progress", "completed", "failed"}:
                step.status = previous_status

        if project_handoff.status not in {"executing", "planned", "exception"}:
            return

        current_step_id = project_handoff.current_step_id
        if not current_step_id:
            return
        for step in steps:
            if step.id != current_step_id:
                continue
            if step.status == "completed":
                return
            observation = project_handoff.latest_observation.strip()
            continuation_note = (
                f"continue from persisted handoff context for: {step.instruction}"
            )
            if observation:
                continuation_note += f" | latest_observation={observation[:160]}"
            step.instruction = continuation_note
            if not step.title.lower().startswith("resume"):
                step.title = f"Resume {step.title}"
            return

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
