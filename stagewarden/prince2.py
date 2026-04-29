from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8


PRINCE2_THEME_NAMES: tuple[str, ...] = (
    "business_case",
    "organization",
    "quality",
    "plans",
    "risk",
    "change",
    "progress",
)

PRINCE2_ROLE_TOLERANCE_WEIGHTS: dict[str, dict[str, float]] = {
    "project_executive": {
        "business_case": 0.32,
        "organization": 0.10,
        "quality": 0.05,
        "plans": 0.08,
        "risk": 0.20,
        "change": 0.10,
        "progress": 0.15,
    },
    "project_manager": {
        "business_case": 0.12,
        "organization": 0.10,
        "quality": 0.15,
        "plans": 0.24,
        "risk": 0.14,
        "change": 0.10,
        "progress": 0.15,
    },
    "team_manager": {
        "business_case": 0.05,
        "organization": 0.08,
        "quality": 0.26,
        "plans": 0.22,
        "risk": 0.14,
        "change": 0.10,
        "progress": 0.15,
    },
    "project_assurance": {
        "business_case": 0.10,
        "organization": 0.12,
        "quality": 0.30,
        "plans": 0.12,
        "risk": 0.18,
        "change": 0.10,
        "progress": 0.08,
    },
    "change_authority": {
        "business_case": 0.08,
        "organization": 0.05,
        "quality": 0.10,
        "plans": 0.15,
        "risk": 0.22,
        "change": 0.30,
        "progress": 0.10,
    },
    "senior_user": {
        "business_case": 0.24,
        "organization": 0.10,
        "quality": 0.18,
        "plans": 0.12,
        "risk": 0.10,
        "change": 0.08,
        "progress": 0.18,
    },
    "senior_supplier": {
        "business_case": 0.06,
        "organization": 0.08,
        "quality": 0.18,
        "plans": 0.22,
        "risk": 0.16,
        "change": 0.16,
        "progress": 0.14,
    },
    "project_support": {
        "business_case": 0.08,
        "organization": 0.24,
        "quality": 0.16,
        "plans": 0.18,
        "risk": 0.10,
        "change": 0.08,
        "progress": 0.16,
    },
}


