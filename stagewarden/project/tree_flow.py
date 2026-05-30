from __future__ import annotations

import copy
import re
from dataclasses import replace
from datetime import datetime

from ..agent import Agent
from ..config import AgentConfig
from ..handoff import format_run_model
from ..modelprefs import PRINCE2_ROLE_IDS, PRINCE2_ROLE_LABELS, provider_model_specs
from .. import agent_setup_views as _agent_setup_views
from .. import model_views as _model_views
from ..project_handoff import ProjectHandoff
from .. import project_handoff_views as _project_handoff_views
from . import design_flow as _project_design_flow
from . import role_flow as _project_role_flow
from . import flow as _project_flow
from ..role_tree import (
    build_prince2_role_flow,
    build_prince2_role_matrix_payload,
    build_prince2_role_tree_with_tolerance,
    check_prince2_role_tree_payload,
)
from . import role_tree_views as _project_role_tree_views
from ..textcodec import dumps_ascii, loads_text


def _project_tree_proposal_report(config: AgentConfig, *, agent: Agent | None = None, use_ai: bool = False) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    prefs = _model_views._load_model_preferences(config)
    proposed_roles = prefs.propose_prince2_roles()
    merged_roles = dict(proposed_roles)
    merged_roles.update(prefs.prince2_roles or {})
    proposal_prefs = replace(prefs, prince2_roles=merged_roles)
    active_models = list(proposal_prefs.active_models() or proposal_prefs.enabled_models)
    brief = {str(key): str(value) for key, value in handoff.project_brief.items()}
    joined = " ".join(value.lower() for value in brief.values())
    tolerance_profile = _project_role_flow._project_tolerance_profile(handoff, task=handoff.task or None)
    local_execution = _model_views._local_execution_candidates_report(config, agent=agent, use_ai=use_ai)
    decomposition_nodes, decomposition = _project_flow._project_tree_decomposition_nodes(
        proposal_prefs=proposal_prefs,
        active_models=active_models,
        brief=brief,
        joined=joined,
        tolerance_profile=tolerance_profile,
    )
    base_tree = build_prince2_role_tree_with_tolerance(
        proposal_prefs,
        tolerance_profile=tolerance_profile,
        accountable_owner=tolerance_profile.accountable_owner,
    )
    nodes = [dict(node) for node in base_tree.get("nodes", []) if isinstance(node, dict)]
    nodes.extend(decomposition_nodes)
    added_nodes: list[str] = [str(node.get("node_id")) for node in decomposition_nodes if str(node.get("node_id"))]
    assumptions: list[str] = []
    if decomposition.get("micro_task_count", 0):
        assumptions.append("Project tree is decomposed into the smallest independently verifiable micro-tasks.")
    if local_execution.get("candidates"):
        assumptions.append("Local execution candidates were used to keep the tree dynamic and runtime-aware.")

    delivery_keywords = ("cli", "shell", "git", "code", "coding", "test", "tests", "download", "web", "compression", "multi", "windows", "linux", "macos")
    complex_delivery = any(keyword in joined for keyword in delivery_keywords) or brief.get("delivery_mode", "").lower() in {"hybrid", "agile", "iterative", "investigative"}
    if complex_delivery:
        node_id = "delivery.implementation_team"
        nodes.append(
            _project_flow._role_node_from_template(
                node_id=node_id,
                role_type="team_manager",
                label="Implementation Team Manager",
                parent_id="management.project_manager",
                level="delivery",
                accountability_boundary="delegated delivery of implementation work packages within agreed tolerances",
                delegated_authority="executes implementation work packages and escalates forecast tolerance breaches",
                assignment=_project_flow._assignment_for_role(proposal_prefs, "team_manager"),
                active_models=active_models,
                tolerance_profile=tolerance_profile,
                accountable_owner=tolerance_profile.accountable_owner,
            )
        )
        added_nodes.append(node_id)
        assumptions.append("Project brief indicates implementation complexity, so a delegated implementation Team Manager node is proposed.")

    tree = dict(base_tree)
    tree["command"] = "project tree propose"
    tree["source"] = "project_brief_local_rules"
    tree["nodes"] = nodes
    tree["decomposition_policy"] = "Decompose the project into the smallest independently verifiable work packages and keep widening only when evidence justifies it."
    tree["adaptation_policy"] = "Refresh the tree continuously from the latest brief, tolerance profile, runtime observation, and response-quality signals."
    tree["decomposition"] = decomposition
    tree["adaptation"] = _project_flow._project_tree_adaptation_snapshot(brief=brief, handoff=handoff, local_execution=local_execution)
    tree = _project_flow._enrich_tree_with_local_execution_candidates(tree, local_execution)
    check = check_prince2_role_tree_payload(tree, proposal_prefs)
    matrix = build_prince2_role_matrix_payload(tree, proposal_prefs)
    gaps: list[dict[str, str]] = []
    for required in ("objective", "scope", "expected_outputs", "delivery_mode"):
        if not brief.get(required):
            gaps.append({"code": f"missing_{required}", "message": f"Project brief is missing {required}."})
    gaps.extend(_project_flow.project_brief_ambiguous_gaps(brief))
    report = {
        "command": "project tree propose",
        "status": "ready_for_review" if not gaps and check.get("status") != "error" else "needs_clarification",
        "source": "local_rules",
        "ai_requested": bool(use_ai),
        "ai_assistance": {
            "attempted": False,
            "ok": None,
            "model": None,
            "account": None,
            "message": "AI assistance was not requested.",
            "valid_added_nodes": [],
            "rejected_nodes": [],
        },
        "project_brief": brief,
        "assumptions": assumptions,
        "added_nodes": added_nodes,
        "tree": tree,
        "decomposition": decomposition,
        "adaptation": tree["adaptation"],
        "local_execution": local_execution,
        "check": check,
        "matrix": matrix,
        "clarification_gaps": gaps,
        "next_missing_gap": gaps[0] if gaps else None,
        "next_missing_field": _project_flow._project_gap_to_brief_field(str(gaps[0].get("code", "")).strip()) if gaps and isinstance(gaps[0], dict) else None,
        "approval_rule": "proposal only; user or Project Board must approve before persistence",
    }
    if use_ai and not gaps:
        active_agent = agent or _agent_setup_views._configure_readonly_agent_for_workspace(config)
        report = _merge_ai_project_tree_proposal(active_agent, config, report)
    return report


