from __future__ import annotations


PRINCE2_ROLE_AUTOMATION_RULES: dict[str, str] = {
    "project_executive": "business justification, benefits, cost tolerance, and stop/go escalation",
    "project_manager": "planning, coordination, controlled execution, reporting, and stage boundary control",
    "team_manager": "implementation and product delivery within the agreed work package",
    "project_assurance": "independent validation, quality evidence, risk/issue review, and closure checks",
    "change_authority": "change requests, exceptions, re-baselining, and tolerance breaches",
    "senior_user": "user value, acceptance, adoption, and benefit realization checks",
    "senior_supplier": "technical feasibility, supplier risk, and specialist delivery integrity",
    "project_support": "logs, handoff, records, git snapshots, and administrative traceability",
}


PRINCE2_ROLE_SCOPE_DESCRIPTIONS: dict[str, str] = {
    "project_executive": "business justification, benefits, cost/risk tolerance, and stop-go decisions only",
    "project_manager": "stage plan, coordination, registers, reporting, and controlled execution",
    "team_manager": "current work package, product delivery, quality criteria, and implementation lessons only",
    "project_assurance": "quality evidence, risk/issue controls, lessons, and independent validation",
    "change_authority": "change impact, exception plan, tolerances, risks, issues, and re-baseline evidence",
    "senior_user": "user value, acceptance criteria, adoption impact, quality, and benefits",
    "senior_supplier": "technical feasibility, supplier risk, delivery integrity, and quality",
    "project_support": "handoff records, logs, traceability, issues, quality records, and git evidence",
}