def _clamp_percentage(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _parse_margin_percent(value: object, default: float = 25.0) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        parsed = float(text)
    except ValueError:
        return default
    if parsed <= 0:
        return default
    return _clamp_percentage(parsed)


def _weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    total = 0.0
    weight_total = 0.0
    for theme in PRINCE2_THEME_NAMES:
        weight = max(0.0, float(weights.get(theme, 0.0)))
        if not weight:
            continue
        total += float(scores.get(theme, 0.0)) * weight
        weight_total += weight
    if weight_total <= 0:
        return 0.0
    return max(0.0, min(1.0, total / weight_total))


@dataclass(slots=True)
class Prince2Checklist:
    business_justification: str
    product_focus: str
    adaptation_policy: str
    role_policy: str
    stage_plan: list[str]
    quality_criteria: list[str]
    risks: list[str]
    issues: list[str]
    tolerances: dict[str, str]
    controls: list[str]
    closure_criteria: list[str]
    lessons_policy: str
    stage_boundary_review: str
    tolerance_profile: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "business_justification": self.business_justification,
            "product_focus": self.product_focus,
            "adaptation_policy": self.adaptation_policy,
            "role_policy": self.role_policy,
            "stage_plan": list(self.stage_plan),
            "quality_criteria": list(self.quality_criteria),
            "risks": list(self.risks),
            "issues": list(self.issues),
            "tolerances": dict(self.tolerances),
            "controls": list(self.controls),
            "closure_criteria": list(self.closure_criteria),
            "lessons_policy": self.lessons_policy,
            "stage_boundary_review": self.stage_boundary_review,
            "tolerance_profile": dict(self.tolerance_profile),
        }

    def render_for_prompt(self) -> str:
        lines = [
            f"Business justification: {self.business_justification}",
            f"Product focus: {self.product_focus}",
            f"Adaptation policy: {self.adaptation_policy}",
            f"Role policy: {self.role_policy}",
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
        tolerance_profile = self.tolerance_profile
        if isinstance(tolerance_profile, dict) and tolerance_profile:
            margin = tolerance_profile.get("margin_percent")
            pressure = tolerance_profile.get("pressure_percent")
            owner = tolerance_profile.get("accountable_owner")
            lines.extend(
                [
                    "Tolerance profile:",
                    f"- accountable_owner: {owner}",
                    f"- default_margin_percent: {tolerance_profile.get('base_margin_percent')}",
                    f"- margin_percent: {margin}",
                    f"- pressure_percent: {pressure}",
                    "- themes:",
                    *[
                        f"- {theme}: {score}"
                        for theme, score in sorted((tolerance_profile.get("theme_scores", {}) or {}).items())
                    ],
                ]
            )
        return "\n".join(lines)


@dataclass(slots=True)
class Prince2ToleranceProfile:
    base_margin_percent: float
    accountable_owner: str
    theme_scores: dict[str, float]
    project_margin_percent: float
    project_pressure_percent: float
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "base_margin_percent": _clamp_percentage(self.base_margin_percent),
            "accountable_owner": self.accountable_owner,
            "theme_scores": {key: round(max(0.0, min(1.0, float(value))), 3) for key, value in self.theme_scores.items()},
            "margin_percent": _clamp_percentage(self.project_margin_percent),
            "pressure_percent": _clamp_percentage(self.project_pressure_percent),
            "notes": list(self.notes),
        }

    def render_for_prompt(self) -> str:
        lines = [
            f"Accountable owner: {self.accountable_owner}",
            f"Default margin percent: {self.base_margin_percent}",
            f"Project margin percent: {self.project_margin_percent}",
            f"Project pressure percent: {self.project_pressure_percent}",
            "Seven-theme scores:",
        ]
        for theme in PRINCE2_THEME_NAMES:
            lines.append(f"- {theme}: {self.theme_scores.get(theme, 0.0):.2f}")
        if self.notes:
            lines.append("Notes:")
            lines.extend(f"- {item}" for item in self.notes)
        return "\n".join(lines)

    def node_profile(self, role_type: str) -> dict[str, Any]:
        weights = PRINCE2_ROLE_TOLERANCE_WEIGHTS.get(role_type, PRINCE2_ROLE_TOLERANCE_WEIGHTS["project_manager"])
        score = _weighted_score(self.theme_scores, weights)
        pressure = _clamp_percentage((1.0 - score) * 100.0)
        margin = _clamp_percentage(self.base_margin_percent * (0.85 + (0.30 * score)))
        autonomy = "autonomous" if pressure <= margin else "escalate"
        return {
            "role_type": role_type,
            "accountable_owner": self.accountable_owner,
            "base_margin_percent": _clamp_percentage(self.base_margin_percent),
            "margin_percent": margin,
            "pressure_percent": pressure,
            "score": round(score, 3),
            "autonomy_state": autonomy,
            "autonomy_rule": "work autonomously within the margin; escalate to the Project Executive when pressure exceeds margin.",
            "escalation_target": "board.executive",
            "theme_scores": {key: round(max(0.0, min(1.0, float(value))), 3) for key, value in self.theme_scores.items()},
            "weights": dict(weights),
        }


