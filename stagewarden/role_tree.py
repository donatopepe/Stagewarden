from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .modelprefs import PRINCE2_ROLE_LABELS, ModelPreferences, account_key
from .roles import PRINCE2_ROLE_AUTOMATION_RULES, PRINCE2_ROLE_SCOPE_DESCRIPTIONS


@dataclass(frozen=True)
class RoleContextRule:
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    expansion_events: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "include": list(self.include),
            "exclude": list(self.exclude),
            "expansion_events": list(self.expansion_events),
        }


@dataclass(frozen=True)
class RoleTreeNode:
    node_id: str
    role_type: str
    label: str
    parent_id: str | None
    level: str
    accountability_boundary: str
    delegated_authority: str
    responsibility_domain: str
    context_scope: str
    context_rule: RoleContextRule
    assignment: dict[str, object] = field(default_factory=dict)
    fallback_pool: tuple[str, ...] = ()
    readiness: str = "unassigned"

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["context_rule"] = self.context_rule.as_dict()
        payload["fallback_pool"] = list(self.fallback_pool)
        return payload


ROLE_TREE_LAYOUT: tuple[dict[str, str | None], ...] = (
    {
        "node_id": "board.executive",
        "role_type": "project_executive",
        "parent_id": None,
        "level": "direction",
        "accountability_boundary": "single point of business accountability and stop/go authority",
        "delegated_authority": "may delegate operational responsibility but not accountability",
    },
    {
        "node_id": "board.senior_user",
        "role_type": "senior_user",
        "parent_id": "board.executive",
        "level": "direction",
        "accountability_boundary": "user value, adoption, acceptance, and benefits realization",
        "delegated_authority": "may delegate user representation without losing benefit ownership",
    },
    {
        "node_id": "board.senior_supplier",
        "role_type": "senior_supplier",
        "parent_id": "board.executive",
        "level": "direction",
        "accountability_boundary": "supplier capability, technical feasibility, and specialist integrity",
        "delegated_authority": "may delegate specialist delivery authority to team managers",
    },
    {
        "node_id": "management.project_manager",
        "role_type": "project_manager",
        "parent_id": "board.executive",
        "level": "management",
        "accountability_boundary": "day-to-day management within approved tolerances",
        "delegated_authority": "authorizes work packages and escalates forecast tolerance breaches",
    },
    {
        "node_id": "assurance.project_assurance",
        "role_type": "project_assurance",
        "parent_id": "board.executive",
        "level": "assurance",
        "accountability_boundary": "independent confidence that project controls and quality evidence are adequate",
        "delegated_authority": "reviews evidence independently; does not execute delivery work",
    },
    {
        "node_id": "authority.change_authority",
        "role_type": "change_authority",
        "parent_id": "board.executive",
        "level": "delegated_authority",
        "accountability_boundary": "change and exception decisions inside delegated tolerances",
        "delegated_authority": "may approve changes only within explicit delegated thresholds",
    },
    {
        "node_id": "support.project_support",
        "role_type": "project_support",
        "parent_id": "management.project_manager",
        "level": "support",
        "accountability_boundary": "records, logs, configuration, traceability, and administrative support",
        "delegated_authority": "maintains evidence; does not approve delivery or assurance decisions",
    },
    {
        "node_id": "delivery.team_manager",
        "role_type": "team_manager",
        "parent_id": "management.project_manager",
        "level": "delivery",
        "accountability_boundary": "delivery of assigned work package products within agreed tolerances",
        "delegated_authority": "plans and executes work package delivery; escalates forecast tolerance breaches",
    },
)


