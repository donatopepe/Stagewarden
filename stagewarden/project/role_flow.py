from __future__ import annotations

from datetime import datetime
import re
from typing import Callable, TextIO

from ..config import AgentConfig
from .. import model_views as _model_views
from ..model_catalog import catalog_entry_for_provider_model, load_ai_models_catalog
from ..modelprefs import (
    ModelPreferences,
    PRINCE2_ROLE_IDS,
    PRINCE2_ROLE_LABELS,
    canonicalize_model_variant,
    provider_model_spec,
    provider_model_specs,
)
from ..prince2 import Prince2AgentPolicy, Prince2ToleranceProfile
from ..provider_registry import SUPPORTED_MODELS
from ..role_tree import (
    ROLE_CONTEXT_RULES,
    STATUS_COLOR_LEGEND,
    PRINCE2_ROLE_AUTOMATION_RULES,
    PRINCE2_ROLE_SCOPE_DESCRIPTIONS,
    build_prince2_role_flow as _build_prince2_role_flow,
    build_prince2_role_matrix_payload as _build_prince2_role_matrix_payload,
    build_prince2_role_tree_with_tolerance as _build_prince2_role_tree_with_tolerance,
    check_prince2_role_tree_payload as _check_prince2_role_tree_payload,
    prince2_node_description,
    prince2_role_mnemonic,
    prince2_role_team_name,
    prince2_status_color,
)
from ..project_handoff import ProjectHandoff
from ..rag import DesignRag, resolve_min_score_policy_details
from .. import shell_views as _shell_views
from .. import project_handoff_views as _project_handoff_views
from . import model_recommendation as _project_model_recommendation
from . import role_views as _project_role_views
from . import role_tree_views as _project_role_tree_views
from . import flow as _project_flow


ROLE_RAG_HIGH_SIGNAL_TOKENS = {
    "decision",
    "exception",
    "tolerance",
    "escalation",
    "validation",
    "risk",
    "issue",
    "business_case",
    "change",
    "approval",
}


def _load_role_rag(config: AgentConfig) -> DesignRag | None:
    try:
        return DesignRag.load(config.rag_path)
    except (OSError, ValueError, TypeError):
        return None


def _stale_role_tree_baseline_block_report(config: AgentConfig, *, command: str) -> dict[str, object] | None:
    prefs = _model_views._load_model_preferences(config)
    baseline: dict[str, object] = dict(prefs.prince2_role_tree_baseline or {})
    if str(baseline.get("status", "approved")).strip().lower() != "stale":
        return None
    raw_stale = baseline.get("stale", {})
    stale: dict[str, object] = dict(raw_stale) if isinstance(raw_stale, dict) else {}
    action = str(
        stale.get("action")
        or "rerun project tree propose, review, then project tree approve before execution continues"
    )
    raw_changed_fields = stale.get("changed_fields", [])
    changed_fields = raw_changed_fields if isinstance(raw_changed_fields, list) else []
    return {
        "command": command,
        "ok": False,
        "status": "blocked_stale_baseline",
        "error": "PRINCE2 role-tree baseline is stale after project brief changes.",
        "baseline_status": "stale",
        "stale": stale,
        "changed_fields": [str(item) for item in changed_fields],
        "action": action,
    }


def _render_stale_role_tree_baseline_block(block: dict[str, object]) -> str:
    raw_stale = block.get("stale", {})
    stale: dict[str, object] = dict(raw_stale) if isinstance(raw_stale, dict) else {}
    raw_changed_fields = block.get("changed_fields", [])
    changed_fields = raw_changed_fields if isinstance(raw_changed_fields, list) else []
    return "\n".join(
        [
            "PRINCE2 runtime blocked: blocked_stale_baseline",
            f"- reason: {stale.get('reason') or block.get('error') or 'baseline is stale'}",
            f"- changed_fields: {', '.join(str(item) for item in changed_fields) if changed_fields else 'unknown'}",
            f"- action: {block.get('action') or 'rerun project tree propose and approve'}",
        ]
    )


def _should_index_role_message(*, payload_scope: list[str], evidence_refs: list[str], summary: str) -> bool:
    text = " ".join(payload_scope + evidence_refs + [summary]).lower()
    if not text.strip():
        return False
    return any(token in text for token in ROLE_RAG_HIGH_SIGNAL_TOKENS)


def _index_role_message_in_rag(
    config: AgentConfig,
    *,
    message: dict[str, object],
    payload_scope: list[str],
    evidence_refs: list[str],
    summary: str,
) -> str | None:
    rag = _load_role_rag(config)
    if rag is None:
        rag = DesignRag()
    entry = rag.add(
        phase="delivery",
        tags=[
            "prince2",
            "node_message",
            str(message.get("source_node", "")).strip(),
            str(message.get("target_node", "")).strip(),
            str(message.get("edge_id", "")).strip(),
        ],
        title=f"PRINCE2 message {message.get('message_id', 'unknown')}",
        content=(
            f"summary: {summary}\n"
            f"source_node: {message.get('source_node')}\n"
            f"target_node: {message.get('target_node')}\n"
            f"edge_id: {message.get('edge_id')}\n"
            f"payload_scope: {', '.join(payload_scope)}\n"
            f"evidence_refs: {', '.join(evidence_refs)}"
        ),
        metadata={
            "source": "role_message",
            "message_id": str(message.get("message_id", "")),
            "flow_type": str(message.get("flow_type", "")),
        },
    )
    try:
        rag.save(config.rag_path)
    except OSError:
        return None
    return entry.entry_id


def _node_role_type(handoff: ProjectHandoff, node_id: str) -> str | None:
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    nodes = runtime.get("nodes", []) if isinstance(runtime.get("nodes", []), list) else []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("node_id", "")).strip() == node_id:
            role_type = str(node.get("role_type", "")).strip()
            return role_type or None
    return None


def _rag_context_for_node_tick(config: AgentConfig, *, handoff: ProjectHandoff, node_id: str, result: dict[str, object]) -> dict[str, object] | None:
    consumed = result.get("consumed_message") if isinstance(result.get("consumed_message"), dict) else None
    if consumed is None:
        return None
    payload_scope = [str(item).strip() for item in consumed.get("payload_scope", []) if str(item).strip()]
    summary = str(consumed.get("summary", "")).strip()
    edge_id = str(consumed.get("edge_id", "")).strip()
    source_node = str(consumed.get("source_node", "")).strip()
    target_node = str(consumed.get("target_node", "")).strip()
    query = " ".join(payload_scope + [summary, edge_id]).strip()
    if not query:
        return None
    rag = _load_role_rag(config)
    if rag is None:
        return None
    role_type = _node_role_type(handoff, node_id)
    policy = resolve_min_score_policy_details(phase="delivery", role=role_type, mode="hybrid", override=None)
    min_score = float(policy.get("min_score", 0.0))
    scoped_tags = [item for item in [source_node, target_node, edge_id] if item]
    entries = rag.search_diagnostics(
        query,
        phase="delivery",
        role=role_type,
        tags=scoped_tags or None,
        mode="hybrid",
        min_score=min_score,
        limit=3,
    )
    if not entries:
        entries = rag.search_diagnostics(
            query,
            phase="delivery",
            role=role_type,
            mode="hybrid",
            min_score=min_score,
            limit=3,
        )
    if not entries:
        return {
            "query": query,
            "policy_source": str(policy.get("policy_source", "default")),
            "min_score": min_score,
            "scoped_tags": scoped_tags,
            "entries": [],
        }
    compact_entries = [
        {
            "entry_id": item["entry"].entry_id,
            "title": item["entry"].title,
            "score": float(item.get("score", 0.0)),
        }
        for item in entries
    ]
    return {
        "query": query,
        "policy_source": str(policy.get("policy_source", "default")),
        "min_score": min_score,
        "scoped_tags": scoped_tags,
        "entries": compact_entries,
    }


def _role_options() -> list[tuple[str, str]]:
    return [(role, f"{PRINCE2_ROLE_LABELS[role]} ({role})") for role in PRINCE2_ROLE_IDS]


def _role_tree_node_options(config: AgentConfig) -> list[tuple[str, str]]:
    prefs = _model_views._load_model_preferences(config)
    baseline = _ensure_prince2_role_tree_baseline(config, prefs, source="role_menu")
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = tree.get("nodes", []) if isinstance(tree, dict) else []
    options: list[tuple[str, str]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("node_id", "")).strip()
        if not node_id:
            continue
        assignment = node.get("assignment") if isinstance(node.get("assignment"), dict) else {}
        provider = assignment.get("provider", "unassigned") if isinstance(assignment, dict) and assignment else "unassigned"
        provider_model = assignment.get("provider_model", "none") if isinstance(assignment, dict) and assignment else "none"
        status_color = prince2_status_color(node)
        label = (
            f"{node.get('label', node_id)} [{node_id}] "
            f"role={node.get('role_type', 'unknown')} "
            f"state={node.get('tolerance_state', node.get('state', 'unknown'))} color={status_color} "
            f"margin={node.get('tolerance_margin_percent', 'unknown')} pressure={node.get('tolerance_pressure_percent', 'unknown')} "
            f"provider={provider} provider_model={provider_model}"
        )
        options.append((node_id, label))
    return options


