from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8


@dataclass(slots=True)
class Prince2Checklist:
    business_justification: str
    product_focus: str
    stage_plan: list[str]
    quality_criteria: list[str]
    risks: list[str]
    issues: list[str]
    tolerances: dict[str, str]
    controls: list[str]
    closure_criteria: list[str]
    lessons_policy: str
    stage_boundary_review: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "business_justification": self.business_justification,
            "product_focus": self.product_focus,
            "stage_plan": list(self.stage_plan),
            "quality_criteria": list(self.quality_criteria),
            "risks": list(self.risks),
            "issues": list(self.issues),
            "tolerances": dict(self.tolerances),
            "controls": list(self.controls),
            "closure_criteria": list(self.closure_criteria),
            "lessons_policy": self.lessons_policy,
            "stage_boundary_review": self.stage_boundary_review,
        }

    def render_for_prompt(self) -> str:
        lines = [
            f"Business justification: {self.business_justification}",
            f"Product focus: {self.product_focus}",
            "Stage plan:",
            *[f"- {item}" for item in self.stage_plan],
            "Quality criteria:",
            *[f"- {item}" for item in self.quality_criteria],
            "Key risks:",
            *[f"- {item}" for item in self.risks],
            "Issue policy:",
            *[f"- {item}" for item in self.issues],
            "Tolerances:",
            *[f"- {key}: {value}" for key, value in self.tolerances.items()],
            "Controls:",
            *[f"- {item}" for item in self.controls],
            "Closure criteria:",
            *[f"- {item}" for item in self.closure_criteria],
            f"Lessons policy: {self.lessons_policy}",
            f"Stage boundary review: {self.stage_boundary_review}",
        ]
        return "\n".join(lines)


@dataclass(slots=True)
class Prince2Assessment:
    allowed: bool
    escalation_required: bool
    reasons: list[str]
    closure_ready: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "escalation_required": self.escalation_required,
            "reasons": list(self.reasons),
            "closure_ready": self.closure_ready,
        }


