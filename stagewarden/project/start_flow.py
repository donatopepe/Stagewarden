from __future__ import annotations

from ..agent import Agent
from ..config import AgentConfig
from ..modelprefs import ModelPreferences
from .. import model_views as _model_views
from ..project_handoff import ProjectHandoff
from .. import project_handoff_views as _project_handoff_views
from . import design_flow as _project_design_flow
from . import flow as _project_flow
from . import tree_flow as _project_tree_flow
from . import role_views as _project_role_views
from . import role_tree_views as _project_role_tree_views


def _project_tree_ai_needed(design: dict[str, object], proposal: dict[str, object]) -> bool:
    if proposal.get("status") != "ready_for_review":
        return False
    project = design.get("project_specification") if isinstance(design.get("project_specification"), dict) else {}
    brief = project.get("brief") if isinstance(project.get("brief"), dict) else {}
    text = " ".join(str(value).lower() for value in brief.values())
    complexity_tokens = (
        "complex",
        "regulated",
        "enterprise",
        "multi-vendor",
        "multi provider",
        "rate-limit",
        "rate limit",
        "high uncertainty",
        "alto rischio",
        "alta incertezza",
        "security",
        "auth",
        "compliance",
    )
    return any(token in text for token in complexity_tokens)


def _project_start_clarification_record(
    config: AgentConfig,
    *,
    design_gaps: list[dict[str, str]],
    proposal_gaps: list[dict[str, str]],
) -> dict[str, object] | None:
    question_sources = [item for item in design_gaps + proposal_gaps if isinstance(item, dict)]
    if not question_sources:
        return None
    handoff = ProjectHandoff.load(config.handoff_path)
    if handoff.status == "waiting" and handoff.waiting_reason == "clarification" and handoff.user_question:
        return dict(handoff.user_question)
    first_gap = question_sources[0]
    gap_code = str(first_gap.get("code", "missing_field")).strip()
    gap_message = str(first_gap.get("message", "Project brief needs clarification.")).strip()
    question_map = {
        "missing_project_task": "What project outcome or objective should I prioritize?",
        "missing_project_objective": "What is the objective of this project?",
        "missing_project_scope": "What is in scope for this project?",
        "missing_expected_outputs": "What deliverables or outputs should exist at completion?",
        "missing_delivery_mode": "What delivery mode should I assume?",
    }
    question = question_map.get(gap_code, gap_message)
    record = handoff.ask_user(
        question=question,
        reason="clarification",
        context={
            "source": "project start",
            "gap_code": gap_code,
            "design_gaps": design_gaps,
            "proposal_gaps": proposal_gaps,
        },
    )
    handoff.save(config.handoff_path)
    _project_handoff_views._record_handoff_action(
        config,
        phase="project_start_clarification_requested",
        summary=f"Project startup asked for clarification: {question[:120]}",
        task="project start",
        details={
            "question": record,
            "design_gaps": design_gaps,
            "proposal_gaps": proposal_gaps,
        },
    )
    return record


def _project_tree_clarification_record(
    config: AgentConfig,
    *,
    gaps: list[dict[str, str]],
) -> dict[str, object] | None:
    question_sources = [item for item in gaps if isinstance(item, dict)]
    if not question_sources:
        return None
    handoff = ProjectHandoff.load(config.handoff_path)
    if handoff.status == "waiting" and handoff.waiting_reason == "clarification" and handoff.user_question:
        return dict(handoff.user_question)
    first_gap = question_sources[0]
    gap_code = str(first_gap.get("code", "missing_field")).strip()
    gap_message = str(first_gap.get("message", "Project tree needs clarification.")).strip()
    question_map = {
        "missing_objective": "What objective should this project tree optimize for?",
        "missing_scope": "What is in scope for this project tree?",
        "missing_expected_outputs": "What outputs should this project tree deliver?",
        "missing_delivery_mode": "What delivery mode should I assume for the tree design?",
    }
    question = question_map.get(gap_code, gap_message)
    record = handoff.ask_user(
        question=question,
        reason="clarification",
        context={
            "source": "project tree propose",
            "gap_code": gap_code,
            "gaps": gaps,
        },
    )
    handoff.save(config.handoff_path)
    _project_handoff_views._record_handoff_action(
        config,
        phase="project_tree_clarification_requested",
        summary=f"Project tree proposal asked for clarification: {question[:120]}",
        task="project tree propose",
        details={
            "question": record,
            "gaps": gaps,
        },
    )
    return record