def _role_tree_node_record(config: AgentConfig, node_id: str) -> dict[str, object] | None:
    prefs = _model_views._load_model_preferences(config)
    baseline = _ensure_prince2_role_tree_baseline(config, prefs, source="role_node_context")
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = tree.get("nodes", []) if isinstance(tree, dict) else []
    for node in nodes:
        if isinstance(node, dict) and str(node.get("node_id", "")).strip() == node_id:
            return dict(node)
    return None


def _role_tree_nodes_by_parent(config: AgentConfig, parent_id: str | None) -> list[dict[str, object]]:
    prefs = _model_views._load_model_preferences(config)
    baseline = _ensure_prince2_role_tree_baseline(config, prefs, source="role_nodes_by_parent")
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = tree.get("nodes", []) if isinstance(tree, dict) else []
    if parent_id is None:
        return [dict(node) for node in nodes if isinstance(node, dict) and node.get("parent_id") in {None, ""}]
    clean_parent = str(parent_id).strip()
    return [dict(node) for node in nodes if isinstance(node, dict) and str(node.get("parent_id", "")).strip() == clean_parent]


def _role_tree_node_children(config: AgentConfig, node_id: str) -> list[dict[str, object]]:
    return _role_tree_nodes_by_parent(config, node_id)


def _with_prince2_role_tree_baseline_mutation(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    source: str,
    mutator: Callable[[dict[str, object], dict[str, object], list[dict[str, object]]], None],
) -> dict[str, object]:
    baseline = _ensure_prince2_role_tree_baseline(config, prefs, source=source)
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = [node for node in tree.get("nodes", []) if isinstance(node, dict)]
    mutator(baseline, tree, nodes)
    tree["nodes"] = nodes
    baseline["tree"] = tree
    baseline["status"] = "approved"
    baseline["source"] = source
    baseline["approved_at"] = datetime.now().isoformat(timespec="seconds")
    _refresh_prince2_role_tree_baseline_checks(baseline, prefs)
    _persist_prince2_role_tree_baseline(config, prefs, baseline)
    return baseline


def _parse_project_tolerance_margin_percent(value: object, default: float = 25.0) -> float:
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
    return min(100.0, parsed)


def _project_accountable_owner(handoff: ProjectHandoff) -> str:
    value = handoff.project_brief.get("accountable_project_executive", "user")
    owner = str(value).strip() if value is not None else "user"
    return owner or "user"


def _project_tolerance_margin_percent(handoff: ProjectHandoff, default: float = 25.0) -> float:
    return _parse_project_tolerance_margin_percent(handoff.project_brief.get("tolerance_margin_percent"), default=default)


def _project_tolerance_profile(handoff: ProjectHandoff, *, task: str | None = None) -> Prince2ToleranceProfile:
    policy = Prince2AgentPolicy()
    effective_task = task or handoff.task or str(handoff.project_brief.get("objective", "")).strip() or "PRINCE2 role tree"
    margin = _project_tolerance_margin_percent(handoff)
    owner = _project_accountable_owner(handoff)
    checklist = policy.build_checklist(
        effective_task,
        project_brief=handoff.project_brief,
        base_margin_percent=margin,
        accountable_owner=owner,
    )
    return policy.build_tolerance_profile(
        effective_task,
        checklist,
        project_brief=handoff.project_brief,
        base_margin_percent=margin,
        accountable_owner=owner,
    )


def _set_prince2_role_node_tolerance_margin(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    margin_percent: float,
    source: str = "role_tolerance_set",
) -> dict[str, object]:
    clean_margin = max(0.0, min(100.0, float(margin_percent)))

    def mutator(baseline: dict[str, object], tree: dict[str, object], nodes: list[dict[str, object]]) -> None:
        for node in nodes:
            if str(node.get("node_id", "")).strip() != node_id:
                continue
            node["tolerance_margin_percent"] = round(clean_margin, 2)
            tolerance_profile = dict(node.get("tolerance_profile", {})) if isinstance(node.get("tolerance_profile", {}), dict) else {}
            tolerance_profile["margin_percent"] = round(clean_margin, 2)
            tolerance_profile["manual_override"] = True
            node["tolerance_profile"] = tolerance_profile
            node["autonomy_rule"] = str(node.get("autonomy_rule", "")).strip() or "work autonomously within the margin; escalate when pressure exceeds margin."
            break

    _with_prince2_role_tree_baseline_mutation(config, prefs, source=source, mutator=mutator)
    return _role_tree_node_record(config, node_id) or {}


def _reset_prince2_role_node_tolerance(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    source: str = "role_tolerance_reset",
) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    tolerance_profile = _project_tolerance_profile(handoff)

    def mutator(baseline: dict[str, object], tree: dict[str, object], nodes: list[dict[str, object]]) -> None:
        for node in nodes:
            if str(node.get("node_id", "")).strip() != node_id:
                continue
            role_type = str(node.get("role_type", "")).strip()
            profile = tolerance_profile.node_profile(role_type)
            node["accountable_owner"] = profile.get("accountable_owner", tolerance_profile.accountable_owner)
            node["tolerance_margin_percent"] = profile.get("margin_percent", tolerance_profile.project_margin_percent)
            node["tolerance_pressure_percent"] = profile.get("pressure_percent", tolerance_profile.project_pressure_percent)
            node["autonomy_rule"] = profile.get("autonomy_rule", node.get("autonomy_rule", ""))
            node["escalation_target"] = profile.get("escalation_target", node.get("escalation_target", "board.executive"))
            node["tolerance_profile"] = profile
            break

    _with_prince2_role_tree_baseline_mutation(config, prefs, source=source, mutator=mutator)
    return _role_tree_node_record(config, node_id) or {}


def _build_prince2_role_tree_baseline(config: AgentConfig, *, source: str) -> dict[str, object]:
    prefs = _model_views._load_model_preferences(config)
    handoff = ProjectHandoff.load(config.handoff_path)
    tolerance_profile = _project_tolerance_profile(handoff)
    local_execution = _model_views._local_execution_candidates_report(config)
    tree = _project_flow._enrich_tree_with_local_execution_candidates(
        _build_prince2_role_tree_with_tolerance(
            prefs,
            tolerance_profile=tolerance_profile,
            accountable_owner=tolerance_profile.accountable_owner,
        ),
        local_execution,
    )
    brief = {str(key): str(value) for key, value in handoff.project_brief.items()}
    joined = " ".join(brief.values()).lower()
    _decomposition_nodes, decomposition = _project_flow._project_tree_decomposition_nodes(
        proposal_prefs=prefs,
        active_models=list(prefs.active_models() or prefs.enabled_models),
        brief=brief,
        joined=joined,
        tolerance_profile=tolerance_profile,
    )
    adaptation = _project_flow._project_tree_adaptation_snapshot(brief=brief, handoff=handoff, local_execution=local_execution)
    tree["decomposition_policy"] = "Decompose the project into the smallest independently verifiable work packages and keep widening only when evidence justifies it."
    tree["adaptation_policy"] = "Refresh the tree continuously from the latest brief, tolerance profile, runtime observation, and response-quality signals."
    tree["decomposition"] = decomposition
    tree["adaptation"] = adaptation
    return {
        "version": "1",
        "approved_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "status": "approved",
        "tree": tree,
        "flow": _build_prince2_role_flow(),
        "check": _check_prince2_role_tree_payload(tree, prefs),
        "matrix": _build_prince2_role_matrix_payload(tree, prefs),
        "local_execution": local_execution,
        "decomposition": decomposition,
        "adaptation": adaptation,
    }


def _approve_prince2_role_tree_baseline(config: AgentConfig, prefs: ModelPreferences, *, source: str) -> dict[str, object]:
    baseline = _build_prince2_role_tree_baseline(config, source=source)
    prefs.set_prince2_role_tree_baseline(baseline)
    prefs.normalize().save(config.model_prefs_path)
    handoff = ProjectHandoff.load(config.handoff_path)
    handoff.sync_prince2_roles(dict(prefs.prince2_roles or {}))
    handoff.sync_prince2_role_tree_baseline(dict(prefs.prince2_role_tree_baseline or {}))
    handoff.save(config.handoff_path)
    return baseline


