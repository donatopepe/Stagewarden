from __future__ import annotations

from ..modelprefs import PRINCE2_ROLE_LABELS
from ..prince2 import Prince2ToleranceProfile
from ..project_handoff import ProjectHandoff
from ..role_tree import (
    ROLE_CONTEXT_RULES,
    build_prince2_role_matrix_payload,
    build_prince2_role_tree_with_tolerance,
    check_prince2_role_tree_payload,
    prince2_role_mnemonic,
    prince2_role_team_name,
)
from ..roles import PRINCE2_ROLE_AUTOMATION_RULES, PRINCE2_ROLE_SCOPE_DESCRIPTIONS


def assignment_for_role(prefs: ModelPreferences, role: str) -> dict[str, object]:
    proposal = prefs.propose_prince2_roles()
    assignment = dict((prefs.prince2_roles or {}).get(role) or proposal.get(role, {}))
    if not assignment:
        return {}
    assignment.setdefault("role", role)
    assignment.setdefault("label", PRINCE2_ROLE_LABELS.get(role, role))
    assignment.setdefault("mode", "auto")
    assignment.setdefault("source", "project_tree_proposal")
    return assignment


def role_node_from_template(
    *,
    node_id: str,
    role_type: str,
    label: str,
    parent_id: str | None,
    level: str,
    accountability_boundary: str,
    delegated_authority: str,
    assignment: dict[str, object],
    active_models: list[str],
    tolerance_profile: Prince2ToleranceProfile,
    accountable_owner: str = "user",
) -> dict[str, object]:
    provider = str(assignment.get("provider", "")) if assignment else ""
    node_tolerance = tolerance_profile.node_profile(role_type)
    return {
        "node_id": node_id,
        "mnemonic": prince2_role_mnemonic(role_type),
        "role_type": role_type,
        "team_name": prince2_role_team_name(role_type),
        "label": label,
        "parent_id": parent_id,
        "level": level,
        "accountability_boundary": accountability_boundary,
        "delegated_authority": delegated_authority,
        "responsibility_domain": PRINCE2_ROLE_AUTOMATION_RULES.get(role_type, "controlled project work"),
        "context_scope": PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role_type, "controlled project work"),
        "context_rule": ROLE_CONTEXT_RULES[role_type].as_dict(),
        "accountable_owner": str(node_tolerance.get("accountable_owner", accountable_owner)),
        "tolerance_margin_percent": float(node_tolerance.get("margin_percent", tolerance_profile.project_margin_percent)),
        "tolerance_pressure_percent": float(node_tolerance.get("pressure_percent", tolerance_profile.project_pressure_percent)),
        "autonomy_rule": str(node_tolerance.get("autonomy_rule", "")),
        "escalation_target": str(node_tolerance.get("escalation_target", "board.executive")),
        "tolerance_profile": dict(node_tolerance),
        "assignment": assignment,
        "fallback_pool": [item for item in active_models if item != provider],
        "readiness": "assigned" if assignment else "unassigned",
    }


def project_tree_brief_complexity(brief: dict[str, str], joined: str) -> dict[str, object]:
    keywords = {
        "risk": ("risk", "security", "production", "prod", "migration", "vendor", "supplier", "legal", "regulatory", "incident", "outage", "breach"),
        "validation": ("test", "tests", "validate", "validation", "wet-run", "review", "verify", "check"),
        "delivery": ("release", "rollback", "deploy", "deployment", "ship", "launch", "rollout"),
        "change": ("change", "refactor", "rebaseline", "update", "patch", "fix"),
    }
    score = 0
    if len(brief) >= 3:
        score += 1
    if len(joined.split()) >= 14:
        score += 1
    if brief.get("delivery_mode", "").lower() in {"hybrid", "iterative", "agile", "continuous"}:
        score += 1
    for group in keywords.values():
        if any(token in joined for token in group):
            score += 1
    if len(joined.split()) >= 30:
        score += 1
    if score <= 1:
        label = "minimal"
    elif score <= 3:
        label = "bounded"
    elif score <= 5:
        label = "multi_lane"
    else:
        label = "crisis"
    return {"score": score, "label": label}