def _project_tree_ai_prompt(design: dict[str, object], local_report: dict[str, object]) -> str:
    packet = {
        "purpose": "Design a proportional PRINCE2 role-tree proposal for Stagewarden.",
        "rules": [
            "Return only valid JSON.",
            "Do not persist or approve anything.",
            "Suggest only additional nodes that are justified by the project brief.",
            "Prefer the smallest independently verifiable work packages possible; do not widen the tree unless the brief or evidence requires it.",
            "Each node must have node_id, role_type, label, parent_id, level, accountability_boundary, and delegated_authority.",
            "Allowed role_type values: " + ", ".join(PRINCE2_ROLE_IDS),
            "Respect PRINCE2 accountability boundaries and keep each node context limited to its responsibility domain.",
            "If you propose custom context slices, include context_include/context_exclude and do not widen beyond the node domain.",
            "Include tolerance_boundary, validation_condition, and open_questions when useful for review.",
            "Treat the tree as living: explain how the proposal should refresh when brief, risk, validation, or response-quality signals change.",
            "Prefer cheaper/local providers unless the node domain requires stronger reasoning.",
        ],
        "expected_schema": {
            "summary": "short rationale",
            "assumptions": ["short assumption"],
            "refresh_reason": "why the tree should be refreshed now",
            "tree_patches": [
                {
                    "node_id": "lowercase.dot_or_underscore_id",
                    "role_type": "project_manager",
                    "label": "Node label",
                    "parent_id": "management.project_manager",
                    "level": "management",
                    "accountability_boundary": "bounded accountability/delegation statement",
                    "delegated_authority": "what this node may decide or execute",
                    "responsibility_domain": "bounded domain of competence",
                    "context_scope": "short context visibility scope",
                    "context_include": ["allowed context slice"],
                    "context_exclude": ["forbidden context slice"],
                    "tolerance_boundary": "delegated tolerance boundary",
                    "validation_condition": "how the node proves its work/decision",
                    "open_questions": ["review question"],
                }
            ],
        },
        "project_design_packet": design,
        "local_proposal": local_report,
    }
    return dumps_ascii(packet)