def _refresh_prince2_role_tree_baseline_checks(baseline: dict[str, object], prefs: ModelPreferences) -> dict[str, object]:
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    baseline["check"] = _check_prince2_role_tree_payload(tree, prefs)
    baseline["matrix"] = _build_prince2_role_matrix_payload(tree, prefs)
    return baseline


def _persist_prince2_role_tree_baseline(config: AgentConfig, prefs: ModelPreferences, baseline: dict[str, object]) -> None:
    prefs.set_prince2_role_tree_baseline(baseline)
    prefs.normalize().save(config.model_prefs_path)
    handoff = ProjectHandoff.load(config.handoff_path)
    handoff.sync_prince2_roles(dict(prefs.prince2_roles or {}))
    handoff.sync_prince2_role_tree_baseline(dict(prefs.prince2_role_tree_baseline or {}))
    handoff.save(config.handoff_path)


def _ensure_prince2_role_tree_baseline(config: AgentConfig, prefs: ModelPreferences, *, source: str) -> dict[str, object]:
    baseline = dict(prefs.prince2_role_tree_baseline or {})
    if baseline:
        return baseline
    return _build_prince2_role_tree_baseline(config, source=source)


def _add_child_prince2_role_node(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    parent_id: str,
    role_type: str,
    node_id: str | None = None,
) -> dict[str, object]:
    if role_type not in PRINCE2_ROLE_IDS:
        raise ValueError(f"Unsupported PRINCE2 role '{role_type}'. Supported: {', '.join(PRINCE2_ROLE_IDS)}")
    baseline = _ensure_prince2_role_tree_baseline(config, prefs, source="role_add_child")
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = list(tree.get("nodes", [])) if isinstance(tree.get("nodes", []), list) else []
    parent = next((node for node in nodes if isinstance(node, dict) and node.get("node_id") == parent_id), None)
    if parent is None:
        raise ValueError(f"Parent role node '{parent_id}' not found.")
    existing_ids = {str(node.get("node_id")) for node in nodes if isinstance(node, dict)}
    if node_id is None:
        base = f"{parent_id}.{role_type}"
        candidate = base
        index = 2
        while candidate in existing_ids:
            candidate = f"{base}_{index}"
            index += 1
        node_id = candidate
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", node_id):
        raise ValueError("Node id must contain only letters, numbers, dot, dash, and underscore.")
    if node_id in existing_ids:
        raise ValueError(f"Role node '{node_id}' already exists.")
    rule = ROLE_CONTEXT_RULES[role_type].as_dict()
    child = {
        "node_id": node_id,
        "role_type": role_type,
        "label": f"{PRINCE2_ROLE_LABELS[role_type]} Delegated",
        "parent_id": parent_id,
        "level": f"delegated_{parent.get('level', 'node')}",
        "accountability_boundary": f"delegated {PRINCE2_ROLE_LABELS[role_type]} accountability under {parent.get('label', parent_id)}",
        "delegated_authority": f"delegated by {parent.get('label', parent_id)}; cannot exceed parent authority or approved tolerances",
        "responsibility_domain": PRINCE2_ROLE_AUTOMATION_RULES.get(role_type, "controlled project work"),
        "context_scope": PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role_type, "controlled project work"),
        "context_rule": rule,
        "assignment": {},
        "fallback_pool": list(prefs.active_models() or prefs.enabled_models),
        "readiness": "unassigned",
    }
    nodes.append(child)
    tree["nodes"] = nodes
    baseline["tree"] = tree
    baseline["status"] = "approved"
    baseline["source"] = "role_add_child"
    baseline["approved_at"] = datetime.now().isoformat(timespec="seconds")
    _refresh_prince2_role_tree_baseline_checks(baseline, prefs)
    _persist_prince2_role_tree_baseline(config, prefs, baseline)
    return child


def _send_prince2_role_message(
    config: AgentConfig,
    *,
    source_node: str,
    target_node: str,
    edge_id: str,
    payload_scope: list[str],
    evidence_refs: list[str] | None = None,
    summary: str | None = None,
) -> dict[str, object]:
    prefs = _model_views._load_model_preferences(config)
    _model_views._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    message = handoff.send_prince2_node_message(
        source_node=source_node,
        target_node=target_node,
        edge_id=edge_id,
        payload_scope=payload_scope,
        evidence_refs=evidence_refs,
        summary=summary,
    )
    rag_entry_id: str | None = None
    summary_text = str(summary or message.get("summary", "")).strip()
    if _should_index_role_message(payload_scope=payload_scope, evidence_refs=list(evidence_refs or []), summary=summary_text):
        rag_entry_id = _index_role_message_in_rag(
            config,
            message=message,
            payload_scope=list(payload_scope),
            evidence_refs=list(evidence_refs or []),
            summary=summary_text,
        )
        if rag_entry_id:
            message["rag_entry_id"] = rag_entry_id
    handoff.save(config.handoff_path)
    _project_handoff_views._record_handoff_action(
        config,
        phase="role_message",
        task=f"role message {source_node} {target_node} {edge_id}",
        summary=f"Queued governed PRINCE2 node message {message['message_id']}.",
        details={
            "source_node": source_node,
            "target_node": target_node,
            "edge_id": edge_id,
            "payload_scope": list(payload_scope),
            "evidence_refs": list(evidence_refs or []),
            "rag_entry_id": rag_entry_id,
        },
    )
    return message


def _set_prince2_role_node_waiting(
    config: AgentConfig,
    *,
    node_id: str,
    reason: str,
    wake_triggers: list[str] | None = None,
) -> dict[str, object]:
    prefs = _model_views._load_model_preferences(config)
    _model_views._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    node = handoff.set_prince2_node_waiting(node_id=node_id, reason=reason, wake_triggers=wake_triggers)
    handoff.save(config.handoff_path)
    _project_handoff_views._record_handoff_action(
        config,
        phase="role_wait",
        task=f"role wait {node_id}",
        summary=f"Node {node_id} moved to waiting state.",
        details={"node_id": node_id, "reason": reason, "wake_triggers": list(wake_triggers or [])},
    )
    return node


def _wake_prince2_role_node(
    config: AgentConfig,
    *,
    node_id: str,
    trigger: str,
) -> dict[str, object]:
    prefs = _model_views._load_model_preferences(config)
    _model_views._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    node = handoff.wake_prince2_node(node_id=node_id, trigger=trigger)
    handoff.save(config.handoff_path)
    _project_handoff_views._record_handoff_action(
        config,
        phase="role_wake",
        task=f"role wake {node_id}",
        summary=f"Node {node_id} woke with trigger {trigger}.",
        details={"node_id": node_id, "trigger": trigger},
    )
    return node


def _tick_prince2_role_node(
    config: AgentConfig,
    *,
    node_id: str,
) -> dict[str, object]:
    block = _stale_role_tree_baseline_block_report(config, command=f"role tick {node_id}")
    if block is not None:
        return block
    prefs = _model_views._load_model_preferences(config)
    _model_views._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    result = handoff.tick_prince2_node(node_id=node_id)
    rag_context = _rag_context_for_node_tick(config, handoff=handoff, node_id=node_id, result=result)
    if rag_context is not None:
        result["rag_context"] = rag_context
    handoff.save(config.handoff_path)
    _model_views._sync_prince2_role_tree_baseline_back_to_preferences(config, prefs, handoff)
    _project_handoff_views._record_handoff_action(
        config,
        phase="role_tick",
        task=f"role tick {node_id}",
        summary=f"Node {node_id} advanced to {result.get('state', 'unknown')}.",
        details=dict(result),
    )
    return result


def _tick_prince2_role_runtime(
    config: AgentConfig,
    *,
    max_nodes: int | None = None,
) -> dict[str, object]:
    block = _stale_role_tree_baseline_block_report(config, command="roles tick")
    if block is not None:
        return block
    prefs = _model_views._load_model_preferences(config)
    _model_views._sync_prince2_roles_to_handoff(config, prefs)
    handoff = ProjectHandoff.load(config.handoff_path)
    result = handoff.tick_prince2_runtime(max_nodes=max_nodes)
    rag_context_by_node: dict[str, dict[str, object]] = {}
    for item in result.get("results", []):
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("node_id", "")).strip()
        if not node_id:
            continue
        rag_context = _rag_context_for_node_tick(config, handoff=handoff, node_id=node_id, result=item)
        if rag_context is not None:
            rag_context_by_node[node_id] = rag_context
    result["rag_context_by_node"] = rag_context_by_node
    handoff.save(config.handoff_path)
    _model_views._sync_prince2_role_tree_baseline_back_to_preferences(config, prefs, handoff)
    _project_handoff_views._record_handoff_action(
        config,
        phase="roles_tick",
        task=f"roles tick {max_nodes if max_nodes is not None else ''}".strip(),
        summary=f"Batch advanced PRINCE2 runtime across {result.get('processed', 0)} node(s).",
        details=dict(result),
    )
    return result