@dataclass(slots=True)
class Prince2Assessment:
    allowed: bool
    escalation_required: bool
    reasons: list[str]
    closure_ready: bool
    escalation_notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "escalation_required": self.escalation_required,
            "reasons": list(self.reasons),
            "closure_ready": self.closure_ready,
            "escalation_notes": list(self.escalation_notes),
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
    def build_tolerance_profile(
        self,
        task: str,
        checklist: Prince2Checklist,
        *,
        project_brief: dict[str, str] | None = None,
        base_margin_percent: float = 25.0,
        accountable_owner: str = "user",
    ) -> Prince2ToleranceProfile:
        brief = {str(key).strip().lower(): str(value).strip() for key, value in (project_brief or {}).items() if str(key).strip()}
        lowered = task.lower()
        risky = any(token in lowered for token in ("delete", "drop", "prod", "production", "payment", "auth", "migration", "security"))
        change_heavy = any(token in lowered for token in ("change", "update", "refactor", "rewrite", "replace", "migrate", "rebaseline", "re-baseline"))
        exploratory = any(token in lowered for token in ("analyze", "inspect", "review", "assess", "investigate"))
        objective_present = bool(brief.get("objective"))
        scope_present = bool(brief.get("scope"))
        outputs_present = bool(brief.get("expected_outputs"))
        delivery_mode = brief.get("delivery_mode", "").lower()
        quality_gates_present = bool(brief.get("quality_gates"))
        stakeholders_present = bool(brief.get("stakeholders"))
        risk_tolerance = brief.get("risk_tolerance", "").lower()

        theme_scores = {
            "business_case": 0.60 + (0.14 if objective_present else 0.0) + (0.14 if scope_present else 0.0) + (0.12 if outputs_present else 0.0),
            "organization": 0.58 + (0.12 if stakeholders_present else 0.0) + (0.10 if delivery_mode else 0.0) + (0.08 if checklist.role_policy else 0.0),
            "quality": 0.56 + (0.12 if quality_gates_present else 0.0) + (0.12 if checklist.quality_criteria else 0.0) + (0.10 if any(token in lowered for token in ("validate", "test", "review", "verify")) else 0.0),
            "plans": 0.55 + (0.10 if checklist.stage_plan else 0.0) + (0.10 if delivery_mode else 0.0) + (0.10 if scope_present else 0.0),
            "risk": 0.72 - (0.20 if risky else 0.0) + (0.08 if risk_tolerance in {"high", "broad", "wide"} else 0.0) - (0.08 if risk_tolerance in {"low", "tight"} else 0.0),
            "change": 0.68 - (0.14 if change_heavy else 0.0) - (0.08 if exploratory else 0.0) + (0.08 if any(token in brief.get("uncertainty", "").lower() for token in ("low", "stable")) else 0.0),
            "progress": 0.58 + (0.10 if checklist.stage_boundary_review else 0.0) + (0.10 if checklist.controls else 0.0) + (0.10 if objective_present and scope_present and outputs_present else 0.0),
        }
        for theme in PRINCE2_THEME_NAMES:
            theme_scores[theme] = _clamp_percentage(theme_scores[theme] * 100.0) / 100.0
            theme_scores[theme] = max(0.35, min(1.0, theme_scores[theme]))
        project_score = _weighted_score(theme_scores, {theme: 1.0 for theme in PRINCE2_THEME_NAMES})
        project_pressure_percent = _clamp_percentage((1.0 - project_score) * 100.0)
        project_margin_percent = _clamp_percentage(base_margin_percent * (0.85 + (0.30 * project_score)))
        notes = [
            "Seven PRINCE2 themes inform the tolerance margin: business case, organization, quality, plans, risk, change, progress.",
            "The user remains the accountable Project Executive; nodes only exercise delegated autonomy inside the computed margin.",
        ]
        if risky:
            notes.append("Risk-heavy language lowers the computed tolerance margin and increases pressure.")
        if change_heavy:
            notes.append("Change-heavy language lowers the computed tolerance margin for delegated work.")
        return Prince2ToleranceProfile(
            base_margin_percent=_clamp_percentage(base_margin_percent),
            accountable_owner=accountable_owner or "user",
            theme_scores=theme_scores,
            project_margin_percent=project_margin_percent,
            project_pressure_percent=project_pressure_percent,
            notes=notes,
        )

    def build_checklist(self, task: str, project_brief: dict[str, str] | None = None, base_margin_percent: float = 25.0, accountable_owner: str = "user") -> Prince2Checklist:
        lowered = task.lower()
        risky = any(token in lowered for token in ("delete", "drop", "prod", "payment", "auth", "migration", "security"))
        code_task = any(token in lowered for token in ("implement", "fix", "refactor", "create", "update", "patch", "code"))

        business_justification = "Proceed only if task still serves requested outcome and remains worth time/risk."
        product_focus = "Define deliverables first, then actions and tools."
        adaptation_policy = (
            "Adapt governance to task size, risk, and complexity. "
            "Small tasks use the lightest viable controls; complex or risky tasks require stricter staged control. "
            "If the method feels heavier than the task, reduce paperwork, not principles."
        )
        role_policy = (
            "Keep responsibility explicit for every stage: who requested the outcome, which model acts, which tool executes, "
            f"and who validates completion. The accountable Project Executive is the user, with delegated models acting inside a {base_margin_percent:.0f}% default tolerance unless the project brief specifies otherwise."
        )
        stage_plan = [
            "Verify objective, context, and constraints.",
            "Plan a bounded next step with validation and no overengineering.",
            "Execute one controlled change or observation.",
            "Validate outcome against quality criteria.",
            "Escalate or close at stage boundary.",
        ]
        quality_criteria = [
            "Output matches the requested outcome.",
            "No evident regression or contradiction.",
            "Validation evidence exists or limitation is explicit.",
            "Governance remains proportionate to the task; no unnecessary bureaucracy.",
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
            "For small tasks, keep documentation and controls minimal but explicit.",
            "For complex or risky tasks, increase formal controls, evidence, and boundary checks.",
            "Keep trace, memory, and validation evidence.",
        ]
        closure_criteria = [
            "Deliverables complete or explicitly excluded.",
            "Validation performed or blocked with reason.",
            "Residual risks and assumptions communicated.",
        ]
        lessons_policy = "Use prior attempts and failures to adjust the next step."
        stage_boundary_review = "At each stage boundary, re-check business case, risks, quality, and whether to continue."
        tolerance_profile = self.build_tolerance_profile(
            task,
            Prince2Checklist(
                business_justification=business_justification,
                product_focus=product_focus,
                adaptation_policy=adaptation_policy,
                role_policy=role_policy,
                stage_plan=stage_plan,
                quality_criteria=quality_criteria,
                risks=risks,
                issues=issues,
                tolerances=tolerances,
                controls=controls,
                closure_criteria=closure_criteria,
                lessons_policy=lessons_policy,
                stage_boundary_review=stage_boundary_review,
            ),
            project_brief=project_brief,
            base_margin_percent=base_margin_percent,
            accountable_owner=accountable_owner,
        ).as_dict()

        return Prince2Checklist(
            business_justification=business_justification,
            product_focus=product_focus,
            adaptation_policy=adaptation_policy,
            role_policy=role_policy,
            stage_plan=stage_plan,
            quality_criteria=quality_criteria,
            risks=risks,
            issues=issues,
            tolerances=tolerances,
            controls=controls,
            closure_criteria=closure_criteria,
            lessons_policy=lessons_policy,
            stage_boundary_review=stage_boundary_review,
            tolerance_profile=tolerance_profile,
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

        tolerance_profile = checklist.tolerance_profile if isinstance(checklist.tolerance_profile, dict) else {}
        margin = _parse_margin_percent(tolerance_profile.get("margin_percent"), default=25.0)
        pressure = _parse_margin_percent(tolerance_profile.get("pressure_percent"), default=0.0)
        escalation_notes: list[str] = []
        if pressure > margin:
            escalation_required = True
            escalation_notes.append(
                f"Computed PRINCE2 tolerance pressure {pressure:.2f}% exceeds margin {margin:.2f}%."
            )

        allowed = not reasons
        closure_ready = allowed and bool(checklist.closure_criteria) and bool(checklist.quality_criteria)
        return Prince2Assessment(
            allowed=allowed,
            escalation_required=escalation_required,
            reasons=reasons,
            closure_ready=closure_ready,
            escalation_notes=escalation_notes,
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
            "adaptation": "Use light governance for small tasks and stricter governance for complex or risky work without dropping principles.",
            "tolerance": "Nodes operate autonomously while pressure remains inside the computed PRINCE2 margin; cross the margin and escalate to the accountable Project Executive.",
        }
        if any(token in lowered for token in ("test", "validate", "check")):
            approaches["quality"] = "Use direct executable validation before claiming completion."
        if any(token in lowered for token in ("prod", "production", "security", "auth")):
            approaches["risk"] = "Treat task as high-impact and use tighter review and escalation."
        tolerance_profile = checklist.tolerance_profile if isinstance(checklist.tolerance_profile, dict) else {}
        if tolerance_profile:
            approaches["tolerance"] = (
                "Project margin "
                f"{tolerance_profile.get('margin_percent', '25')}% vs pressure "
                f"{tolerance_profile.get('pressure_percent', '0')}%; escalate when pressure exceeds margin."
            )

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