def _merge_ai_project_tree_proposal(agent: Agent, config: AgentConfig, local_report: dict[str, object]) -> dict[str, object]:
    report = copy.deepcopy(local_report)
    design = _project_design_flow._project_design_report(agent, config)
    prompt = _project_tree_ai_prompt(design, local_report)
    _model_views._apply_model_preferences(agent, config)
    handoff = ProjectHandoff.load(config.handoff_path)
    tolerance_profile = _project_role_flow._project_tolerance_profile(handoff, task=handoff.task or None)
    prefs = _model_views._load_model_preferences(config)
    model = _model_views._choose_cloud_priority_model(agent, prefs)
    account = prefs.account_for_model(model)
    result = agent.handoff.execute(format_run_model(model, prompt, account=account))
    assistance: dict[str, object] = {
        "attempted": True,
        "ok": False,
        "model": model,
        "account": account or None,
        "message": "",
        "valid_added_nodes": [],
        "rejected_nodes": [],
    }
    if not result.ok:
        assistance["message"] = result.error or "AI proposal model call failed; using local proposal only."
        report["ai_assistance"] = assistance
        report["source"] = "local_rules_ai_failed"
        return report
    try:
        payload = loads_text(result.output)
    except ValueError as exc:
        assistance["message"] = f"AI proposal output was not valid JSON: {exc}"
        report["ai_assistance"] = assistance
        report["source"] = "local_rules_ai_invalid"
        return report
    if not isinstance(payload, dict):
        assistance["message"] = "AI proposal output must be a JSON object."
        report["ai_assistance"] = assistance
        report["source"] = "local_rules_ai_invalid"
        return report

    prefs = _model_views._load_model_preferences(config)
    proposed_roles = prefs.propose_prince2_roles()
    merged_roles = dict(proposed_roles)
    merged_roles.update(prefs.prince2_roles or {})
    proposal_prefs = replace(prefs, prince2_roles=merged_roles)
    active_models = list(proposal_prefs.active_models() or proposal_prefs.enabled_models)
    tree = report["tree"] if isinstance(report.get("tree"), dict) else {}
    nodes = [dict(node) for node in tree.get("nodes", []) if isinstance(node, dict)]
    existing = {str(node.get("node_id", "")) for node in nodes}
    patches = payload.get("tree_patches", payload.get("nodes", []))
    if not isinstance(patches, list):
        patches = []
    rejected: list[dict[str, str]] = []
    added: list[str] = []
    for raw_patch in patches:
        if not isinstance(raw_patch, dict):
            rejected.append({"node_id": "unknown", "reason": "patch is not an object"})
            continue
        node_id = str(raw_patch.get("node_id", "")).strip().lower()
        role_type = str(raw_patch.get("role_type", "")).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,80}", node_id):
            rejected.append({"node_id": node_id or "unknown", "reason": "invalid node_id"})
            continue
        if node_id in existing:
            rejected.append({"node_id": node_id, "reason": "duplicate node_id"})
            continue
        if role_type not in PRINCE2_ROLE_IDS:
            rejected.append({"node_id": node_id, "reason": "unsupported role_type"})
            continue
        parent_id = str(raw_patch.get("parent_id") or "management.project_manager").strip()
        node = _project_flow._role_node_from_template(
            node_id=node_id,
            role_type=role_type,
            label=str(raw_patch.get("label") or PRINCE2_ROLE_LABELS.get(role_type, role_type)).strip(),
            parent_id=parent_id,
            level=str(raw_patch.get("level") or "delegated").strip(),
            accountability_boundary=str(raw_patch.get("accountability_boundary") or "delegated PRINCE2 accountability within agreed tolerances").strip(),
            delegated_authority=str(raw_patch.get("delegated_authority") or "executes delegated work and escalates tolerance breaches").strip(),
            assignment=_project_flow._assignment_for_role(proposal_prefs, role_type),
            active_models=active_models,
            tolerance_profile=tolerance_profile,
            accountable_owner=tolerance_profile.accountable_owner,
        )
        context_include = raw_patch.get("context_include")
        context_exclude = raw_patch.get("context_exclude")
        if isinstance(context_include, list) or isinstance(context_exclude, list):
            base_rule = node.get("context_rule") if isinstance(node.get("context_rule"), dict) else {}
            node["context_rule"] = {
                "include": [str(item) for item in context_include] if isinstance(context_include, list) else list(base_rule.get("include", [])),
                "exclude": [str(item) for item in context_exclude] if isinstance(context_exclude, list) else list(base_rule.get("exclude", [])),
                "expansion_events": list(base_rule.get("expansion_events", [])),
            }
        for optional_key in ("responsibility_domain", "context_scope", "tolerance_boundary", "validation_condition"):
            value = str(raw_patch.get(optional_key, "")).strip()
            if value:
                node[optional_key] = value
        open_questions = raw_patch.get("open_questions")
        if isinstance(open_questions, list):
            node["open_questions"] = [str(item) for item in open_questions if str(item).strip()]
        nodes.append(node)
        existing.add(node_id)
        added.append(node_id)

    tree["nodes"] = nodes
    tree["source"] = "project_brief_local_rules_plus_ai"
    report["tree"] = tree
    report["source"] = "local_rules_plus_ai" if added else "local_rules_ai_no_changes"
    decomposition = dict(report.get("decomposition", {})) if isinstance(report.get("decomposition"), dict) else {}
    adaptation = dict(report.get("adaptation", {})) if isinstance(report.get("adaptation"), dict) else {}
    refresh_reason = str(payload.get("refresh_reason", "")).strip()
    if refresh_reason:
        adaptation["ai_refresh_reason"] = refresh_reason
    if adaptation:
        tree["adaptation"] = adaptation
        report["adaptation"] = adaptation
    if decomposition:
        tree["decomposition"] = decomposition
        report["decomposition"] = decomposition
    report["check"] = check_prince2_role_tree_payload(tree, proposal_prefs)
    report["matrix"] = build_prince2_role_matrix_payload(tree, proposal_prefs)
    report["added_nodes"] = list(dict.fromkeys([*report.get("added_nodes", []), *added]))
    assumptions = list(report.get("assumptions", [])) if isinstance(report.get("assumptions"), list) else []
    summary = str(payload.get("summary", "")).strip()
    if summary:
        assumptions.append(f"AI tree designer: {summary}")
    ai_assumptions = payload.get("assumptions", [])
    if isinstance(ai_assumptions, list):
        assumptions.extend(str(item).strip() for item in ai_assumptions if str(item).strip())
    report["assumptions"] = assumptions
    assistance["ok"] = True
    assistance["message"] = "AI proposal merged into review-only project tree." if added else "AI proposal returned no valid new nodes; using local proposal."
    assistance["valid_added_nodes"] = added
    assistance["rejected_nodes"] = rejected
    report["ai_assistance"] = assistance
    return report