def _assign_prince2_role_node(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    provider: str,
    provider_model: str,
    params: dict[str, str] | None = None,
    account: str | None = None,
    pool: str = "primary",
) -> dict[str, object]:
    clean_pool = str(pool).strip().lower() or "primary"
    if clean_pool not in {"primary", "reviewer", "fallback"}:
        raise ValueError("Pool must be primary, reviewer, or fallback.")
    if provider not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported provider '{provider}'. Supported: {', '.join(SUPPORTED_MODELS)}")
    canonical_model = canonicalize_model_variant(provider, provider_model)
    if account is not None and account not in (prefs.accounts_by_model or {}).get(provider, []):
        raise ValueError(f"Account '{account}' is not configured for provider '{provider}'.")
    baseline = _ensure_prince2_role_tree_baseline(config, prefs, source="role_assign")
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = list(tree.get("nodes", [])) if isinstance(tree.get("nodes", []), list) else []
    target = next((node for node in nodes if isinstance(node, dict) and node.get("node_id") == node_id), None)
    if target is None:
        raise ValueError(f"Role node '{node_id}' not found.")
    clean_params: dict[str, str] = {}
    spec = provider_model_spec(provider, canonical_model)
    for key, value in (params or {}).items():
        if key != "reasoning_effort":
            continue
        if spec is not None and value in spec.reasoning_efforts:
            clean_params[key] = value
    route = {
        "role": str(target.get("role_type", "")),
        "node_id": node_id,
        "label": str(target.get("label", node_id)),
        "mode": "manual",
        "provider": provider,
        "provider_model": canonical_model,
        "params": clean_params,
        "account": account,
        "source": "node_manual",
    }
    if clean_pool == "primary":
        target["assignment"] = route
        target["fallback_pool"] = [model for model in (prefs.active_models() or prefs.enabled_models) if model != provider]
        target["readiness"] = "assigned"
    else:
        pools = target.get("assignment_pool", {}) if isinstance(target.get("assignment_pool"), dict) else {}
        routes = [dict(item) for item in pools.get(clean_pool, []) if isinstance(item, dict)] if isinstance(pools.get(clean_pool, []), list) else []
        routes = [
            item
            for item in routes
            if not (item.get("provider") == provider and item.get("provider_model") == canonical_model and item.get("account") == account)
        ]
        route["pool"] = clean_pool
        routes.append(route)
        pools[clean_pool] = routes
        target["assignment_pool"] = pools
        if target.get("assignment"):
            target["readiness"] = "assigned"
        else:
            target["readiness"] = "reviewer_pool_only" if clean_pool == "reviewer" else "fallback_pool_only"
    tree["nodes"] = nodes
    baseline["tree"] = tree
    baseline["status"] = "approved"
    baseline["source"] = "role_assign"
    baseline["approved_at"] = datetime.now().isoformat(timespec="seconds")
    _refresh_prince2_role_tree_baseline_checks(baseline, prefs)
    _persist_prince2_role_tree_baseline(config, prefs, baseline)
    return dict(target)


def _remove_prince2_role_node(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    reparent_children: bool = True,
    source: str = "role_remove",
) -> dict[str, object]:
    removed: dict[str, object] = {}

    def mutator(baseline: dict[str, object], tree: dict[str, object], nodes: list[dict[str, object]]) -> None:
        nonlocal removed
        target = next((node for node in nodes if str(node.get("node_id", "")).strip() == node_id), None)
        if target is None:
            raise ValueError(f"Role node '{node_id}' not found.")
        if node_id == "board.executive":
            raise ValueError("The Project Executive root node cannot be removed.")
        removed = dict(target)
        parent_id = str(target.get("parent_id")) if target.get("parent_id") not in {None, ""} else None
        if reparent_children:
            for child in nodes:
                if str(child.get("parent_id", "")).strip() == node_id:
                    child["parent_id"] = parent_id
        nodes[:] = [node for node in nodes if str(node.get("node_id", "")).strip() != node_id]
        flow = baseline.get("flow", {}) if isinstance(baseline.get("flow"), dict) else {}
        edges = flow.get("edges", []) if isinstance(flow, dict) else []
        if isinstance(edges, list):
            flow["edges"] = [
                edge
                for edge in edges
                if isinstance(edge, dict)
                and str(edge.get("source_node", "")).strip() != node_id
                and str(edge.get("target_node", "")).strip() != node_id
            ]
            baseline["flow"] = flow

    _with_prince2_role_tree_baseline_mutation(config, prefs, source=source, mutator=mutator)
    return removed


def _guided_role_node_assignment_context(config: AgentConfig, node_id: str, pool: str) -> str:
    node = _role_tree_node_record(config, node_id)
    if not node:
        return ""
    lines = [
        "Node assignment context:",
        f"- node_id: {node_id}",
        f"- role_type: {node.get('role_type', 'unknown')}",
        f"- level: {node.get('level', 'unknown')}",
        f"- selected_pool: {pool}",
    ]
    local_routes = _project_model_recommendation._node_local_fallback_candidates(node)
    if local_routes:
        lines.append(
            "- recommended_local_fallbacks: "
            + ", ".join(
                f"{item.get('provider_model')}({((item.get('params') or {}).get('reasoning_effort') or 'provider-default')})"
                for item in local_routes
            )
        )
    else:
        lines.append("- recommended_local_fallbacks: none")
    return "\n".join(lines)


def _role_tree_node_navigation(config: AgentConfig, node_id: str) -> dict[str, object]:
    node = _role_tree_node_record(config, node_id)
    if not node:
        return {}
    parent_id = node.get("parent_id")
    siblings = _role_tree_nodes_by_parent(config, str(parent_id) if parent_id not in {None, ""} else None)
    sibling_ids = [str(item.get("node_id", "")).strip() for item in siblings if str(item.get("node_id", "")).strip()]
    try:
        index = sibling_ids.index(node_id)
    except ValueError:
        index = -1
    children = _role_tree_node_children(config, node_id)
    child_ids = [str(item.get("node_id", "")).strip() for item in children if str(item.get("node_id", "")).strip()]
    return {
        "node_id": node_id,
        "parent_id": str(parent_id).strip() if parent_id not in {None, ""} else None,
        "siblings": sibling_ids,
        "children": child_ids,
        "previous_sibling": sibling_ids[index - 1] if index > 0 else None,
        "next_sibling": sibling_ids[index + 1] if index >= 0 and index + 1 < len(sibling_ids) else None,
    }


def _render_prince2_role_node_detail(config: AgentConfig, node_id: str) -> str:
    report = _project_role_views._prince2_role_context_report(config, node_id)
    if report.get("status") != "ok":
        return str(report.get("message", "PRINCE2 role context unavailable."))
    runtime_state = report["runtime_state"]
    role_context = report["prince2_role_context"]
    assignment = report["assignment"]
    comms = report["communications"]
    caps = report["agent_capabilities"]
    lines = [
        "PRINCE2 node detail:",
        f"- node: {report['node_label']} [{report['node_id']}]",
        f"- role_type: {report['role_type']} mnemonic={prince2_role_mnemonic(report['role_type'])} team={prince2_role_team_name(report['role_type'])}",
        f"- state: {runtime_state['state']} wait={runtime_state['wait_status']} inbox={runtime_state['inbox_count']} outbox={runtime_state['outbox_count']}",
        f"- parent: {next((str(edge.get('source_node')) for edge in comms['incoming_edges'] if str(edge.get('source_node', '')).strip()), 'none')}",
        f"- provider: {assignment.get('provider') or 'none'} provider_model={assignment.get('provider_model') or 'none'} account={assignment.get('account') or 'none'}",
        f"- tolerance_margin: {runtime_state.get('tolerance_margin_percent', 'unknown')} pressure={runtime_state.get('tolerance_pressure_percent', 'unknown')} state={runtime_state.get('tolerance_state', runtime_state['state'])}",
        f"- responsibility_domain: {role_context['responsibility_domain']}",
        f"- context_scope: {role_context['context_scope']}",
        f"- accountability_boundary: {role_context['accountability_boundary']}",
        f"- delegated_authority: {role_context['delegated_authority']}",
        f"- context_include: {', '.join(role_context['context_include']) or 'none'}",
        f"- context_exclude: {', '.join(role_context['context_exclude']) or 'none'}",
        f"- wake_triggers: {', '.join(runtime_state['wake_triggers']) or 'none'}",
        f"- incoming_edges: {', '.join(str(edge.get('edge_id')) for edge in comms['incoming_edges']) or 'none'}",
        f"- outgoing_edges: {', '.join(str(edge.get('edge_id')) for edge in comms['outgoing_edges']) or 'none'}",
        f"- agent_tools: {', '.join(caps['shell_operations'] + caps['git_operations'][:2] + ['...'])}",
        f"- file_ops: {', '.join(caps['file_operations'][:6])}, ...",
    ]
    recommendation = _project_model_recommendation._node_model_recommendation(config, _role_tree_node_record(config, node_id) or {})
    suggested = recommendation.get("suggested", {}) if isinstance(recommendation.get("suggested"), dict) else {}
    lines.append(
        f"- model_recommendation: direction={recommendation.get('direction', 'hold')} "
        f"provider={suggested.get('provider') or 'none'} provider_model={suggested.get('provider_model') or 'none'} "
        f"bucket={suggested.get('bucket', 'none')}"
    )
    lines.append("- communication_commands:")
    for command in comms["commands"]:
        lines.append(f"  {command}")
    lines.append(f"- project_task: {report['project_context']['task']}")
    lines.append(f"- project_status: {report['project_context']['project_status']}")
    lines.append(f"- current_step: {report['project_context']['current_step']} [{report['project_context']['current_step_status']}]")
    return "\n".join(lines)