@dataclass(slots=True)
class Prince2PID:
    version: int
    task: str
    business_case: str
    project_product: str
    stage_plan: list[str]
    quality_criteria: list[str]
    tolerances: dict[str, str]
    controls: list[str]
    risks: list[str]
    issues_policy: list[str]
    closure_criteria: list[str]
    stage_boundary_review: str
    management_approaches: dict[str, str]
    status: str = "initiated"
    outcome: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "_format": "stagewarden_prince2_pid",
            "_version": self.version,
            "task": self.task,
            "business_case": self.business_case,
            "project_product": self.project_product,
            "stage_plan": list(self.stage_plan),
            "quality_criteria": list(self.quality_criteria),
            "tolerances": dict(self.tolerances),
            "controls": list(self.controls),
            "risks": list(self.risks),
            "issues_policy": list(self.issues_policy),
            "closure_criteria": list(self.closure_criteria),
            "stage_boundary_review": self.stage_boundary_review,
            "management_approaches": dict(self.management_approaches),
            "status": self.status,
            "outcome": self.outcome,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_utf8(path, dumps_ascii(self.as_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "Prince2PID":
        payload = loads_text(read_text_utf8(path))
        return cls(
            version=int(payload.get("_version", 1)),
            task=str(payload["task"]),
            business_case=str(payload["business_case"]),
            project_product=str(payload["project_product"]),
            stage_plan=[str(item) for item in payload.get("stage_plan", [])],
            quality_criteria=[str(item) for item in payload.get("quality_criteria", [])],
            tolerances={str(key): str(value) for key, value in payload.get("tolerances", {}).items()},
            controls=[str(item) for item in payload.get("controls", [])],
            risks=[str(item) for item in payload.get("risks", [])],
            issues_policy=[str(item) for item in payload.get("issues_policy", [])],
            closure_criteria=[str(item) for item in payload.get("closure_criteria", [])],
            stage_boundary_review=str(payload.get("stage_boundary_review", "")),
            management_approaches={
                str(key): str(value) for key, value in payload.get("management_approaches", {}).items()
            },
            status=str(payload.get("status", "initiated")),
            outcome=str(payload["outcome"]) if payload.get("outcome") is not None else None,
        )


class Prince2AgentPolicy:
    def build_checklist(self, task: str) -> Prince2Checklist:
        lowered = task.lower()
        risky = any(token in lowered for token in ("delete", "drop", "prod", "payment", "auth", "migration", "security"))
        code_task = any(token in lowered for token in ("implement", "fix", "refactor", "create", "update", "patch", "code"))

        business_justification = "Proceed only if task still serves requested outcome and remains worth time/risk."
        product_focus = "Define deliverables first, then actions and tools."
        stage_plan = [
            "Verify objective, context, and constraints.",
            "Plan a bounded next step with validation.",
            "Execute one controlled change or observation.",
            "Validate outcome against quality criteria.",
            "Escalate or close at stage boundary.",
        ]
        quality_criteria = [
            "Output matches the requested outcome.",
            "No evident regression or contradiction.",
            "Validation evidence exists or limitation is explicit.",
        ]
        if code_task:
            quality_criteria.append("Changed code is syntactically consistent and tested proportionally.")

        risks = [
            "Requirement misunderstanding.",
            "Regression from file, command, or patch execution.",
            "Continuing after business justification has weakened.",
        ]
        if risky:
            risks.append("Irreversible or high-impact action requires tighter control and explicit caution.")

        issues = [
            "Treat runtime errors, blockers, and schema conflicts as issues.",
            "Escalate when tolerance is exceeded or forecast to be exceeded.",
        ]
        tolerances = {
            "time": "bounded by max_steps and task complexity",
            "scope": "do not drift beyond requested deliverable",
            "risk": "stop or escalate on high-impact uncertainty",
            "quality": "do not claim completion without validation evidence",
        }
        controls = [
            "Work stage-by-stage.",
            "Use management by exception.",
            "Keep trace, memory, and validation evidence.",
        ]
        closure_criteria = [
            "Deliverables complete or explicitly excluded.",
            "Validation performed or blocked with reason.",
            "Residual risks and assumptions communicated.",
        ]
        lessons_policy = "Use prior attempts and failures to adjust the next step."
        stage_boundary_review = "At each stage boundary, re-check business case, risks, quality, and whether to continue."

        return Prince2Checklist(
            business_justification=business_justification,
            product_focus=product_focus,
            stage_plan=stage_plan,
            quality_criteria=quality_criteria,
            risks=risks,
            issues=issues,
            tolerances=tolerances,
            controls=controls,
            closure_criteria=closure_criteria,
            lessons_policy=lessons_policy,
            stage_boundary_review=stage_boundary_review,
        )

    def assess_task(self, task: str, checklist: Prince2Checklist) -> Prince2Assessment:
        lowered = task.lower()
        reasons: list[str] = []
        escalation_required = False

        risky_tokens = ("delete", "drop", "prod", "production", "payment", "auth", "migration", "security")
        if len(task.strip()) < 8:
            reasons.append("Task too vague to establish business justification and product focus.")
        if not any(token in lowered for token in ("create", "implement", "fix", "update", "write", "read", "analyze", "validate", "review", "plan")):
            reasons.append("Task does not express a clear product or management outcome.")
        if any(token in lowered for token in risky_tokens):
            escalation_required = True
            if "validate" not in lowered and "test" not in lowered and "review" not in lowered:
                reasons.append("High-impact task lacks explicit validation or review criteria.")

        allowed = not reasons
        closure_ready = allowed and bool(checklist.closure_criteria) and bool(checklist.quality_criteria)
        return Prince2Assessment(
            allowed=allowed,
            escalation_required=escalation_required,
            reasons=reasons,
            closure_ready=closure_ready,
        )

    def assess_completion(self, observation: str, checklist: Prince2Checklist) -> Prince2Assessment:
        lowered = observation.lower()
        reasons: list[str] = []
        if not observation.strip():
            reasons.append("No validation evidence was produced.")
        weak_markers = ("blocked", "unable", "failed", "error", "invalid")
        if any(marker in lowered for marker in weak_markers):
            reasons.append("Observation indicates unresolved issue or weak closure evidence.")
        strong_markers = (
            "complete",
            "completed",
            "completata",
            "completato",
            "done",
            "validated",
            "validazione completata",
            "analisi completata",
            "wrote file",
            "patched file",
            "patched files",
            "exit_code=0",
            "wet-run validation passed",
            "stdout:",
        )
        if not any(marker in lowered for marker in strong_markers):
            reasons.append("Completion message does not clearly confirm the product outcome.")

        allowed = not reasons
        return Prince2Assessment(
            allowed=allowed,
            escalation_required=not allowed,
            reasons=reasons,
            closure_ready=allowed and bool(checklist.closure_criteria),
        )

    def build_pid(self, task: str, checklist: Prince2Checklist) -> Prince2PID:
        lowered = task.lower()
        approaches = {
            "change": "Record issues and changes, then escalate when tolerances are threatened.",
            "communication": "Keep concise progress, explicit blockers, and final residual risk reporting.",
            "quality": "Validate each stage with direct evidence or state the limitation clearly.",
            "risk": "Prefer lowest-cost safe route, but escalate risky work automatically.",
            "digital_data": "Persist traces, memory, and artifacts in structured workspace files.",
        }
        if any(token in lowered for token in ("test", "validate", "check")):
            approaches["quality"] = "Use direct executable validation before claiming completion."
        if any(token in lowered for token in ("prod", "production", "security", "auth")):
            approaches["risk"] = "Treat task as high-impact and use tighter review and escalation."

        return Prince2PID(
            version=1,
            task=task,
            business_case=checklist.business_justification,
            project_product=checklist.product_focus,
            stage_plan=list(checklist.stage_plan),
            quality_criteria=list(checklist.quality_criteria),
            tolerances=dict(checklist.tolerances),
            controls=list(checklist.controls),
            risks=list(checklist.risks),
            issues_policy=list(checklist.issues),
            closure_criteria=list(checklist.closure_criteria),
            stage_boundary_review=checklist.stage_boundary_review,
            management_approaches=approaches,
        )