ROLE_CONTEXT_RULES: dict[str, RoleContextRule] = {
    "project_executive": RoleContextRule(
        include=("business_case", "benefits", "cost_tolerance", "risk_tolerance", "exceptions", "stage_boundary"),
        exclude=("specialist_delivery_detail", "implementation_transcript_noise"),
        expansion_events=("board_decision", "exception", "stage_boundary_review"),
    ),
    "senior_user": RoleContextRule(
        include=("acceptance_criteria", "quality_records", "benefits", "adoption_impact", "user_risks"),
        exclude=("supplier_internal_detail", "unrelated_cost_control"),
        expansion_events=("acceptance_review", "quality_exception", "benefit_review"),
    ),
    "senior_supplier": RoleContextRule(
        include=("technical_feasibility", "supplier_risks", "delivery_integrity", "quality_evidence"),
        exclude=("business_case_detail", "user_adoption_private_notes"),
        expansion_events=("supplier_exception", "quality_review", "stage_boundary_review"),
    ),
    "project_manager": RoleContextRule(
        include=("stage_plan", "work_packages", "registers", "progress", "tolerances", "latest_observations"),
        exclude=("board_private_decision_context", "supplier_internal_private_detail"),
        expansion_events=("escalation", "exception", "stage_boundary_review"),
    ),
    "project_assurance": RoleContextRule(
        include=("quality_evidence", "risk_controls", "issue_controls", "lessons", "closure_evidence"),
        exclude=("delivery_execution_commands", "unapproved_change_work"),
        expansion_events=("formal_assurance_review", "quality_exception", "closure_review"),
    ),
    "change_authority": RoleContextRule(
        include=("change_request", "impact_assessment", "exception_plan", "tolerances", "risks", "issues"),
        exclude=("unrelated_work_package_detail", "board_private_strategy"),
        expansion_events=("delegated_change_decision", "exception", "rebaseline_request"),
    ),
    "project_support": RoleContextRule(
        include=("handoff_records", "logs", "git_evidence", "register_entries", "configuration_items"),
        exclude=("approval_authority", "private_model_tokens", "unrelated_business_strategy"),
        expansion_events=("record_update", "audit_request", "configuration_review"),
    ),
    "team_manager": RoleContextRule(
        include=("assigned_work_package", "product_descriptions", "quality_criteria", "delivery_lessons", "team_risks"),
        exclude=("business_case_detail", "full_exception_plan", "unrelated_project_registers"),
        expansion_events=("work_package_escalation", "quality_failure", "delivery_checkpoint"),
    ),
}


def build_prince2_role_tree(prefs: ModelPreferences) -> dict[str, object]:
    active_models = tuple(prefs.active_models() or prefs.enabled_models)
    assignments = prefs.prince2_roles or {}
    nodes: list[dict[str, object]] = []
    for raw in ROLE_TREE_LAYOUT:
        role_type = str(raw["role_type"])
        assignment = dict(assignments.get(role_type, {}))
        nodes.append(
            RoleTreeNode(
                node_id=str(raw["node_id"]),
                role_type=role_type,
                label=PRINCE2_ROLE_LABELS[role_type],
                parent_id=str(raw["parent_id"]) if raw["parent_id"] is not None else None,
                level=str(raw["level"]),
                accountability_boundary=str(raw["accountability_boundary"]),
                delegated_authority=str(raw["delegated_authority"]),
                responsibility_domain=PRINCE2_ROLE_AUTOMATION_RULES.get(role_type, "controlled project work"),
                context_scope=PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role_type, "controlled project work"),
                context_rule=ROLE_CONTEXT_RULES[role_type],
                assignment=assignment,
                fallback_pool=tuple(model for model in active_models if model != assignment.get("provider")),
                readiness="assigned" if assignment else "unassigned",
            ).as_dict()
        )
    return {
        "command": "roles tree",
        "version": 1,
        "rule": "each PRINCE2 role node receives only its role-derived context; fallback routing must not widen context",
        "expansion_rule": "context expands only through escalation, exception, stage boundary, delegated change, assurance review, or board decision",
        "nodes": nodes,
    }