def _render_prince2_role_node_shell(config: AgentConfig, node_id: str) -> str:
    node = _role_tree_node_record(config, node_id)
    if not node:
        return f"PRINCE2 node '{node_id}' not found."
    navigation = _role_tree_node_navigation(config, node_id)
    role_type = str(node.get("role_type", "")).strip()
    parent_id = navigation.get("parent_id") or "none"
    siblings = navigation.get("siblings", [])
    children = navigation.get("children", [])
    recommendation = _project_model_recommendation._node_model_recommendation(config, node)
    suggested = recommendation.get("suggested", {}) if isinstance(recommendation.get("suggested"), dict) else {}
    lines = [
        "PRINCE2 node shell:",
        f"- node: {node.get('label', node_id)} [{node_id}]",
        f"- role_type: {role_type} mnemonic={prince2_role_mnemonic(role_type)} team={prince2_role_team_name(role_type)}",
        f"- parent={parent_id}",
        f"- siblings: {', '.join(siblings) or 'none'}",
        f"- children: {', '.join(children) or 'none'}",
        f"- description={prince2_node_description(node)}",
        f"- status_color={prince2_status_color(node)}",
        "- status_legend: "
        + ", ".join(f"{color}={meaning}" for color, meaning in STATUS_COLOR_LEGEND.items()),
        f"- model_recommendation: direction={recommendation.get('direction', 'hold')} provider={suggested.get('provider') or 'none'} provider_model={suggested.get('provider_model') or 'none'} bucket={suggested.get('bucket', 'none')}",
        "- actions: parent prev next child jump menu switch back",
        f"- shell=role shell {node_id}",
        f"- switch_hint: role switch {node_id}",
    ]
    return "\n".join(lines)


def _node_model_choice_options(config: AgentConfig, node_id: str) -> list[tuple[str, str]]:
    node = _role_tree_node_record(config, node_id)
    if not node:
        return []
    recommendation = _project_model_recommendation._node_model_recommendation(config, node)
    current = recommendation.get("current", {}) if isinstance(recommendation.get("current"), dict) else {}
    current_key = _model_views._catalog_model_choice_key(
        str(current.get("provider", "")).strip(),
        str(current.get("provider_model", "")).strip(),
    )

    options: list[tuple[str, str]] = []
    seen: set[str] = set()

    def append_group(prefix: str, items: list[dict[str, object]]) -> None:
        for item in items:
            provider = str(item.get("provider", "")).strip()
            provider_model = str(item.get("provider_model", "")).strip()
            if not provider or not provider_model:
                continue
            key = _model_views._catalog_model_choice_key(provider, provider_model)
            if key in seen:
                continue
            seen.add(key)
            label = str(item.get("label", key))
            if key == current_key:
                label = f"[current] {label}"
            else:
                label = f"[{prefix}] {label}"
            options.append((key, label))

    append_group("stronger", [item for item in recommendation.get("stronger", []) if isinstance(item, dict)])
    append_group("lighter", [item for item in recommendation.get("lighter", []) if isinstance(item, dict)])
    append_group("peer", [item for item in recommendation.get("peers", []) if isinstance(item, dict)])

    if current_key and current_key not in seen and current.get("provider") and current.get("provider_model"):
        options.insert(
            0,
            (
                current_key,
                f"[current] {current.get('provider')} / {current.get('provider_model')} | current assignment",
            ),
        )
    return options


def _guided_provider_options_for_node(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    node_id: str,
    pool: str,
) -> list[tuple[str, str]]:
    providers = list(prefs.enabled_models or list(SUPPORTED_MODELS))
    node = _role_tree_node_record(config, node_id)
    local_routes = _project_model_recommendation._node_local_fallback_candidates(node) if node else []
    recommended_local = bool(pool == "fallback" and local_routes)
    ordered: list[str] = []
    if recommended_local and "local" in providers:
        ordered.append("local")
    for provider in providers:
        if provider not in ordered:
            ordered.append(provider)
    options: list[tuple[str, str]] = []
    for provider in ordered:
        label = provider
        if provider == "local" and local_routes:
            label += " | recommended for this node fallback"
        options.append((provider, label))
    return options


def _guided_provider_model_options_for_node(
    config: AgentConfig,
    *,
    provider: str,
    node_id: str,
    pool: str,
) -> list[tuple[str, str]]:
    node = _role_tree_node_record(config, node_id)
    local_routes = _project_model_recommendation._node_local_fallback_candidates(node) if node else []
    catalog = load_ai_models_catalog()
    if provider == "local" and pool == "fallback" and local_routes:
        return [
            (
                str(item.get("provider_model", "")),
                f"{item.get('provider_model')} | recommended local fallback reasoning={((item.get('params') or {}).get('reasoning_effort') or 'provider-default')}",
            )
            for item in local_routes
            if str(item.get("provider_model", "")).strip()
        ]
    specs = list(provider_model_specs(provider))
    return [
        (spec.id, f"{spec.id} | {spec.label}{_project_model_recommendation._catalog_option_suffix(catalog_entry_for_provider_model(provider, spec.id, catalog))}")
        for spec in specs
    ]


def _guided_provider_context(prefs: ModelPreferences, provider: str | None = None) -> str:
    enabled = ", ".join(prefs.enabled_models or []) or "none"
    preferred = prefs.preferred_model or "automatic"
    lines = [
        "Selection context:",
        f"- enabled_providers: {enabled}",
        f"- preferred_provider: {preferred}",
    ]
    active_accounts = []
    for item in prefs.enabled_models or []:
        account = (prefs.active_account_by_model or {}).get(item)
        if account:
            active_accounts.append(f"{item}={account}")
    blocked = []
    for item in prefs.enabled_models or []:
        until = (prefs.blocked_until_by_model or {}).get(item)
        if until:
            blocked.append(f"{item}:{until}")
    lines.append(f"- active_accounts: {', '.join(active_accounts) or 'none'}")
    lines.append(f"- blocked_providers: {', '.join(blocked) or 'none'}")
    if provider:
        provider_model = prefs.variant_for_model(provider) or "provider-default"
        params = prefs.params_for_model(provider)
        reasoning = params.get("reasoning_effort") or "provider-default"
        accounts = ", ".join((prefs.accounts_by_model or {}).get(provider, [])) or "none"
        lines.extend(
            [
                f"- selected_provider: {provider}",
                f"- current_provider_model: {provider_model}",
                f"- current_reasoning_effort: {reasoning}",
                f"- configured_accounts: {accounts}",
            ]
        )
    return "\n".join(lines)


def _route_pool_options() -> list[tuple[str, str]]:
    return [
        ("primary", "primary - route used for normal execution"),
        ("reviewer", "reviewer - independent review/assurance route"),
        ("fallback", "fallback - same-context route used if primary is unavailable"),
    ]


def _guided_role_context(role: str) -> str:
    return "\n".join(
        [
            "PRINCE2 role context:",
            f"- role: {PRINCE2_ROLE_LABELS[role]} ({role})",
            f"- mnemonic: {prince2_role_mnemonic(role)}",
            f"- team: {prince2_role_team_name(role)}",
            f"- responsibility: {PRINCE2_ROLE_AUTOMATION_RULES.get(role, 'controlled project work')}",
            f"- context_scope: {PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role, 'controlled project work')}",
        ]
    )