def _render_project_tree_proposal_report(report: dict[str, object]) -> str:
    check = report["check"] if isinstance(report.get("check"), dict) else {}
    summary = check.get("summary", {}) if isinstance(check.get("summary"), dict) else {}
    lines = [
        "Project tree proposal:",
        f"- status: {report['status']}",
        f"- source: {report['source']}",
        f"- ai_requested: {str(bool(report.get('ai_requested'))).lower()}",
        f"- nodes: {summary.get('nodes', 0)} assigned={summary.get('assigned', 0)} unassigned={summary.get('unassigned', 0)}",
        f"- added_nodes: {', '.join(report['added_nodes']) or 'none'}",
        f"- approval_rule: {report['approval_rule']}",
        "AI assistance:",
    ]
    ai_assistance = report.get("ai_assistance") if isinstance(report.get("ai_assistance"), dict) else {}
    if ai_assistance:
        added = ai_assistance.get("valid_added_nodes", [])
        rejected = ai_assistance.get("rejected_nodes", [])
        lines.append(
            f"- attempted: {str(bool(ai_assistance.get('attempted'))).lower()} "
            f"ok={ai_assistance.get('ok')} model={ai_assistance.get('model') or 'none'} "
            f"account={ai_assistance.get('account') or 'none'}"
        )
        lines.append(f"- message: {ai_assistance.get('message') or 'none'}")
        lines.append(f"- valid_added_nodes: {', '.join(added) if isinstance(added, list) and added else 'none'}")
        lines.append(f"- rejected_nodes: {len(rejected) if isinstance(rejected, list) else 0}")
    else:
        lines.append("- none")
    local_execution = report.get("local_execution") if isinstance(report.get("local_execution"), dict) else {}
    lines.append("Local execution candidates:")
    if local_execution:
        ai = local_execution.get("ai_analysis", {}) if isinstance(local_execution.get("ai_analysis"), dict) else {}
        lines.append(
            f"- source: {local_execution.get('catalog_source', 'unknown')} "
            f"ai_attempted={str(bool(ai.get('attempted'))).lower()} ai_ok={ai.get('ok')}"
        )
        if local_execution.get("message"):
            lines.append(f"- recommendation: {local_execution.get('message')}")
        candidates = [item for item in local_execution.get("candidates", []) if isinstance(item, dict)]
        if candidates:
            for item in candidates:
                lines.append(
                    f"- {item.get('id')}: fit={item.get('agentic_fit')} risk={item.get('tool_support_risk')} "
                    f"best_for={', '.join(str(entry) for entry in item.get('best_for', [])) or 'none'}"
                )
        else:
            lines.append("- none")
    else:
        lines.append("- none")
    decomposition = report.get("decomposition") if isinstance(report.get("decomposition"), dict) else {}
    adaptation = report.get("adaptation") if isinstance(report.get("adaptation"), dict) else {}
    lines.append("Decomposition:")
    if decomposition:
        lines.append(f"- policy: {decomposition.get('policy') or 'none'}")
        lines.append(f"- complexity: {decomposition.get('status') or 'unknown'} score={decomposition.get('score', 0)}")
        lines.append(f"- micro_task_count: {decomposition.get('micro_task_count', 0)}")
        micro_tasks = [item for item in decomposition.get("micro_tasks", []) if isinstance(item, dict)]
        if micro_tasks:
            for item in micro_tasks:
                lines.append(
                    f"- {item.get('node_id')}: role={item.get('role_type')} label={item.get('label')} reason={item.get('reason')}"
                )
        else:
            lines.append("- micro_tasks: none")
    else:
        lines.append("- none")
    lines.append("Adaptation:")
    if adaptation:
        lines.append(f"- policy: {adaptation.get('policy') or 'none'}")
        lines.append(f"- status: {adaptation.get('status') or 'unknown'}")
        lines.append(f"- reason: {adaptation.get('reason') or 'none'}")
        changed = adaptation.get("changed_fields", [])
        lines.append(f"- changed_fields: {', '.join(changed) if isinstance(changed, list) and changed else 'none'}")
        lines.append(f"- latest_observation: {adaptation.get('latest_observation') or 'none'}")
        lines.append(f"- plan_status: {adaptation.get('plan_status') or 'none'}")
        lines.append(f"- baseline_source: {adaptation.get('baseline_source') or 'none'}")
    else:
        lines.append("- none")
    lines.append("Assumptions:")
    assumptions = report["assumptions"]
    if isinstance(assumptions, list) and assumptions:
        for item in assumptions:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("Clarification gaps:")
    gaps = report["clarification_gaps"]
    if isinstance(gaps, list) and gaps:
        for item in gaps:
            if isinstance(item, dict):
                lines.append(f"- {item.get('code')}: {item.get('message')}")
    else:
        lines.append("- none")
    next_missing_field = report.get("next_missing_field")
    if next_missing_field:
        lines.append(f"Next missing project brief field: {next_missing_field}")
    next_missing_gap = report.get("next_missing_gap")
    if isinstance(next_missing_gap, dict) and next_missing_gap.get("code"):
        lines.append(f"- next_missing_gap: {next_missing_gap.get('code')}")
    clarification_question = report.get("clarification_question")
    if isinstance(clarification_question, dict) and clarification_question.get("question"):
        lines.append("Clarification question:")
        lines.append(f"- question: {clarification_question.get('question')}")
        lines.append("- answer: update the brief then rerun /project tree propose --ai")
    lines.append("Node preview:")
    tree = report["tree"] if isinstance(report.get("tree"), dict) else {}
    for node in tree.get("nodes", []) if isinstance(tree.get("nodes"), list) else []:
        if not isinstance(node, dict):
            continue
        marker = "added" if node.get("node_id") in report["added_nodes"] else "base"
        assignment = node.get("assignment") if isinstance(node.get("assignment"), dict) else {}
        lines.append(
            f"- [{marker}] {node.get('node_id')} role={node.get('role_type')} "
            f"parent={node.get('parent_id') or 'none'} provider={assignment.get('provider') or 'none'} "
            f"provider_model={assignment.get('provider_model') or 'none'}"
        )
    return "\n".join(lines)


