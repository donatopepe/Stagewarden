from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class PlanStep:
    id: str
    title: str
    instruction: str
    validation: str
    status: str = "pending"
    wet_run_required: bool = True


class Planner:
    def create_plan(self, task: str) -> list[PlanStep]:
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

        return steps

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