def check_prince2_role_tree(prefs: ModelPreferences) -> dict[str, object]:
    tree = build_prince2_role_tree(prefs)
    nodes = [node for node in tree.get("nodes", []) if isinstance(node, dict)]
    findings: list[dict[str, object]] = []

    def add(severity: str, code: str, node_id: str, message: str) -> None:
        findings.append(
            {
                "severity": severity,
                "code": code,
                "node_id": node_id,
                "message": message,
            }
        )

    for node in nodes:
        node_id = str(node.get("node_id"))
        role_type = str(node.get("role_type"))
        assignment = node.get("assignment") if isinstance(node.get("assignment"), dict) else {}
        if not assignment:
            add("error", "missing_assignment", node_id, f"{role_type} has no provider/model assignment.")
            continue
        provider = str(assignment.get("provider", ""))
        account = assignment.get("account")
        if provider and prefs.is_blocked(provider):
            add(
                "error",
                "provider_blocked",
                node_id,
                f"{role_type} provider {provider} is blocked until {(prefs.blocked_until_by_model or {}).get(provider)}.",
            )
        if account and prefs.is_account_blocked(provider, str(account)):
            add(
                "error",
                "account_blocked",
                node_id,
                f"{role_type} account {provider}:{account} is blocked until {(prefs.blocked_until_by_account or {}).get(account_key(provider, str(account)))}.",
            )
        if provider in {"chatgpt", "openai", "claude", "cheap"} and account is None and provider in (prefs.accounts_by_model or {}):
            add("warning", "account_not_selected", node_id, f"{role_type} provider {provider} has profiles but no active account on this node.")

    by_role = {str(node.get("role_type")): node for node in nodes}
    assurance = by_role.get("project_assurance", {})
    team_manager = by_role.get("team_manager", {})
    assurance_assignment = assurance.get("assignment") if isinstance(assurance.get("assignment"), dict) else {}
    team_assignment = team_manager.get("assignment") if isinstance(team_manager.get("assignment"), dict) else {}
    if assurance_assignment and team_assignment:
        if assurance_assignment.get("provider") == team_assignment.get("provider") and assurance_assignment.get("provider_model") == team_assignment.get("provider_model"):
            add(
                "warning",
                "assurance_delivery_same_model",
                str(assurance.get("node_id", "assurance.project_assurance")),
                "Project Assurance uses the same provider-model as Team Manager; independence may be weak.",
            )

    status = "ok"
    if any(item["severity"] == "error" for item in findings):
        status = "error"
    elif findings:
        status = "warning"

    return {
        "command": "roles check",
        "status": status,
        "rule": "role tree is ready only when required nodes are assigned, unblocked, and independence constraints are visible",
        "summary": {
            "nodes": len(nodes),
            "assigned": sum(1 for node in nodes if node.get("readiness") == "assigned"),
            "unassigned": sum(1 for node in nodes if node.get("readiness") != "assigned"),
            "errors": sum(1 for item in findings if item["severity"] == "error"),
            "warnings": sum(1 for item in findings if item["severity"] == "warning"),
        },
        "findings": findings,
        "tree": tree,
    }


def render_prince2_role_check(report: dict[str, object]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "PRINCE2 role tree check:",
        f"- status: {report.get('status')}",
        f"- nodes: {summary.get('nodes', 0)} assigned={summary.get('assigned', 0)} unassigned={summary.get('unassigned', 0)}",
        f"- findings: errors={summary.get('errors', 0)} warnings={summary.get('warnings', 0)}",
        f"- rule: {report.get('rule')}",
    ]
    findings = [item for item in report.get("findings", []) if isinstance(item, dict)]
    if findings:
        lines.append("Findings:")
        for item in findings:
            lines.append(
                f"- {item.get('severity')} {item.get('code')} [{item.get('node_id')}]: {item.get('message')}"
            )
    else:
        lines.append("Findings: none")
    return "\n".join(lines)


def render_prince2_role_tree(tree: dict[str, object]) -> str:
    nodes = [node for node in tree.get("nodes", []) if isinstance(node, dict)]
    children: dict[str | None, list[dict[str, object]]] = {}
    for node in nodes:
        parent_id = node.get("parent_id")
        children.setdefault(str(parent_id) if parent_id else None, []).append(node)

    lines = ["PRINCE2 role tree:", f"- rule: {tree.get('rule')}"]

    def append_node(node: dict[str, object], depth: int) -> None:
        indent = "  " * depth
        assignment = node.get("assignment") if isinstance(node.get("assignment"), dict) else {}
        provider = assignment.get("provider", "unassigned") if isinstance(assignment, dict) else "unassigned"
        provider_model = assignment.get("provider_model", "none") if isinstance(assignment, dict) else "none"
        lines.append(
            f"{indent}- {node.get('label')} [{node.get('node_id')}] "
            f"level={node.get('level')} readiness={node.get('readiness')} "
            f"provider={provider} provider_model={provider_model}"
        )
        lines.append(f"{indent}  context={node.get('context_scope')}")
        lines.append(f"{indent}  authority={node.get('delegated_authority')}")
        for child in children.get(str(node.get("node_id")), []):
            append_node(child, depth + 1)

    for root in children.get(None, []):
        append_node(root, 0)
    lines.append(f"- expansion_rule: {tree.get('expansion_rule')}")
    return "\n".join(lines)