def _record_project_tree_proposal_action(config: AgentConfig, report: dict[str, object], *, task: str) -> None:
    _project_handoff_views._record_handoff_action(
        config,
        phase="project_tree_proposal_ai" if report.get("ai_requested") else "project_tree_proposal",
        summary="Project tree proposal generated for review; no baseline persisted.",
        task=task,
        details={
            "status": report.get("status"),
            "source": report.get("source"),
            "ai_requested": report.get("ai_requested"),
            "ai_assistance": report.get("ai_assistance"),
            "added_nodes": report.get("added_nodes", []),
            "decomposition": report.get("decomposition", {}),
            "adaptation": report.get("adaptation", {}),
            "clarification_gaps": report.get("clarification_gaps", []),
            "node_count": len(report.get("tree", {}).get("nodes", [])) if isinstance(report.get("tree"), dict) else 0,
        },
    )


def _approve_project_tree_proposal(
    config: AgentConfig,
    *,
    force: bool = False,
    proposal_report: dict[str, object] | None = None,
) -> dict[str, object]:
    report = proposal_report or _project_tree_proposal_report(config)
    gaps = report.get("clarification_gaps", [])
    if isinstance(gaps, list) and gaps and not force:
        _project_handoff_views._record_handoff_action(
            config,
            phase="project_tree_approval_blocked",
            summary="Project tree approval blocked by unresolved clarification gaps.",
            task="project tree approve",
            details={
                "clarification_gaps": gaps,
                "proposal_status": report.get("status"),
                "added_nodes": report.get("added_nodes", []),
            },
        )
        return {
            "command": "project tree approve",
            "status": "blocked",
            "message": "Project tree proposal has clarification gaps; resolve them or rerun with --force.",
            "clarification_gaps": gaps,
            "proposal": report,
        }
    prefs = _model_views._load_model_preferences(config)
    merged_roles = dict(prefs.propose_prince2_roles())
    merged_roles.update(prefs.prince2_roles or {})
    proposal_prefs = replace(prefs, prince2_roles=merged_roles)
    baseline = {
        "version": "1",
        "approved_at": datetime.now().isoformat(timespec="seconds"),
        "source": "project_tree_approve_force" if force else "project_tree_approve",
        "status": "approved",
        "tree": _project_flow._enrich_tree_with_local_execution_candidates(
            dict(report["tree"]) if isinstance(report.get("tree"), dict) else {},
            dict(report.get("local_execution", {})) if isinstance(report.get("local_execution"), dict) else {},
        ),
        "flow": build_prince2_role_flow(),
        "check": {},
        "matrix": {},
        "local_execution": dict(report.get("local_execution", {})) if isinstance(report.get("local_execution"), dict) else {},
        "proposal": {
            "source": report["source"],
            "assumptions": list(report.get("assumptions", [])) if isinstance(report.get("assumptions"), list) else [],
            "added_nodes": list(report.get("added_nodes", [])) if isinstance(report.get("added_nodes"), list) else [],
            "clarification_gaps": list(gaps) if isinstance(gaps, list) else [],
            "project_brief": dict(report.get("project_brief", {})) if isinstance(report.get("project_brief"), dict) else {},
            "ai_requested": bool(report.get("ai_requested")),
            "ai_assistance": dict(report.get("ai_assistance", {})) if isinstance(report.get("ai_assistance"), dict) else {},
            "forced": force,
        },
    }
    _project_role_flow._refresh_prince2_role_tree_baseline_checks(baseline, proposal_prefs)
    _project_role_flow._persist_prince2_role_tree_baseline(config, proposal_prefs, baseline)
    _project_handoff_views._record_handoff_action(
        config,
        phase="project_tree_approval",
        summary="Project tree proposal approved and persisted as PRINCE2 role-tree baseline.",
        task="project tree approve --force" if force else "project tree approve",
        details={
            "forced": force,
            "source": baseline["source"],
            "added_nodes": baseline["proposal"]["added_nodes"],
            "clarification_gaps": baseline["proposal"]["clarification_gaps"],
            "node_count": len(report.get("tree", {}).get("nodes", [])) if isinstance(report.get("tree"), dict) else 0,
        },
    )
    return {
        "command": "project tree approve",
        "status": "approved",
        "forced": force,
        "message": "Approved project-tree proposal as PRINCE2 role-tree baseline.",
        "baseline": _project_role_tree_views._prince2_role_tree_baseline_report(config),
    }