def project_tree_adaptation_snapshot(
    *,
    brief: dict[str, str],
    handoff: ProjectHandoff,
    local_execution: dict[str, object],
) -> dict[str, object]:
    baseline = handoff.prince2_role_tree_baseline if isinstance(handoff.prince2_role_tree_baseline, dict) else {}
    proposal = baseline.get("proposal", {}) if isinstance(baseline.get("proposal", {}), dict) else {}
    previous_brief = proposal.get("project_brief", {}) if isinstance(proposal.get("project_brief", {}), dict) else {}
    changed_fields = sorted(
        {
            key
            for key in set(brief) | set(previous_brief)
            if str(brief.get(key, "")).strip() != str(previous_brief.get(key, "")).strip()
        }
    )
    if not baseline:
        status = "initial"
        reason = "no approved baseline exists yet"
    elif changed_fields:
        status = "refreshed"
        reason = "project brief or execution context changed"
    else:
        status = "steady"
        reason = "baseline still matches the current brief"
    return {
        "status": status,
        "reason": reason,
        "baseline_source": str(baseline.get("source", "none")) if baseline else "none",
        "baseline_approved_at": str(baseline.get("approved_at", "")) if baseline else "",
        "changed_fields": changed_fields,
        "latest_observation": str(handoff.latest_observation or "").strip()[:240],
        "plan_status": str(handoff.plan_status or "").strip()[:120],
        "goal_status": str(handoff.goal_view().get("status", "unknown")),
        "local_execution_model": str((local_execution.get("ai_analysis") or {}).get("model", "")) if isinstance(local_execution.get("ai_analysis"), dict) else "",
        "local_execution_candidates": [
            str(item.get("id", ""))
            for item in local_execution.get("candidates", [])
            if isinstance(item, dict) and str(item.get("id", "")).strip()
        ],
    }


