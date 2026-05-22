from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .planner import PlanStep


@dataclass(slots=True)
class ResponseQualityAssessment:
    score: float
    threshold: float
    sufficient: bool
    reasons: list[str]
    signals: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "threshold": round(self.threshold, 3),
            "sufficient": self.sufficient,
            "reasons": list(self.reasons),
            "signals": dict(self.signals),
        }


def assess_response_quality(
    *,
    task: str,
    step: PlanStep,
    observation: str,
    action_type: str,
    step_completed: bool,
    prince2_assessment: dict[str, Any] | None,
) -> ResponseQualityAssessment:
    prompt_text = " ".join(
        part
        for part in (
            task,
            step.id,
            step.title,
            step.instruction,
            step.validation,
            step.wet_run_required and "wet run required" or "",
        )
        if part
    ).lower()
    observation_text = observation.lower().strip()
    prompt_terms = [
        term
        for term in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", prompt_text)
        if term not in {"the", "and", "for", "with", "step", "task", "validate", "validation"}
    ]
    unique_terms = list(dict.fromkeys(prompt_terms))
    matched_terms = [term for term in unique_terms if term in observation_text]
    coverage = len(matched_terms) / max(4, min(len(unique_terms), 10)) if unique_terms else 0.0

    strong_evidence_markers = (
        "exit_code=0",
        "wet-run validation passed",
        "validation completed",
        "wrote file",
        "patched file",
        "patched files",
        "completed",
        "validated",
        "done",
    )
    weak_evidence_markers = (
        "summary:",
        "result:",
        "observed",
        "confirmed",
        "implemented",
        "updated",
        "checked",
    )
    contradiction_markers = (
        "blocked",
        "unable",
        "failed",
        "error",
        "invalid",
        "missing",
        "unclear",
        "insufficient",
    )

    strong_evidence = any(marker in observation_text for marker in strong_evidence_markers)
    weak_evidence = any(marker in observation_text for marker in weak_evidence_markers)
    contradictions = [marker for marker in contradiction_markers if marker in observation_text]
    if isinstance(prince2_assessment, dict) and prince2_assessment.get("escalation_required"):
        contradictions.append("prince2_escalation_required")

    words = re.findall(r"[a-z0-9][a-z0-9_-]{2,}", observation_text)
    specificity = min(1.0, len(words) / 18.0)
    evidence_strength = 1.0 if strong_evidence else 0.62 if weak_evidence else 0.2
    completion_bias = 0.12 if step_completed or action_type == "complete" else 0.0
    contradiction_penalty = min(0.55, 0.14 * len(dict.fromkeys(contradictions)))
    score = max(0.0, min(1.0, (0.46 * coverage) + (0.30 * evidence_strength) + (0.18 * specificity) + completion_bias - contradiction_penalty))
    prompt_complexity = min(1.0, len(unique_terms) / 12.0) if unique_terms else 0.0
    threshold = 0.30 + (0.20 * prompt_complexity)
    if any(
        token in prompt_text
        for token in (
            "regulatory",
            "compliance",
            "security",
            "migration",
            "vendor",
            "incident",
            "recovery",
            "board",
            "legal",
            "breach",
            "supplier",
            "procurement",
        )
    ):
        threshold += 0.05
    threshold = max(0.40, min(0.72, threshold))
    reasons: list[str] = []
    if coverage < 0.35:
        reasons.append("Response does not cover enough prompt-specific terms.")
    if not strong_evidence:
        reasons.append("Response does not show strong validation evidence.")
    if specificity < 0.35:
        reasons.append("Response is too generic to prove the requested outcome.")
    if contradictions:
        reasons.append("Response contains contradiction or insufficiency markers.")
    sufficient = score >= threshold and not contradictions and (strong_evidence or step_completed)
    signals = {
        "coverage": round(coverage, 3),
        "evidence_strength": round(evidence_strength, 3),
        "specificity": round(specificity, 3),
        "strong_evidence": strong_evidence,
        "weak_evidence": weak_evidence,
        "contradictions": list(dict.fromkeys(contradictions)),
        "matched_terms": matched_terms,
        "unique_terms": unique_terms[:12],
        "step_completed": step_completed,
        "action_type": action_type,
    }
    return ResponseQualityAssessment(
        score=score,
        threshold=threshold,
        sufficient=sufficient,
        reasons=reasons,
        signals=signals,
    )
