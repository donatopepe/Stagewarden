from __future__ import annotations

from collections.abc import Mapping

from ..config import AgentConfig
from ..project_handoff import ProjectHandoff


PROJECT_BRIEF_FIELDS: dict[str, str] = {
    "objective": "Why the project exists and what outcome it should achieve.",
    "scope": "What is in scope for this project brief.",
    "expected_outputs": "What deliverables or outcomes must exist at completion.",
    "delivery_mode": "Delivery approach such as agile, sequential, hybrid, or investigative.",
    "constraints": "Known limits such as budget, time, regulatory, or platform constraints.",
    "quality_gates": "Explicit acceptance or validation gates required before closure.",
    "stakeholders": "Key stakeholders, sponsors, users, suppliers, or reviewers.",
    "uncertainty": "Known uncertainty, ambiguity, or discovery level.",
    "risk_tolerance": "Declared tolerance or escalation posture for risk.",
    "tolerance_margin_percent": "Default per-node tolerance margin, usually 25, before escalation is required.",
    "accountable_project_executive": "Human accountable owner for the Project Executive decision line; defaults to user.",
}

AMBIGUOUS_BRIEF_MARKERS = {
    "?",
    "tbd",
    "todo",
    "unknown",
    "unclear",
    "unsure",
    "not sure",
    "to decide",
    "to be decided",
    "decide later",
    "da definire",
    "da decidere",
    "non so",
}


def project_brief_value_is_ambiguous(value: object) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    compact = " ".join(text.replace("…", " ").split())
    return compact in AMBIGUOUS_BRIEF_MARKERS


def project_brief_ambiguous_gaps(fields: Mapping[str, object]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for field_name in ("objective", "scope", "expected_outputs", "delivery_mode"):
        value = fields.get(field_name)
        if project_brief_value_is_ambiguous(value):
            gaps.append(
                {
                    "code": f"ambiguous_{field_name}",
                    "message": f"Project brief {field_name} is ambiguous ({value}); ask the user for a concrete value before planning.",
                }
            )
    return gaps


def project_brief_missing_fields(config: AgentConfig) -> list[str]:
    handoff = ProjectHandoff.load(config.handoff_path)
    missing: list[str] = []
    for field_name in ("objective", "scope", "expected_outputs", "delivery_mode"):
        if not handoff.project_brief.get(field_name):
            missing.append(field_name)
    return missing


def project_gap_to_brief_field(gap_code: str) -> str | None:
    gap_map = {
        "missing_project_task": "objective",
        "missing_project_objective": "objective",
        "missing_project_scope": "scope",
        "missing_expected_outputs": "expected_outputs",
        "missing_delivery_mode": "delivery_mode",
        "missing_objective": "objective",
        "missing_scope": "scope",
        "ambiguous_objective": "objective",
        "ambiguous_scope": "scope",
        "ambiguous_expected_outputs": "expected_outputs",
        "ambiguous_delivery_mode": "delivery_mode",
    }
    return gap_map.get(gap_code)


def project_brief_guidance(config: AgentConfig) -> str:
    missing = project_brief_missing_fields(config)
    if not missing:
        return "Project brief is complete enough for structured gates."
    first = missing[0]
    description = PROJECT_BRIEF_FIELDS.get(first, "Provide this field.")
    return (
        "Next missing project brief field: "
        f"{first}\n- meaning: {description}\n- action: project brief set {first} <value>"
    )


def project_brief_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    missing = project_brief_missing_fields(config)
    return {
        "command": "project brief",
        "fields": dict(handoff.project_brief),
        "supported_fields": dict(PROJECT_BRIEF_FIELDS),
        "count": len(handoff.project_brief),
        "next_missing_field": missing[0] if missing else None,
        "guidance": project_brief_guidance(config),
    }


def render_project_brief(config: AgentConfig) -> str:
    report = project_brief_report(config)
    lines = ["Project brief:"]
    fields = report["fields"]
    if isinstance(fields, dict) and fields:
        for key in sorted(fields):
            lines.append(f"- {key}: {fields[key]}")
    else:
        lines.append("- none")
    lines.append("Supported fields:")
    for key in sorted(PROJECT_BRIEF_FIELDS):
        lines.append(f"- {key}: {PROJECT_BRIEF_FIELDS[key]}")
    lines.append(project_brief_guidance(config))
    return "\n".join(lines)


def handle_project_brief_command(command: str, config: AgentConfig) -> str | None:
    parts = command.split()
    if parts[:2] != ["project", "brief"]:
        return None
    handoff = ProjectHandoff.load(config.handoff_path)
    if len(parts) == 2:
        return render_project_brief(config)
    if len(parts) >= 4 and parts[2] == "set":
        field_name = parts[3].strip().lower()
        if field_name not in PROJECT_BRIEF_FIELDS:
            return f"Unsupported project brief field '{field_name}'. Supported: {', '.join(sorted(PROJECT_BRIEF_FIELDS))}"
        prefix = f"project brief set {parts[3]}"
        value = command[len(prefix):].strip()
        if not value:
            return "Usage: project brief set <field> <value>"
        handoff.update_project_brief({field_name: value})
        handoff.save(config.handoff_path)
        return (
            f"Project brief updated: {field_name}={handoff.project_brief.get(field_name, '')}\n"
            f"{project_brief_guidance(config)}"
        )
    if len(parts) >= 3 and parts[2] == "clear":
        if len(parts) == 3:
            handoff.clear_project_brief()
            handoff.save(config.handoff_path)
            return "Project brief cleared."
        field_name = parts[3].strip().lower()
        if field_name not in PROJECT_BRIEF_FIELDS:
            return f"Unsupported project brief field '{field_name}'. Supported: {', '.join(sorted(PROJECT_BRIEF_FIELDS))}"
        handoff.clear_project_brief(field_name)
        handoff.save(config.handoff_path)
        return f"Project brief field cleared: {field_name}"
    return "Usage: project brief | project brief set <field> <value> | project brief clear [field]"