def _render_project_tree_approval_report(report: dict[str, object], config: AgentConfig) -> str:
    lines = ["Project tree approval:"]
    lines.append(f"- status: {report['status']}")
    lines.append(f"- message: {report['message']}")
    if report["status"] == "blocked":
        lines.append("Clarification gaps:")
        gaps = report.get("clarification_gaps", [])
        if isinstance(gaps, list) and gaps:
            for item in gaps:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('code')}: {item.get('message')}")
        lines.append("- action: resolve missing project brief fields or rerun /project tree approve --force")
        return "\n".join(lines)
    lines.append(f"- forced: {str(bool(report.get('forced'))).lower()}")
    baseline = report.get("baseline") if isinstance(report.get("baseline"), dict) else {}
    lines.append(f"- baseline_status: {baseline.get('status', 'unknown')}")
    if isinstance(baseline.get("baseline"), dict):
        proposal = baseline["baseline"].get("proposal", {})
        added = proposal.get("added_nodes", []) if isinstance(proposal, dict) else []
        lines.append(f"- added_nodes: {', '.join(added) if isinstance(added, list) and added else 'none'}")
    return "\n".join(lines) + "\n" + _project_role_tree_views._render_prince2_role_tree_baseline(config)


def _render_project_tree_approval(config: AgentConfig, *, force: bool = False) -> str:
    return _render_project_tree_approval_report(_approve_project_tree_proposal(config, force=force), config)