def _project_start_report(agent: Agent, config: AgentConfig, prefs: ModelPreferences, *, force_ai: bool = False) -> dict[str, object]:
    design = _project_design_flow._project_design_report(agent, config)
    local_proposal = _project_tree_flow._project_tree_proposal_report(config)
    use_ai = force_ai or _project_tree_ai_needed(design, local_proposal)
    proposal = _project_tree_flow._project_tree_proposal_report(config, agent=agent, use_ai=True) if use_ai else local_proposal
    ignored_startup_design_gaps = {"role_tree_not_ready", "missing_role_tree_baseline"}
    raw_design_gaps = design.get("clarification_gaps", [])
    design_gaps = [
        item
        for item in raw_design_gaps
        if isinstance(item, dict) and str(item.get("code", "")) not in ignored_startup_design_gaps
    ] if isinstance(raw_design_gaps, list) else []
    proposal_gaps = proposal.get("clarification_gaps", [])
    has_gaps = bool(design_gaps or proposal_gaps)
    next_gap = None
    if design_gaps:
        next_gap = design_gaps[0]
    elif isinstance(proposal_gaps, list) and proposal_gaps:
        next_gap = proposal_gaps[0] if isinstance(proposal_gaps[0], dict) else None
    next_missing_field = _project_flow._project_gap_to_brief_field(str(next_gap.get("code", "")).strip()) if isinstance(next_gap, dict) else None
    report: dict[str, object] = {
        "command": "project start",
        "status": "blocked" if has_gaps or proposal.get("status") != "ready_for_review" else "approved",
        "force_ai": force_ai,
        "ready": not (has_gaps or proposal.get("status") != "ready_for_review"),
        "design": design,
        "proposal": proposal,
        "design_gaps": design_gaps,
        "proposal_gaps": proposal_gaps if isinstance(proposal_gaps, list) else [],
        "next_missing_gap": next_gap,
        "next_missing_field": next_missing_field,
    }
    if report["status"] == "blocked":
        clarification = _project_start_clarification_record(
            config,
            design_gaps=design_gaps if isinstance(design_gaps, list) else [],
            proposal_gaps=proposal_gaps if isinstance(proposal_gaps, list) else [],
        )
        if isinstance(clarification, dict) and clarification.get("question"):
            report["clarification_question"] = clarification
        _project_handoff_views._record_handoff_action(
            config,
            phase="project_start_blocked",
            summary="Project startup blocked by unresolved design/proposal clarification gaps.",
            task="project start",
            details={
                "design_gaps": design_gaps,
                "proposal_gaps": proposal_gaps if isinstance(proposal_gaps, list) else [],
                "proposal_status": proposal.get("status"),
                "ai_requested": proposal.get("ai_requested"),
                "ai_assistance": proposal.get("ai_assistance"),
                "next_missing_field": next_missing_field,
            },
        )
        return report
    approval = _project_tree_flow._approve_project_tree_proposal(config, force=False, proposal_report=proposal)
    _model_views._apply_model_preferences(agent, config)
    _project_handoff_views._record_handoff_action(
        config,
        phase="project_start_approved",
        summary="Project startup approved through controlled project-tree proposal path.",
        task="project start",
        details={
            "approval_status": approval.get("status"),
            "forced": approval.get("forced"),
            "proposal_added_nodes": proposal.get("added_nodes", []),
            "ai_requested": proposal.get("ai_requested"),
            "ai_assistance": proposal.get("ai_assistance"),
            "local_execution": proposal.get("local_execution", {}),
        },
    )
    report["approval"] = approval
    local_execution = proposal.get("local_execution") if isinstance(proposal.get("local_execution"), dict) else {}
    local_candidates = [item for item in local_execution.get("candidates", []) if isinstance(item, dict)]
    if local_candidates:
        lines = ["Project start local fallback preload:"]
        lines.append(
            "- candidates: "
            + ", ".join(str(item.get("id", "")) for item in local_candidates if str(item.get("id", "")).strip())
        )
        if local_execution.get("message"):
            lines.append(f"- recommendation: {local_execution.get('message')}")
        lines.append("- status: approved baseline includes recommended local delivery fallback routes.")
        report["local_fallback_preload"] = lines
    return report


def _render_project_start_report(report: dict[str, object], agent: Agent, config: AgentConfig, prefs: ModelPreferences) -> str:
    sections = [
        "Project startup design gate:",
        _project_design_flow._render_project_design(agent, config),
        _project_tree_flow._render_project_tree_proposal_report(report.get("proposal", {}) if isinstance(report.get("proposal"), dict) else _project_tree_flow._project_tree_proposal_report(config)),
    ]
    if report.get("status") == "blocked":
        lines = [
            "Project startup blocked:",
            "- reason: project design/proposal has unresolved clarification gaps.",
            "- action: complete /project brief fields, rerun /project tree propose, then rerun /project start.",
            "- override: use /project tree approve --force if the Project Board accepts the gaps explicitly.",
        ]
        for item in report.get("design_gaps", []) if isinstance(report.get("design_gaps"), list) else []:
            if isinstance(item, dict):
                lines.append(f"- design_gap {item.get('code', 'gap')}: {item.get('message', 'missing')}")
        for item in report.get("proposal_gaps", []) if isinstance(report.get("proposal_gaps"), list) else []:
            if isinstance(item, dict):
                lines.append(f"- proposal_gap {item.get('code', 'gap')}: {item.get('message', 'missing')}")
        next_field = report.get("next_missing_field")
        if next_field:
            lines.append(f"- next_missing_field: {next_field}")
        clarification = report.get("clarification_question") if isinstance(report.get("clarification_question"), dict) else None
        if isinstance(clarification, dict) and clarification.get("question"):
            lines.append("Clarification question:")
            lines.append(f"- question: {clarification.get('question')}")
            lines.append("- answer: use /answer <response> or update the brief then rerun /project start")
        sections.append("\n".join(lines))
    else:
        approval = report.get("approval") if isinstance(report.get("approval"), dict) else None
        if approval:
            sections.append(_project_tree_flow._render_project_tree_approval_report(approval, config))
        local_fallback = report.get("local_fallback_preload")
        if isinstance(local_fallback, list) and local_fallback:
            sections.append("\n".join(local_fallback))
        sections.extend(
        [
            _project_role_views._render_prince2_roles(config),
            _project_role_tree_views._render_prince2_role_tree_baseline(config),
        ]
    )
    return "\n\n".join(sections)


def _render_project_start(agent: Agent, config: AgentConfig, prefs: ModelPreferences, *, force_ai: bool = False) -> str:
    return _render_project_start_report(_project_start_report(agent, config, prefs, force_ai=force_ai), agent, config, prefs)


def _project_start_ready(config: AgentConfig) -> bool:
    handoff = ProjectHandoff.load(config.handoff_path)
    if not handoff.task.strip():
        return False
    for field_name in ("objective", "scope", "expected_outputs", "delivery_mode"):
        if not handoff.project_brief.get(field_name):
            return False
    return True
