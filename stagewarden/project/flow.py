from __future__ import annotations

from ..config import AgentConfig
from ..modelprefs import ModelPreferences
from ..prince2 import Prince2ToleranceProfile
from ..project_handoff import ProjectHandoff
from .brief import (
    handle_project_brief_command,
    project_brief_report,
    project_gap_to_brief_field,
    render_project_brief,
)
from .tree import (
    assignment_for_role,
    enrich_tree_with_local_execution_candidates,
    project_tree_adaptation_snapshot,
    project_tree_decomposition_nodes,
    role_node_from_template,
)


def _project_gap_to_brief_field(gap_code: str) -> str | None:
    return project_gap_to_brief_field(gap_code)


def _project_brief_report(config: AgentConfig) -> dict[str, object]:
    return project_brief_report(config)


def _render_project_brief(config: AgentConfig) -> str:
    return render_project_brief(config)


def _handle_project_brief_command(command: str, config: AgentConfig) -> str | None:
    return handle_project_brief_command(command, config)


def _assignment_for_role(prefs: ModelPreferences, role: str) -> dict[str, object]:
    return assignment_for_role(prefs, role)


def _role_node_from_template(
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
    tolerance_profile: Prince2ToleranceProfile | None = None,
    accountable_owner: str = "user",
) -> dict[str, object]:
    assert tolerance_profile is not None
    return role_node_from_template(
        node_id=node_id,
        role_type=role_type,
        label=label,
        parent_id=parent_id,
        level=level,
        accountability_boundary=accountability_boundary,
        delegated_authority=delegated_authority,
        assignment=assignment,
        active_models=active_models,
        tolerance_profile=tolerance_profile,
        accountable_owner=accountable_owner,
    )


def _project_tree_adaptation_snapshot(
    *,
    brief: dict[str, str],
    handoff: ProjectHandoff,
    local_execution: dict[str, object],
) -> dict[str, object]:
    return project_tree_adaptation_snapshot(brief=brief, handoff=handoff, local_execution=local_execution)


def _project_tree_decomposition_nodes(
    *,
    proposal_prefs: ModelPreferences,
    active_models: list[str],
    brief: dict[str, str],
    joined: str,
    tolerance_profile: Prince2ToleranceProfile,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    return project_tree_decomposition_nodes(
        proposal_prefs=proposal_prefs,
        active_models=active_models,
        brief=brief,
        joined=joined,
        tolerance_profile=tolerance_profile,
    )


def _enrich_tree_with_local_execution_candidates(
    tree: dict[str, object],
    local_execution: dict[str, object],
) -> dict[str, object]:
    return enrich_tree_with_local_execution_candidates(tree, local_execution)
