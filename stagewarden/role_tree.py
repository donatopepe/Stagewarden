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


@dataclass(frozen=True)
class RoleFlowEdge:
    edge_id: str
    trigger: str
    source_node: str
    target_node: str
    flow_type: str
    payload_scope: tuple[str, ...]
    decision_authority: str
    expected_evidence: tuple[str, ...]
    validation_condition: str
    tolerance_boundary: str
    return_path: str

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["payload_scope"] = list(self.payload_scope)
        payload["expected_evidence"] = list(self.expected_evidence)
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


ROLE_FLOW_EDGES: tuple[RoleFlowEdge, ...] = (
    RoleFlowEdge(
        edge_id="authorize.project",
        trigger="project_start_or_stage_authorization",
        source_node="board.executive",
        target_node="management.project_manager",
        flow_type="authorization",
        payload_scope=("business_justification", "approved_tolerances", "stage_objectives", "reporting_controls"),
        decision_authority="Project Executive / Project Board",
        expected_evidence=("approved_brief_or_pid", "business_case_viability", "tolerance_set"),
        validation_condition="Project Manager receives enough approved baseline context to plan/control the stage.",
        tolerance_boundary="board-approved project/stage tolerances",
        return_path="management.project_manager -> board.executive via highlight, exception, stage boundary, or closure report",
    ),
    RoleFlowEdge(
        edge_id="issue.work_package",
        trigger="work_package_authorization",
        source_node="management.project_manager",
        target_node="delivery.team_manager",
        flow_type="delegation",
        payload_scope=("assigned_work_package", "product_descriptions", "quality_criteria", "delivery_tolerances"),
        decision_authority="Project Manager",
        expected_evidence=("work_package_description", "quality_criteria", "checkpoint_frequency"),
        validation_condition="Team Manager receives only the work package context needed for delivery.",
        tolerance_boundary="work package tolerances",
        return_path="delivery.team_manager -> management.project_manager via checkpoint or completion notification",
    ),
    RoleFlowEdge(
        edge_id="record.project_evidence",
        trigger="baseline_register_or_log_update",
        source_node="management.project_manager",
        target_node="support.project_support",
        flow_type="record",
        payload_scope=("approved_baseline_delta", "register_entry", "git_evidence", "decision_record"),
        decision_authority="Project Manager for request; Project Support for record integrity",
        expected_evidence=("traceable_record", "timestamp", "source_reference"),
        validation_condition="Project Support records evidence without approving delivery or assurance decisions.",
        tolerance_boundary="configuration and record-control rules",
        return_path="support.project_support -> management.project_manager via record confirmation",
    ),
    RoleFlowEdge(
        edge_id="assure.quality_risk",
        trigger="formal_assurance_review",
        source_node="management.project_manager",
        target_node="assurance.project_assurance",
        flow_type="assurance",
        payload_scope=("quality_evidence", "risk_controls", "issue_controls", "lessons", "closure_evidence"),
        decision_authority="Project Assurance reports independently to Project Board",
        expected_evidence=("quality_records", "risk_issue_register_extract", "test_or_review_output"),
        validation_condition="Assurance review remains independent from delivery execution.",
        tolerance_boundary="assurance scope approved by Project Board",
        return_path="assurance.project_assurance -> board.executive and management.project_manager via assurance finding",
    ),
    RoleFlowEdge(
        edge_id="escalate.work_package_exception",
        trigger="forecast_work_package_tolerance_breach",
        source_node="delivery.team_manager",
        target_node="management.project_manager",
        flow_type="exception",
        payload_scope=("breach_forecast", "impact_on_work_package", "options", "recommended_action"),
        decision_authority="Project Manager within stage tolerances",
        expected_evidence=("checkpoint_report", "variance_evidence", "impact_assessment"),
        validation_condition="Project Manager can decide correction or escalate to delegated authority/Board.",
        tolerance_boundary="work package tolerances",
        return_path="management.project_manager -> delivery.team_manager via corrective action or revised work package",
    ),
    RoleFlowEdge(
        edge_id="escalate.stage_exception",
        trigger="forecast_stage_or_project_tolerance_breach",
        source_node="management.project_manager",
        target_node="authority.change_authority",
        flow_type="exception",
        payload_scope=("exception_report", "impact_assessment", "options", "risks", "issues", "rebaseline_need"),
        decision_authority="Change Authority only within delegated limits",
        expected_evidence=("exception_report", "updated_forecast", "recommended_options"),
        validation_condition="Change Authority decides only inside delegated tolerance thresholds.",
        tolerance_boundary="delegated change/exception tolerance",
        return_path="authority.change_authority -> management.project_manager via approval/rejection/rebaseline decision",
    ),
    RoleFlowEdge(
        edge_id="escalate.board_decision",
        trigger="out_of_delegated_tolerance_or_business_justification_risk",
        source_node="management.project_manager",
        target_node="board.executive",
        flow_type="board_decision",
        payload_scope=("exception_report", "business_case_impact", "benefit_impact", "cost_time_risk_forecast"),
        decision_authority="Project Executive / Project Board",
        expected_evidence=("exception_report", "business_case_update", "options_and_recommendation"),
        validation_condition="Board receives sufficient context for stop/go/rebaseline decision without delivery noise.",
        tolerance_boundary="project tolerances and business justification",
        return_path="board.executive -> management.project_manager via direction, exception plan authorization, or closure decision",
    ),
)


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


def build_prince2_role_flow() -> dict[str, object]:
    return {
        "command": "roles flow",
        "version": 1,
        "rule": "context moves only along approved PRINCE2 flow edges; broader context requires formal escalation or decision event",
        "edges": [edge.as_dict() for edge in ROLE_FLOW_EDGES],
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


def render_prince2_role_flow(flow: dict[str, object]) -> str:
    lines = ["PRINCE2 role flow:", f"- rule: {flow.get('rule')}"]
    edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
    for edge in edges:
        payload = ", ".join(str(item) for item in edge.get("payload_scope", []))
        evidence = ", ".join(str(item) for item in edge.get("expected_evidence", []))
        lines.append(
            f"- {edge.get('edge_id')}: {edge.get('source_node')} -> {edge.get('target_node')} "
            f"trigger={edge.get('trigger')} type={edge.get('flow_type')}"
        )
        lines.append(f"  payload={payload}")
        lines.append(f"  authority={edge.get('decision_authority')}")
        lines.append(f"  evidence={evidence}")
        lines.append(f"  validation={edge.get('validation_condition')}")
        lines.append(f"  tolerance={edge.get('tolerance_boundary')}")
        lines.append(f"  return={edge.get('return_path')}")
    return "\n".join(lines)