def _guided_role_configure(
    *,
    requested_role: str | None,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided role configuration is available in the interactive shell. Run `python3 -m stagewarden.main` and use `/role configure`."
    role = requested_role
    if role is None:
        role = _shell_views._prompt_menu_choice(
            title="Choose PRINCE2 role:",
            options=_role_options(),
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if role is None:
            return "Role configuration cancelled."
    if role not in PRINCE2_ROLE_IDS:
        return f"Unsupported PRINCE2 role '{role}'. Supported: {', '.join(PRINCE2_ROLE_IDS)}"
    output_stream.write(_guided_role_context(role) + "\n")
    output_stream.write(_guided_provider_context(prefs) + "\n")
    mode = _shell_views._prompt_menu_choice(
        title=f"Configure {PRINCE2_ROLE_LABELS[role]}:",
        options=[
            ("auto", "Automatic proposal for this role"),
            ("manual", "Manual provider/model/account selection"),
            ("manual_min", "Manual minimum-input selection"),
            ("blocked", "Blocked assignment for this role"),
        ],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if mode is None:
        return "Role configuration cancelled."
    if mode == "auto":
        assignment = prefs.propose_prince2_roles()[role]
        prefs.set_prince2_role_assignment(
            role,
            mode="auto",
            provider=str(assignment["provider"]),
            provider_model=str(assignment["provider_model"]),
            params=dict(assignment.get("params", {})),
            account=assignment.get("account"),
            source="auto_proposal",
        )
        _model_views._save_model_preferences(config, prefs)
        _model_views._sync_prince2_roles_to_handoff(config, prefs)
        return f"Assigned {PRINCE2_ROLE_LABELS[role]} automatically."
    provider = _shell_views._prompt_menu_choice(
        title=f"Choose provider for {PRINCE2_ROLE_LABELS[role]}:",
        options=[(provider, provider) for provider in (prefs.enabled_models or list(SUPPORTED_MODELS))],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if provider is None:
        return "Role configuration cancelled."
    output_stream.write(_guided_provider_context(prefs, provider) + "\n")
    specs = list(provider_model_specs(provider))
    provider_model = _shell_views._prompt_menu_choice(
        title=f"Choose provider-model for {provider}:",
        options=[(spec.id, f"{spec.id} | {spec.label}") for spec in specs],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if provider_model is None:
        return "Role configuration cancelled."
    spec = provider_model_spec(provider, provider_model)
    params: dict[str, str] = {}
    if spec is not None and spec.reasoning_efforts:
        ordered_reasoning_efforts = list(spec.reasoning_efforts)
        if provider_model and "mini" not in provider_model.lower():
            ordered_reasoning_efforts = list(reversed(ordered_reasoning_efforts))
        reasoning = _shell_views._prompt_menu_choice(
            title=f"Choose reasoning_effort for {provider}:{provider_model}:",
            options=[
                (effort, f"{effort}{' (default)' if effort == spec.reasoning_default else ''}")
                for effort in ordered_reasoning_efforts
            ],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if reasoning is None:
            return "Role configuration cancelled."
        params["reasoning_effort"] = reasoning
    account_options = [("", "none")]
    account_options.extend((account, account) for account in (prefs.accounts_by_model or {}).get(provider, []))
    account = _shell_views._prompt_menu_choice(
        title=f"Choose account for {provider}:",
        options=account_options,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if account is None:
        return "Role configuration cancelled."
    assignment_mode = mode
    prefs.set_prince2_role_assignment(
        role,
        mode=assignment_mode,
        provider=provider,
        provider_model=provider_model,
        params=params,
        account=account or None,
        source="manual_menu" if assignment_mode == "manual" else "manual_min_menu" if assignment_mode == "manual_min" else "blocked_menu",
    )
    _model_views._save_model_preferences(config, prefs)
    _model_views._sync_prince2_roles_to_handoff(config, prefs)
    params_text = " ".join(f"{key}={value}" for key, value in sorted(params.items()))
    return (
        f"{'Blocked' if assignment_mode == 'blocked' else 'Assigned'} {PRINCE2_ROLE_LABELS[role]}: provider={provider} "
        f"provider_model={provider_model} account={account or 'none'}"
        + (f" {params_text}" if params_text else "")
        + "."
    )


def _guided_role_add_child(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided role node creation is available in the interactive shell. Run `python3 -m stagewarden.main` and use `/role add-child`."
    output_stream.write("PRINCE2 delegated node setup:\n")
    output_stream.write("- rule: delegated nodes inherit PRINCE2 role context but remain under parent accountability.\n")
    parent_id = _shell_views._prompt_menu_choice(
        title="Choose parent role-tree node:",
        options=_role_tree_node_options(config),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if parent_id is None:
        return "Role node creation cancelled."
    role_type = _shell_views._prompt_menu_choice(
        title="Choose delegated PRINCE2 role type:",
        options=_role_options(),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if role_type is None:
        return "Role node creation cancelled."
    output_stream.write("Optional node id, or blank for automatic id: ")
    output_stream.flush()
    response = input_stream.readline()
    if response == "":
        return "Role node creation cancelled."
    node_id = response.strip() or None
    try:
        child = _add_child_prince2_role_node(config, prefs, parent_id=parent_id, role_type=role_type, node_id=node_id)
    except ValueError as exc:
        return str(exc)
    return f"Added delegated PRINCE2 role node {child.get('node_id')} under {child.get('parent_id')}."


def _guided_role_assign(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided role node assignment is available in the interactive shell. Run `python3 -m stagewarden.main` and use `/role assign`."
    output_stream.write("PRINCE2 role-tree node assignment:\n")
    output_stream.write("- rule: choose a specific node so provider fallback does not widen context.\n")
    node_id = _shell_views._prompt_menu_choice(
        title="Choose role-tree node:",
        options=_role_tree_node_options(config),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if node_id is None:
        return "Role node assignment cancelled."
    pool = _shell_views._prompt_menu_choice(
        title=f"Choose assignment pool for {node_id}:",
        options=_route_pool_options(),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if pool is None:
        return "Role node assignment cancelled."
    output_stream.write(_guided_role_node_assignment_context(config, node_id, pool) + "\n")
    output_stream.write(_guided_provider_context(prefs) + "\n")
    provider = _shell_views._prompt_menu_choice(
        title=f"Choose provider for {node_id}:",
        options=_guided_provider_options_for_node(config, prefs, node_id=node_id, pool=pool),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if provider is None:
        return "Role node assignment cancelled."
    output_stream.write(_guided_provider_context(prefs, provider) + "\n")
    provider_model = _shell_views._prompt_menu_choice(
        title=f"Choose provider-model for {provider}:",
        options=_guided_provider_model_options_for_node(config, provider=provider, node_id=node_id, pool=pool),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if provider_model is None:
        return "Role node assignment cancelled."
    spec = provider_model_spec(provider, provider_model)
    params: dict[str, str] = {}
    if spec is not None and spec.reasoning_efforts:
        reasoning = _shell_views._prompt_menu_choice(
            title=f"Choose reasoning_effort for {provider}:{provider_model}:",
            options=[
                (effort, f"{effort}{' (default)' if effort == spec.reasoning_default else ''}")
                for effort in spec.reasoning_efforts
            ],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if reasoning is None:
            return "Role node assignment cancelled."
        params["reasoning_effort"] = reasoning
    account_options = [("", "none")]
    account_options.extend((account, account) for account in (prefs.accounts_by_model or {}).get(provider, []))
    account = _shell_views._prompt_menu_choice(
        title=f"Choose account for {provider}:",
        options=account_options,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if account is None:
        return "Role node assignment cancelled."
    try:
        node = _assign_prince2_role_node(
            config,
            prefs,
            node_id=node_id,
            provider=provider,
            provider_model=provider_model,
            params=params,
            account=account or None,
            pool=pool,
        )
    except ValueError as exc:
        return str(exc)
    assignment = node.get("assignment", {}) if isinstance(node.get("assignment"), dict) else {}
    params_text = " ".join(f"{key}={value}" for key, value in sorted(params.items()))
    if pool == "primary":
        provider_display = assignment.get("provider")
        provider_model_display = assignment.get("provider_model")
        account_display = assignment.get("account") or "none"
    else:
        pools = node.get("assignment_pool", {}) if isinstance(node.get("assignment_pool"), dict) else {}
        routes = pools.get(pool, []) if isinstance(pools.get(pool), list) else []
        route = routes[-1] if routes and isinstance(routes[-1], dict) else {}
        provider_display = route.get("provider")
        provider_model_display = route.get("provider_model")
        account_display = route.get("account") or "none"
    return (
        f"Assigned role node {node.get('node_id')}: provider={provider_display} "
        f"provider_model={provider_model_display} account={account_display}"
        + (f" {params_text}" if params_text else "")
        + f" pool={pool}"
        + "."
    )


def _guided_role_node_model_choice(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    node_id: str,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided PRINCE2 node model selection is available in the interactive shell. Run `python3 -m stagewarden.main` and use `role menu` or `role model`."
    node = _role_tree_node_record(config, node_id)
    if not node:
        return f"PRINCE2 node '{node_id}' not found."
    output_stream.write(_render_prince2_role_node_detail(config, node_id) + "\n")
    output_stream.write(_guided_role_node_assignment_context(config, node_id, "primary") + "\n")
    output_stream.write(_guided_provider_context(prefs) + "\n")
    choice = _shell_views._prompt_menu_choice(
        title=f"Choose provider-model for {node_id}:",
        options=_node_model_choice_options(config, node_id),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if choice is None:
        return "Role node model selection cancelled."
    parsed = _model_views._parse_catalog_model_choice(choice)
    if parsed is None:
        return f"Invalid provider-model choice '{choice}'."
    provider, provider_model = parsed
    spec = provider_model_spec(provider, provider_model)
    params: dict[str, str] = {}
    if spec is not None and spec.reasoning_efforts:
        current_reasoning = prefs.params_for_model(provider).get("reasoning_effort") or spec.reasoning_default or spec.reasoning_efforts[0]
        reasoning = _shell_views._prompt_menu_choice(
            title=f"Choose reasoning_effort for {provider}:{provider_model}:",
            options=[(effort, f"{effort}{' (default)' if effort == current_reasoning else ''}") for effort in spec.reasoning_efforts],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if reasoning is None:
            return "Role node model selection cancelled."
        params["reasoning_effort"] = reasoning
    account_options = [("", "none")]
    account_options.extend((account, account) for account in (prefs.accounts_by_model or {}).get(provider, []))
    account = _shell_views._prompt_menu_choice(
        title=f"Choose account for {provider}:",
        options=account_options,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if account is None:
        return "Role node model selection cancelled."
    try:
        node = _assign_prince2_role_node(
            config,
            prefs,
            node_id=node_id,
            provider=provider,
            provider_model=provider_model,
            params=params,
            account=account or None,
            pool="primary",
        )
    except ValueError as exc:
        return str(exc)
    return (
        f"Assigned role node {node.get('node_id')}: provider={node.get('assignment', {}).get('provider')} "
        f"provider_model={node.get('assignment', {}).get('provider_model')} account={node.get('assignment', {}).get('account') or 'none'} "
        f"{' '.join(f'{key}={value}' for key, value in sorted((node.get('assignment', {}).get('params', {}) or {}).items()))}".strip()
    ).strip()


def _guided_role_node_switch_agent(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    node_id: str,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided PRINCE2 node agent switching is available in the interactive shell. Run `python3 -m stagewarden.main` and use `role menu`, `role shell`, or `role switch`."
    node = _role_tree_node_record(config, node_id)
    if not node:
        return f"PRINCE2 node '{node_id}' not found."
    recommendation = _project_model_recommendation._node_model_recommendation(config, node)
    current = recommendation.get("current", {}) if isinstance(recommendation.get("current"), dict) else {}
    suggested = recommendation.get("suggested", {}) if isinstance(recommendation.get("suggested"), dict) else {}
    output_stream.write("KiloCode-style switch agent:\n")
    output_stream.write(_render_prince2_role_node_detail(config, node_id) + "\n")
    output_stream.write(
        "- switch_summary: "
        f"current={current.get('provider') or 'none'}:{current.get('provider_model') or 'none'} "
        f"direction={recommendation.get('direction', 'hold')} "
        f"suggested={suggested.get('provider') or 'none'}:{suggested.get('provider_model') or 'none'}\n"
    )
    output_stream.write(_guided_role_node_assignment_context(config, node_id, "primary") + "\n")
    output_stream.write("Switching agent means choosing a new provider-model for this node.\n")
    return _guided_role_node_model_choice(
        prefs=prefs,
        config=config,
        node_id=node_id,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _guided_role_node_menu(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    node_id: str,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided PRINCE2 node menu is available in the interactive shell. Run `python3 -m stagewarden.main` and use `role menu`."
    current = node_id
    while True:
        node = _role_tree_node_record(config, current)
        if not node:
            return f"PRINCE2 node '{current}' not found."
        output_stream.write(_render_prince2_role_node_detail(config, current) + "\n")
        action = _shell_views._prompt_menu_choice(
            title=f"Node menu for {current}:",
            options=[
                ("view", "View node detail again"),
                ("shell", "Open node shell and navigate between nodes"),
                ("switch-agent", "Switch agent/model for this node"),
                ("model", "Change model assignment"),
                ("auto-model", "Auto-pick a stronger or lighter model from the menu"),
                ("tolerance", "Adjust tolerance margin"),
                ("reset-tolerance", "Reset tolerance from project brief"),
                ("add-child", "Add delegated child node"),
                ("remove", "Remove this node"),
                ("back", "Back"),
            ],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if action is None or action == "back":
            return f"Closed node menu for {current}."
        if action == "view":
            output_stream.write(_render_prince2_role_node_detail(config, current) + "\n")
            continue
        if action == "shell":
            output_stream.write(_guided_role_node_shell(prefs=prefs, config=config, node_id=current, input_stream=input_stream, output_stream=output_stream) + "\n")
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "switch-agent":
            output_stream.write(_guided_role_node_switch_agent(prefs=prefs, config=config, node_id=current, input_stream=input_stream, output_stream=output_stream) + "\n")
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "model":
            output_stream.write(_guided_role_node_model_choice(prefs=prefs, config=config, node_id=current, input_stream=input_stream, output_stream=output_stream) + "\n")
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "auto-model":
            recommendation = _project_model_recommendation._node_model_recommendation(config, node)
            suggested = recommendation.get("suggested", {}) if isinstance(recommendation.get("suggested"), dict) else {}
            provider = str(suggested.get("provider", "")).strip()
            provider_model = str(suggested.get("provider_model", "")).strip()
            if not provider or not provider_model:
                output_stream.write("No automatic model suggestion is available for this node.\n")
                continue
            spec = provider_model_spec(provider, provider_model)
            params: dict[str, str] = {}
            if spec is not None and spec.reasoning_efforts:
                preferred = prefs.params_for_model(provider).get("reasoning_effort") or spec.reasoning_default or spec.reasoning_efforts[0]
                if preferred not in spec.reasoning_efforts:
                    preferred = spec.reasoning_default or spec.reasoning_efforts[0]
                params["reasoning_effort"] = preferred
            try:
                updated = _assign_prince2_role_node(
                    config,
                    prefs,
                    node_id=current,
                    provider=provider,
                    provider_model=provider_model,
                    params=params,
                    account=(prefs.account_for_model(provider) if provider in (prefs.accounts_by_model or {}) else None),
                    pool="primary",
                )
            except ValueError as exc:
                output_stream.write(str(exc) + "\n")
                continue
            output_stream.write(
                f"Auto model switch applied: provider={updated.get('assignment', {}).get('provider')} "
                f"provider_model={updated.get('assignment', {}).get('provider_model')}\n"
            )
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "tolerance":
            output_stream.write("Set new tolerance margin percent: ")
            output_stream.flush()
            response = input_stream.readline()
            if response == "":
                return "Node menu cancelled."
            try:
                margin = float(response.strip().rstrip("%"))
            except ValueError:
                output_stream.write("Invalid margin. Enter a numeric percentage.\n")
                continue
            try:
                updated = _set_prince2_role_node_tolerance_margin(config, prefs, node_id=current, margin_percent=margin)
            except ValueError as exc:
                output_stream.write(str(exc) + "\n")
                continue
            output_stream.write(
                f"Updated tolerance margin for {current}: margin={updated.get('tolerance_margin_percent', 'unknown')}.\n"
            )
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "reset-tolerance":
            updated = _reset_prince2_role_node_tolerance(config, prefs, node_id=current)
            output_stream.write(
                f"Reset tolerance for {current}: margin={updated.get('tolerance_margin_percent', 'unknown')} pressure={updated.get('tolerance_pressure_percent', 'unknown')}.\n"
            )
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "add-child":
            output_stream.write(_guided_role_add_child(prefs=prefs, config=config, input_stream=input_stream, output_stream=output_stream) + "\n")
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "remove":
            output_stream.write("Reparent direct children to the parent of this node? [yes/no]: ")
            output_stream.flush()
            response = input_stream.readline()
            if response == "":
                return "Node menu cancelled."
            reparent = response.strip().lower() in {"y", "yes", "true", "1"}
            try:
                removed = _remove_prince2_role_node(config, prefs, node_id=current, reparent_children=reparent)
            except ValueError as exc:
                output_stream.write(str(exc) + "\n")
                continue
            output_stream.write(
                f"Removed PRINCE2 role node {removed.get('node_id', current)}.\n"
            )
            prefs = _model_views._load_model_preferences(config)
            return f"Removed PRINCE2 role node {current}."


def _guided_role_shell(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided PRINCE2 role shell navigation is available in the interactive shell. Run `python3 -m stagewarden.main` and use `roles shell`."
    output_stream.write("PRINCE2 node shell navigator:\n")
    output_stream.write("- rule: choose a node and move with parent, sibling, or child hops.\n")
    node_id = _shell_views._prompt_menu_choice(
        title="Choose starting node:",
        options=_role_tree_node_options(config),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if node_id is None:
        return "Role shell navigation cancelled."
    return _guided_role_node_shell(
        prefs=prefs,
        config=config,
        node_id=node_id,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _guided_role_node_shell(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    node_id: str,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided PRINCE2 node shell is available in the interactive shell. Run `python3 -m stagewarden.main` and use `role shell`."
    current = node_id
    while True:
        node = _role_tree_node_record(config, current)
        if not node:
            return f"PRINCE2 node '{current}' not found."
        output_stream.write(_render_prince2_role_node_shell(config, current) + "\n")
        action = _shell_views._prompt_menu_choice(
            title=f"Node shell for {current}:",
            options=[
                ("parent", "Go to parent node"),
                ("prev", "Go to previous sibling"),
                ("next", "Go to next sibling"),
                ("child", "Choose one child node"),
                ("jump", "Jump to another node"),
                ("menu", "Open the node menu"),
                ("switch", "Switch agent/model for this node"),
                ("tree", "Show the full role tree"),
                ("back", "Close node shell"),
            ],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if action is None or action == "back":
            return f"Closed node shell for {current}."
        if action == "tree":
            output_stream.write(_project_role_tree_views._render_prince2_role_tree(config) + "\n")
            continue
        if action == "menu":
            output_stream.write(_guided_role_node_menu(prefs=prefs, config=config, node_id=current, input_stream=input_stream, output_stream=output_stream) + "\n")
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "switch":
            output_stream.write(_guided_role_node_switch_agent(prefs=prefs, config=config, node_id=current, input_stream=input_stream, output_stream=output_stream) + "\n")
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "jump":
            next_node = _shell_views._prompt_menu_choice(
                title="Jump to node:",
                options=_role_tree_node_options(config),
                input_stream=input_stream,
                output_stream=output_stream,
            )
            if next_node is None:
                continue
            current = next_node
            continue
        navigation = _role_tree_node_navigation(config, current)
        if action == "parent":
            parent_id = navigation.get("parent_id")
            if not parent_id:
                output_stream.write("Current node has no parent.\n")
                continue
            current = str(parent_id)
            continue
        if action == "prev":
            previous = navigation.get("previous_sibling")
            if not previous:
                output_stream.write("No previous sibling is available.\n")
                continue
            current = str(previous)
            continue
        if action == "next":
            next_sibling = navigation.get("next_sibling")
            if not next_sibling:
                output_stream.write("No next sibling is available.\n")
                continue
            current = str(next_sibling)
            continue
        if action == "child":
            children = _role_tree_node_children(config, current)
            if not children:
                output_stream.write("Current node has no children.\n")
                continue
            child_choice = _shell_views._prompt_menu_choice(
                title=f"Choose child of {current}:",
                options=[(str(item.get("node_id")), f"{item.get('label')} [{item.get('node_id')}]") for item in children if str(item.get("node_id", "")).strip()],
                input_stream=input_stream,
                output_stream=output_stream,
            )
            if child_choice is None:
                continue
            current = child_choice
            continue


def _guided_role_tree_menu(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        return "Guided PRINCE2 tree menu is available in the interactive shell. Run `python3 -m stagewarden.main` and use `roles menu`."
    while True:
        output_stream.write(_project_role_tree_views._render_prince2_role_tree(config) + "\n")
        action = _shell_views._prompt_menu_choice(
            title="PRINCE2 tree menu:",
            options=[
                ("node", "Open a node menu"),
                ("shell", "Open a node shell"),
                ("add-child", "Add delegated node"),
                ("remove", "Remove a node"),
                ("approve", "Approve the current baseline"),
                ("refresh", "Refresh tree view"),
                ("back", "Back"),
            ],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if action is None or action == "back":
            return "PRINCE2 tree menu closed."
        if action == "node":
            node_id = _shell_views._prompt_menu_choice(
                title="Choose role-tree node:",
                options=_role_tree_node_options(config),
                input_stream=input_stream,
                output_stream=output_stream,
            )
            if node_id is None:
                continue
            output_stream.write(_guided_role_node_menu(prefs=prefs, config=config, node_id=node_id, input_stream=input_stream, output_stream=output_stream) + "\n")
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "shell":
            node_id = _shell_views._prompt_menu_choice(
                title="Choose role-tree node:",
                options=_role_tree_node_options(config),
                input_stream=input_stream,
                output_stream=output_stream,
            )
            if node_id is None:
                continue
            output_stream.write(_guided_role_node_shell(prefs=prefs, config=config, node_id=node_id, input_stream=input_stream, output_stream=output_stream) + "\n")
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "add-child":
            output_stream.write(_guided_role_add_child(prefs=prefs, config=config, input_stream=input_stream, output_stream=output_stream) + "\n")
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "remove":
            node_id = _shell_views._prompt_menu_choice(
                title="Choose role-tree node to remove:",
                options=_role_tree_node_options(config),
                input_stream=input_stream,
                output_stream=output_stream,
            )
            if node_id is None:
                continue
            output_stream.write("Reparent direct children to the removed node's parent? [yes/no]: ")
            output_stream.flush()
            response = input_stream.readline()
            if response == "":
                return "PRINCE2 tree menu cancelled."
            reparent = response.strip().lower() in {"y", "yes", "true", "1"}
            try:
                _remove_prince2_role_node(config, prefs, node_id=node_id, reparent_children=reparent)
            except ValueError as exc:
                output_stream.write(str(exc) + "\n")
                continue
            output_stream.write(f"Removed PRINCE2 role node {node_id}.\n")
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "approve":
            _approve_prince2_role_tree_baseline(config, prefs, source="roles_tree_menu")
            output_stream.write("Approved PRINCE2 role-tree baseline from menu.\n")
            prefs = _model_views._load_model_preferences(config)
            continue
        if action == "refresh":
            output_stream.write(_project_role_tree_views._render_prince2_role_tree(config) + "\n")
            continue


def _guided_roles_setup(
    *,
    prefs: ModelPreferences,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
) -> str:
    if input_stream is None or output_stream is None:
        prefs.apply_prince2_role_proposal()
        _model_views._save_model_preferences(config, prefs)
        _approve_prince2_role_tree_baseline(config, prefs, source="roles_setup_auto")
        return "Applied automatic PRINCE2 role proposal."
    choice = _shell_views._prompt_menu_choice(
        title="PRINCE2 role setup:",
        options=[
            ("auto", "Automatic proposal based on available providers/accounts/models"),
            ("manual", "Manual configuration role by role"),
            ("show", "Show current assignments only"),
        ],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if choice is None:
        return "Role setup cancelled."
    if choice == "show":
        return _project_role_views._render_prince2_roles(config)
    if choice == "auto":
        prefs.apply_prince2_role_proposal()
        _model_views._save_model_preferences(config, prefs)
        _approve_prince2_role_tree_baseline(config, prefs, source="roles_setup_auto")
        return (
            "Applied automatic PRINCE2 role proposal.\n"
            + _project_role_views._render_prince2_roles(config)
            + "\n"
            + _project_role_tree_views._render_prince2_role_tree_baseline(config)
        )
    while True:
        role = _shell_views._prompt_menu_choice(
            title="Choose role to configure, or `done`:",
            options=[("done", "done")] + _role_options(),
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if role is None or role == "done":
            break
        output_stream.write(
            _guided_role_configure(
                requested_role=role,
                prefs=prefs,
                config=config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
            + "\n"
        )
        output_stream.flush()
        prefs = _model_views._load_model_preferences(config)
    local_execution = _model_views._local_execution_candidates_report(config)
    candidates = [item for item in local_execution.get("candidates", []) if isinstance(item, dict)]
    if candidates:
        output_stream.write(
            "Recommended local fallback candidates discovered: "
            + ", ".join(str(item.get("id", "")) for item in candidates if str(item.get("id", "")).strip())
            + "\n"
        )
        preload = _shell_views._prompt_menu_choice(
            title="Approve baseline with recommended local delivery fallbacks now?",
            options=[
                ("yes", "Yes - approve baseline and preload recommended local fallback routes"),
                ("no", "No - keep only role assignments for now"),
            ],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if preload is None:
            return "Role setup cancelled."
        if preload == "yes":
            _approve_prince2_role_tree_baseline(config, prefs, source="roles_setup_manual_local_fallbacks")
            return (
                "Role setup completed with approved baseline and recommended local delivery fallbacks.\n"
                + _project_role_views._render_prince2_roles(config)
                + "\n"
                + _project_role_tree_views._render_prince2_role_tree_baseline(config)
            )
    return "Role setup completed.\n" + _project_role_views._render_prince2_roles(config)