def project_tree_decomposition_nodes(
    *,
    proposal_prefs: ModelPreferences,
    active_models: list[str],
    brief: dict[str, str],
    joined: str,
    tolerance_profile: Prince2ToleranceProfile,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    complexity = project_tree_brief_complexity(brief, joined)
    score = int(complexity["score"])
    nodes: list[dict[str, object]] = []
    micro_tasks: list[dict[str, str]] = []

    def add_node(
        *,
        node_id: str,
        role_type: str,
        label: str,
        parent_id: str,
        level: str,
        accountability_boundary: str,
        delegated_authority: str,
        reason: str,
    ) -> None:
        nodes.append(
            role_node_from_template(
                node_id=node_id,
                role_type=role_type,
                label=label,
                parent_id=parent_id,
                level=level,
                accountability_boundary=accountability_boundary,
                delegated_authority=delegated_authority,
                assignment=assignment_for_role(proposal_prefs, role_type),
                active_models=active_models,
                tolerance_profile=tolerance_profile,
                accountable_owner=tolerance_profile.accountable_owner,
            )
        )
        nodes[-1]["decomposition_reason"] = reason
        nodes[-1]["refresh_policy"] = "recompute when brief, tolerance, or response quality changes"
        micro_tasks.append(
            {
                "node_id": node_id,
                "role_type": role_type,
                "label": label,
                "reason": reason,
            }
        )

    add_node(
        node_id="management.work_package_breakdown",
        role_type="project_manager",
        label="Work Package Breakdown",
        parent_id="management.project_manager",
        level="management",
        accountability_boundary="decompose the brief into the smallest controllable work packages and keep them independently reviewable",
        delegated_authority="splits work into atomic tasks and reslices them whenever evidence changes",
        reason="Every project tree should start by slicing the work into the smallest executable packages.",
    )
    add_node(
        node_id="support.evidence_keeper",
        role_type="project_support",
        label="Evidence Keeper",
        parent_id="management.project_manager",
        level="support",
        accountability_boundary="keep the minimum evidence needed to validate each micro-task and refresh the tree when traces change",
        delegated_authority="maintains traceability, evidence, and updated task snapshots",
        reason="Continuous adaptation needs a live evidence node so the tree can refresh from actual execution.",
    )
    if score >= 2:
        add_node(
            node_id="assurance.validation_assurance",
            role_type="project_assurance",
            label="Validation Assurance",
            parent_id="board.executive",
            level="assurance",
            accountability_boundary="independent validation of the smallest deliverable before broader work continues",
            delegated_authority="confirms evidence, checks closure, and rejects weak completions",
            reason="Complex work needs an assurance lane that keeps validation separate from delivery.",
        )
    if score >= 3:
        add_node(
            node_id="authority.change_control_lane",
            role_type="change_authority",
            label="Change Control Lane",
            parent_id="board.executive",
            level="delegated_authority",
            accountability_boundary="approve or reject bounded changes and refinements before the tree widens",
            delegated_authority="authorizes delegated changes and re-baselines within tolerance",
            reason="Change-heavy work needs a narrow control lane to avoid broad, static plans.",
        )
    if score >= 4 or any(token in joined for token in ("rollback", "recovery", "release", "deploy", "rollout", "outage", "breach")):
        add_node(
            node_id="delivery.rollback_lane",
            role_type="team_manager",
            label="Rollback Lane",
            parent_id="management.project_manager",
            level="delivery",
            accountability_boundary="keep the rollback and recovery path as small and explicit as the forward path",
            delegated_authority="executes reversible steps and escalates if rollback evidence is weak",
            reason="Recovery-sensitive work needs a dedicated rollback path that can be refreshed continuously.",
        )
    if score >= 5 or any(token in joined for token in ("user", "browser", "login", "ux", "interactive", "adoption")):
        add_node(
            node_id="board.user_acceptance",
            role_type="senior_user",
            label="User Acceptance Delegate",
            parent_id="board.senior_user",
            level="direction",
            accountability_boundary="keep user acceptance focused on the minimum acceptance evidence needed to continue",
            delegated_authority="reviews user-facing evidence and escalates adoption issues",
            reason="User-facing work still benefits from a narrow acceptance lane that can be updated continuously.",
        )
    adaptation = {
        "policy": "Recompute the tree on every proposal and stage boundary from the latest brief, tolerance profile, runtime observation, and response quality.",
        "status": complexity["label"],
        "score": score,
        "micro_task_count": len(micro_tasks),
        "micro_tasks": micro_tasks,
    }
    return nodes, adaptation


def route_from_local_execution_candidate(candidate: dict[str, object], *, node: dict[str, object]) -> dict[str, object] | None:
    provider_model = str(candidate.get("id", "")).strip()
    if not provider_model:
        return None
    params: dict[str, str] = {}
    reasoning_default = str(candidate.get("reasoning_default", "")).strip()
    if reasoning_default:
        params["reasoning_effort"] = reasoning_default
    return {
        "role": str(node.get("role_type", "")),
        "node_id": str(node.get("node_id", "")),
        "label": str(node.get("label", node.get("node_id", ""))),
        "mode": "auto",
        "provider": "local",
        "provider_model": provider_model,
        "params": params,
        "account": None,
        "source": "auto_local_execution_candidate",
        "pool": "fallback",
    }


def enrich_tree_with_local_execution_candidates(
    tree: dict[str, object],
    local_execution: dict[str, object],
) -> dict[str, object]:
    nodes = [dict(node) for node in tree.get("nodes", []) if isinstance(node, dict)]
    candidates = [item for item in local_execution.get("candidates", []) if isinstance(item, dict)]
    candidate_ids = [str(item.get("id", "")).strip() for item in candidates if str(item.get("id", "")).strip()]
    for node in nodes:
        if not str(node.get("level", "")).startswith("delivery"):
            continue
        node["local_execution_candidates"] = list(candidate_ids)
        if not candidates:
            continue
        pools = node.get("assignment_pool", {}) if isinstance(node.get("assignment_pool"), dict) else {}
        routes = [dict(item) for item in pools.get("fallback", []) if isinstance(item, dict)] if isinstance(pools.get("fallback", []), list) else []
        assignment = node.get("assignment") if isinstance(node.get("assignment"), dict) else {}
        assignment_provider = str(assignment.get("provider", "")).strip()
        assignment_model = str(assignment.get("provider_model", "")).strip()
        existing = {
            (str(item.get("provider", "")).strip(), str(item.get("provider_model", "")).strip(), str(item.get("account", "")).strip())
            for item in routes
        }
        for candidate in candidates:
            route = route_from_local_execution_candidate(candidate, node=node)
            if route is None:
                continue
            signature = (
                str(route.get("provider", "")).strip(),
                str(route.get("provider_model", "")).strip(),
                str(route.get("account", "")).strip(),
            )
            if assignment_provider == "local" and assignment_model == signature[1]:
                continue
            if signature in existing:
                continue
            routes.append(route)
            existing.add(signature)
        if routes:
            pools["fallback"] = routes
            node["assignment_pool"] = pools
    enriched = dict(tree)
    enriched["nodes"] = nodes
    return enriched
