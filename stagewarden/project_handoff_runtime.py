from __future__ import annotations

from pathlib import Path
from typing import Any

from .model_catalog import catalog_entry_for_provider_model, load_ai_models_catalog
from .prince2 import PRINCE2_THEME_NAMES
from .role_tree import prince2_node_description
from .textcodec import dumps_ascii, loads_text, read_text_utf8, round_usd, utc_now, write_text_utf8


def _safe_price_per_token(value: object) -> float | None:
    try:
        price = float(str(value))
    except (TypeError, ValueError):
        return None
    return None if price < 0 else price


def send_prince2_node_message(
    handoff: Any,
    *,
    source_node: str,
    target_node: str,
    edge_id: str,
    payload_scope: list[str],
    evidence_refs: list[str] | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    baseline = handoff.prince2_role_tree_baseline if isinstance(handoff.prince2_role_tree_baseline, dict) else {}
    flow = baseline.get("flow", {}) if isinstance(baseline.get("flow"), dict) else {}
    edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
    if not runtime:
        raise ValueError("No materialized PRINCE2 node runtime. Approve a role-tree baseline first.")
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    source = next((node for node in nodes if str(node.get("node_id", "")).strip() == source_node), None)
    target = next((node for node in nodes if str(node.get("node_id", "")).strip() == target_node), None)
    if source is None:
        raise ValueError(f"Source node '{source_node}' not found in PRINCE2 node runtime.")
    if target is None:
        raise ValueError(f"Target node '{target_node}' not found in PRINCE2 node runtime.")
    edge = next(
        (
            item
            for item in edges
            if str(item.get("edge_id", "")).strip() == edge_id
            and str(item.get("source_node", "")).strip() == source_node
            and str(item.get("target_node", "")).strip() == target_node
        ),
        None,
    )
    if edge is None:
        raise ValueError(
            f"Unauthorized PRINCE2 flow edge '{edge_id}' for {source_node} -> {target_node}."
        )
    clean_payload = [str(item).strip() for item in payload_scope if str(item).strip()]
    if not clean_payload:
        raise ValueError("Message payload scope cannot be empty.")
    allowed_payload = {str(item).strip() for item in edge.get("payload_scope", []) if str(item).strip()}
    invalid_payload = [item for item in clean_payload if item not in allowed_payload]
    if invalid_payload:
        raise ValueError("Payload scope exceeds authorized PRINCE2 flow edge: " + ", ".join(invalid_payload))
    evidence = [str(item).strip() for item in (evidence_refs or []) if str(item).strip()]
    message_id = f"msg-{len(handoff.entries) + len(clean_payload) + len(evidence) + 1}-{utc_now().replace(':', '').replace('-', '')}"
    message = {
        "message_id": message_id,
        "timestamp": utc_now(),
        "source_node": source_node,
        "target_node": target_node,
        "edge_id": edge_id,
        "flow_type": str(edge.get("flow_type", "")),
        "payload_scope": clean_payload,
        "expected_evidence": [str(item) for item in edge.get("expected_evidence", []) if str(item).strip()],
        "evidence_refs": evidence,
        "validation_condition": str(edge.get("validation_condition", "")),
        "decision_authority": str(edge.get("decision_authority", "")),
        "return_path": str(edge.get("return_path", "")),
        "status": "queued",
        "summary": (summary or f"{edge_id} message").strip()[:240],
    }
    source.setdefault("outbox", [])
    target.setdefault("inbox", [])
    if not isinstance(source["outbox"], list):
        source["outbox"] = []
    if not isinstance(target["inbox"], list):
        target["inbox"] = []
    source["outbox"].append(dict(message))
    target["inbox"].append(dict(message))
    source["outbox_count"] = len(source["outbox"])
    target["inbox_count"] = len(target["inbox"])
    source["last_transition_at"] = message["timestamp"]
    target["last_transition_at"] = message["timestamp"]
    message_tokens = max(1, len(" ".join(clean_payload + evidence + [message["summary"]]).split()))
    handoff._bump_node_thread_tokens(
        source,
        output_tokens=message_tokens,
        bucket=handoff._node_flow_bucket(str(edge.get("flow_type", ""))),
    )
    handoff._bump_node_thread_tokens(
        target,
        input_tokens=message_tokens,
        bucket="business_case",
    )
    if str(target.get("state", "idle")).strip().lower() in {"idle", "waiting"}:
        target["state"] = "ready"
    if str(target.get("wait_status", "none")).strip().lower() != "none":
        target["wait_status"] = "message_received"
    handoff.prince2_node_runtime["nodes"] = nodes
    handoff.updated_at = utc_now()
    return message


def set_prince2_node_waiting(
    handoff: Any,
    *,
    node_id: str,
    reason: str,
    wake_triggers: list[str] | None = None,
) -> dict[str, Any]:
    node = handoff._prince2_runtime_node(node_id)
    clean_reason = str(reason).strip()
    if not clean_reason:
        raise ValueError("Wait reason cannot be empty.")
    node["state"] = "waiting"
    node["wait_status"] = "waiting_for_trigger"
    node["wait_reason"] = clean_reason[:240]
    if wake_triggers is not None:
        node["wake_triggers"] = [str(item).strip() for item in wake_triggers if str(item).strip()]
    node["last_transition_at"] = utc_now()
    handoff.updated_at = utc_now()
    return dict(node)


def wake_prince2_node(
    handoff: Any,
    *,
    node_id: str,
    trigger: str,
) -> dict[str, Any]:
    node = handoff._prince2_runtime_node(node_id)
    clean_trigger = str(trigger).strip()
    if not clean_trigger:
        raise ValueError("Wake trigger cannot be empty.")
    allowed = [str(item).strip() for item in node.get("wake_triggers", []) if str(item).strip()]
    inbox = [dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]
    trigger_allowed = clean_trigger in allowed
    message_allowed = clean_trigger == "message_received" and bool(inbox)
    if not trigger_allowed and not message_allowed:
        raise ValueError(
            f"Wake trigger '{clean_trigger}' is not authorized for node '{node_id}'."
        )
    node["state"] = "ready"
    node["wait_status"] = "none"
    node["wait_reason"] = None
    node["last_transition_at"] = utc_now()
    handoff.updated_at = utc_now()
    return dict(node)


def tick_prince2_node(handoff: Any, *, node_id: str) -> dict[str, Any]:
    node = handoff._prince2_runtime_node(node_id)
    state = handoff._node_tolerance_state(node)
    if state == "escalated":
        spawned_child = handoff._spawn_prince2_escalation_child(
            node_id=node_id,
            reason="tolerance_margin_exceeded",
        )
        antagonist_profile = handoff._node_antagonist_profile(node)
        node["state"] = "escalated"
        node["wait_status"] = "none"
        node["wait_reason"] = None
        node["last_transition_at"] = utc_now()
        handoff.updated_at = utc_now()
        return {
            "node_id": node_id,
            "state": "escalated",
            "reason": "tolerance_margin_exceeded",
            "escalation_target": str(node.get("escalation_target", "board.executive")),
            "antagonist_name": antagonist_profile.get("antagonist_name", "unknown"),
            "antagonist_pressure_percent": antagonist_profile.get("decision_kpis", {}).get("antagonist_pressure_percent", 0.0)
            if isinstance(antagonist_profile.get("decision_kpis", {}), dict)
            else 0.0,
            "devil_advocate": antagonist_profile.get("devil_advocate", ""),
            "evidence_signals": list(antagonist_profile.get("evidence_signals", []))
            if isinstance(antagonist_profile.get("evidence_signals", []), list)
            else [],
            "evidence_refs": list(antagonist_profile.get("evidence_refs", []))
            if isinstance(antagonist_profile.get("evidence_refs", []), list)
            else [],
            "decision_kpis": dict(antagonist_profile.get("decision_kpis", {}))
            if isinstance(antagonist_profile.get("decision_kpis", {}), dict)
            else {},
            "spawned_child": spawned_child,
            "consumed_message": None,
            "remaining_inbox": len([dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]),
        }
    if state == "completed":
        return {
            "node_id": node_id,
            "state": "completed",
            "consumed_message": None,
            "remaining_inbox": len([dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]),
        }
    if state == "waiting":
        raise ValueError(f"Node '{node_id}' is waiting and cannot tick until woken.")
    inbox = [dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]
    now = utc_now()
    if inbox:
        message = inbox.pop(0)
        message["status"] = "consumed"
        message["consumed_at"] = now
        node["inbox"] = inbox
        node["inbox_count"] = len(inbox)
        node.setdefault("transcript_refs", [])
        if not isinstance(node["transcript_refs"], list):
            node["transcript_refs"] = []
        node["transcript_refs"].append(f"message:{message.get('message_id', 'unknown')}")
        node["state"] = "running"
        node["wait_status"] = "none"
        node["wait_reason"] = None
        node["last_transition_at"] = now
        handoff.updated_at = now
        return {
            "node_id": node_id,
            "state": "running",
            "consumed_message": dict(message),
            "remaining_inbox": len(inbox),
        }
    if state in {"ready", "running"}:
        node["state"] = "completed"
        node["wait_status"] = "none"
        node["wait_reason"] = None
        node["last_transition_at"] = now
        handoff.updated_at = now
        return {
            "node_id": node_id,
            "state": "completed",
            "consumed_message": None,
            "remaining_inbox": 0,
        }
    if state == "completed":
        return {
            "node_id": node_id,
            "state": "completed",
            "consumed_message": None,
            "remaining_inbox": len(inbox),
        }
    raise ValueError(f"Node '{node_id}' is not ready to tick from state '{state}'.")


def tick_prince2_runtime(handoff: Any, *, max_nodes: int | None = None) -> dict[str, Any]:
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    if not runtime:
        raise ValueError("No materialized PRINCE2 node runtime. Approve a role-tree baseline first.")
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    if not nodes:
        raise ValueError("No materialized PRINCE2 nodes are available to tick.")
    limit = max_nodes if isinstance(max_nodes, int) and max_nodes > 0 else len(nodes)
    processed = 0
    woken = 0
    progressed = 0
    escalated = 0
    spawned_children = 0
    skipped = 0
    results: list[dict[str, Any]] = []
    for node in nodes:
        if processed >= limit:
            break
        node_id = str(node.get("node_id", "")).strip()
        if not node_id:
            continue
        processed += 1
        state = str(node.get("state", "idle")).strip().lower() or "idle"
        inbox = [dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]
        if state == "waiting" and inbox:
            allowed = [str(item).strip() for item in node.get("wake_triggers", []) if str(item).strip()]
            if "message_received" in allowed:
                woke_node = handoff.wake_prince2_node(node_id=node_id, trigger="message_received")
                state = str(woke_node.get("state", "ready")).strip().lower() or "ready"
                woken += 1
                results.append(
                    {
                        "node_id": node_id,
                        "action": "wake",
                        "state": state,
                        "reason": "message_received",
                    }
                )
            else:
                skipped += 1
                results.append(
                    {
                        "node_id": node_id,
                        "action": "skip",
                        "state": state,
                        "reason": "message_waiting_without_authorized_trigger",
                    }
                )
                continue
        tolerance_state = handoff._node_tolerance_state(node)
        if tolerance_state == "escalated":
            tick = handoff.tick_prince2_node(node_id=node_id)
            escalated += 1
            spawned_child = tick.get("spawned_child") if isinstance(tick.get("spawned_child"), dict) else None
            if spawned_child is not None:
                spawned_children += 1
            results.append(
                {
                    "node_id": node_id,
                    "action": "escalate",
                    "state": tick.get("state", "escalated"),
                    "reason": tick.get("reason", "tolerance_margin_exceeded"),
                    "margin_percent": handoff._node_tolerance_margin(node),
                    "pressure_percent": handoff._node_tolerance_pressure(node),
                    "spawned_child": spawned_child,
                }
            )
            continue
        if state in {"ready", "running", "completed"}:
            tick = handoff.tick_prince2_node(node_id=node_id)
            if tick.get("state") == "escalated":
                escalated += 1
                spawned_child = tick.get("spawned_child") if isinstance(tick.get("spawned_child"), dict) else None
                if spawned_child is not None:
                    spawned_children += 1
                results.append(
                    {
                        "node_id": node_id,
                        "action": "escalate",
                        "state": tick.get("state", "escalated"),
                        "reason": tick.get("reason", "tolerance_margin_exceeded"),
                        "margin_percent": handoff._node_tolerance_margin(node),
                        "pressure_percent": handoff._node_tolerance_pressure(node),
                        "spawned_child": spawned_child,
                    }
                )
                continue
            progressed += 1
            results.append(
                {
                    "node_id": node_id,
                    "action": "tick",
                    "state": tick.get("state", state),
                    "consumed_message": tick.get("consumed_message"),
                    "remaining_inbox": tick.get("remaining_inbox", 0),
                }
            )
            continue
        skipped += 1
        results.append(
            {
                "node_id": node_id,
                "action": "skip",
                "state": state,
                "reason": "not_ready",
            }
        )
    handoff.updated_at = utc_now()
    return {
        "command": "roles tick",
        "processed": processed,
        "woken": woken,
        "progressed": progressed,
        "escalated": escalated,
        "spawned_children": spawned_children,
        "skipped": skipped,
        "max_nodes": limit,
        "results": results,
        "summary": handoff.prince2_node_runtime_summary(),
    }


def as_dict(handoff: Any) -> dict[str, Any]:
    return {
        "_format": "stagewarden_project_handoff",
        "_version": 1,
        "task": handoff.task,
        "goal": dict(handoff.goal),
        "project_budget": dict(handoff.project_budget),
        "user_question": dict(handoff.user_question),
        "user_question_log": [dict(item) for item in handoff.user_question_log],
        "project_brief": dict(handoff.project_brief),
        "status": handoff.status,
        "waiting_reason": handoff.waiting_reason,
        "current_step_id": handoff.current_step_id,
        "current_step_title": handoff.current_step_title,
        "current_step_status": handoff.current_step_status,
        "latest_observation": handoff.latest_observation,
        "plan_status": handoff.plan_status,
        "git_head": handoff.git_head,
        "git_head_baseline": handoff.git_head_baseline,
        "risk_register": list(handoff.risk_register),
        "issue_register": list(handoff.issue_register),
        "quality_register": list(handoff.quality_register),
        "lessons_log": list(handoff.lessons_log),
        "exception_plan": list(handoff.exception_plan),
        "implementation_backlog": list(handoff.implementation_backlog),
        "prince2_roles": {role: dict(assignment) for role, assignment in handoff.prince2_roles.items()},
        "prince2_role_tree_baseline": dict(handoff.prince2_role_tree_baseline),
        "prince2_node_runtime": dict(handoff.prince2_node_runtime),
        "updated_at": handoff.updated_at,
        "entries": [entry.as_dict() for entry in handoff.entries],
    }


def save(handoff: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_utf8(path, dumps_ascii(as_dict(handoff), indent=2))


def record_issue(handoff: Any, *, step_id: str, severity: str, summary: str) -> None:
    handoff.issue_register.append(
        {
            "step_id": step_id,
            "severity": severity,
            "summary": summary[:240],
            "status": "open",
            "recorded_at": utc_now(),
        }
    )


def record_quality(handoff: Any, *, step_id: str, status: str, evidence: str) -> None:
    handoff.quality_register.append(
        {"step_id": step_id, "status": status, "evidence": evidence[:240], "recorded_at": utc_now()}
    )


def record_lesson(handoff: Any, *, step_id: str, lesson_type: str, lesson: str) -> None:
    handoff.lessons_log.append(
        {"step_id": step_id, "type": lesson_type, "lesson": lesson[:240], "recorded_at": utc_now()}
    )


def update_project_brief(handoff: Any, updates: dict[str, str]) -> None:
    for key, value in updates.items():
        clean_key = str(key).strip().lower()
        clean_value = str(value).strip()
        if not clean_key:
            continue
        if clean_value:
            handoff.project_brief[clean_key] = clean_value[:1000]
        elif clean_key in handoff.project_brief:
            del handoff.project_brief[clean_key]
    handoff.updated_at = utc_now()


def clear_project_brief(handoff: Any, field_name: str | None = None) -> None:
    if field_name is None:
        handoff.project_brief = {}
    else:
        handoff.project_brief.pop(field_name.strip().lower(), None)
    handoff.updated_at = utc_now()


def close_issues_for_step(handoff: Any, *, step_id: str, resolution: str) -> None:
    for item in handoff.issue_register:
        if str(item.get("step_id", "")).strip() != step_id:
            continue
        if str(item.get("status", "open")).strip().lower() == "closed":
            continue
        item["status"] = "closed"
        item["resolved_at"] = utc_now()
        item["resolution"] = resolution[:240]


def close_all_open_issues(handoff: Any, *, resolution: str) -> None:
    for item in handoff.issue_register:
        if str(item.get("status", "open")).strip().lower() == "closed":
            continue
        item["status"] = "closed"
        item["resolved_at"] = utc_now()
        item["resolution"] = resolution[:240]


def close_all_open_risks(handoff: Any, *, resolution: str) -> None:
    for item in handoff.risk_register:
        if str(item.get("status", "open")).strip().lower() == "closed":
            continue
        item["status"] = "closed"
        item["resolved_at"] = utc_now()
        item["resolution"] = resolution[:240]


def finalize_quality_register(handoff: Any, *, resolution: str) -> None:
    for item in handoff.quality_register:
        status = str(item.get("status", "")).strip().lower()
        if status in {"accepted", "closed"}:
            continue
        item["status"] = "accepted"
        item["accepted_at"] = utc_now()
        item["resolution"] = resolution[:240]


def clear_exception_plan_if_recovered(handoff: Any) -> None:
    if not handoff.exception_plan:
        return
    open_issues = [
        item
        for item in handoff.issue_register
        if str(item.get("status", "open")).strip().lower() != "closed"
    ]
    if not open_issues:
        handoff.exception_plan = []


def _seed_risk_register(handoff: Any, risks: list[Any]) -> None:
    if handoff.risk_register:
        return
    for item in risks:
        text = str(item).strip()
        if not text:
            continue
        handoff.risk_register.append({"risk": text[:240], "status": "open", "recorded_at": utc_now()})


def _build_exception_plan(handoff: Any) -> None:
    if handoff.exception_plan:
        return
    current_step = handoff.current_step_id or "unknown-step"
    handoff.exception_plan = [
        f"review boundary for {current_step}",
        "inspect latest issue register and failed observations",
        "prepare controlled corrective action with wet-run validation",
    ]


def _register_status_summary(handoff: Any) -> dict[str, int]:
    risks_open = sum(1 for item in handoff.risk_register if str(item.get("status", "open")).strip().lower() != "closed")
    risks_closed = len(handoff.risk_register) - risks_open
    issues_open = sum(1 for item in handoff.issue_register if str(item.get("status", "open")).strip().lower() != "closed")
    issues_closed = len(handoff.issue_register) - issues_open
    quality_accepted = sum(
        1 for item in handoff.quality_register if str(item.get("status", "")).strip().lower() in {"accepted", "closed"}
    )
    quality_open = len(handoff.quality_register) - quality_accepted
    return {
        "risks_open": risks_open,
        "risks_closed": risks_closed,
        "issues_open": issues_open,
        "issues_closed": issues_closed,
        "quality_open": quality_open,
        "quality_accepted": quality_accepted,
    }


def _stage_health(
    handoff: Any,
    boundary_decision: str,
    active_step: dict[str, object] | None,
    register_statuses: dict[str, int],
    backlog_statuses: dict[str, int],
) -> str:
    if handoff.status == "waiting":
        return "waiting"
    if handoff.status == "exception" or boundary_decision.startswith("review_boundary:exception"):
        return "exception"
    if backlog_statuses["blocked"] > 0:
        return "blocked"
    if register_statuses["issues_open"] > 0 or handoff.exception_plan:
        return "at_risk"
    if active_step:
        return "active"
    if boundary_decision == "close_project":
        return "ready_to_close"
    return "stable"


def _next_action(
    handoff: Any,
    boundary_decision: str,
    active_step: dict[str, object] | None,
    stage_health: str,
    backlog_statuses: dict[str, int],
    recovery_state: str,
) -> str:
    if handoff.status == "waiting":
        if handoff.waiting_reason == "clarification":
            return "answer the pending clarification question and rerun the task"
        return "resume suspended session when connectivity returns"
    if recovery_state == "recovery_active":
        return "execute recovery lane and confirm wet-run before re-baseline"
    if recovery_state == "recovery_cleared":
        return "clear exception controls and resume planned stages"
    if stage_health == "exception":
        return "execute exception plan and re-baseline the current stage"
    if stage_health == "blocked":
        return "resolve blocking issues and promote the next ready stage"
    if boundary_decision == "review_boundary:open_issues":
        return "close remaining open issues before project closure"
    if boundary_decision == "close_project":
        return "authorize project closure"
    if active_step:
        return f"continue {active_step.get('id', 'current-step')}"
    if backlog_statuses["ready"] > 0:
        next_ready = next(
            (item.get("step_id", "next-step") for item in handoff.implementation_backlog if str(item.get("status", "")).strip().lower() == "ready"),
            "next-step",
        )
        return f"start {next_ready}"
    if stage_health == "stable":
        return "review current handoff and confirm next stage"
    return "review boundary and decide next controlled action"


def _parse_plan_status(handoff: Any, value: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for item in (value or "").split(","):
        key, separator, status = item.partition(":")
        if not separator:
            continue
        clean_key = key.strip()
        clean_status = status.strip()
        if clean_key and clean_status:
            statuses[clean_key] = clean_status
    return statuses


def _boundary_decision(handoff: Any, status_by_step: dict[str, str]) -> str:
    if not status_by_step:
        return "review_boundary:no_plan_status"
    open_issues = [
        item
        for item in handoff.issue_register
        if str(item.get("status", "open")).strip().lower() != "closed"
    ]
    if handoff.status == "exception" and handoff.exception_plan:
        return "review_boundary:exception_plan"
    values = list(status_by_step.values())
    if any(status in {"failed", "exception"} for status in values):
        return "review_boundary:exception_path"
    if all(status == "completed" for status in values):
        if open_issues:
            return "review_boundary:open_issues"
        return "close_project"
    if any(status in {"pending", "planned", "ready", "in_progress"} for status in values):
        return "continue_current_stage"
    return "review_boundary:manual_check"


def _recovery_state(handoff: Any, status_by_step: dict[str, str], backlog_statuses: dict[str, int]) -> str:
    if handoff.status == "waiting":
        return "network_wait"
    recovery_statuses = {
        step_id: status
        for step_id, status in status_by_step.items()
        if step_id.startswith("recovery-step-")
    }
    if recovery_statuses:
        values = list(recovery_statuses.values())
        if any(status in {"ready", "in_progress", "planned", "pending"} for status in values):
            return "recovery_active"
        if all(status == "completed" for status in values):
            return "recovery_cleared"
    if handoff.status == "exception" and handoff.exception_plan:
        return "exception_active"
    if backlog_statuses["blocked"] > 0:
        return "exception_active"
    return "none"


def _implementation_backlog_status_summary(handoff: Any) -> dict[str, int]:
    counts = {"ready": 0, "planned": 0, "in_progress": 0, "blocked": 0, "done": 0}
    for item in handoff.implementation_backlog:
        status = _normalize_backlog_status(handoff, str(item.get("status", "")))
        if status in counts:
            counts[status] += 1
    return counts


def _normalize_backlog_status(handoff: Any, raw: str) -> str:
    status = raw.strip().lower()
    if status in {"completed", "done", "closed", "accepted"}:
        return "done"
    if status in {"failed", "blocked"}:
        return "blocked"
    if status in {"in_progress", "active", "executing"}:
        return "in_progress"
    if status in {"ready", "pending"}:
        return "ready"
    if status in {"planned", "queued"}:
        return "planned"
    if status in {"exception"}:
        return "blocked"
    return status or "planned"


def prince2_node_runtime_summary(handoff: Any) -> dict[str, int | str]:
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    counts = {
        "command": "roles runtime",
        "status": "missing" if not runtime else str(runtime.get("status", "materialized")),
        "nodes": len(nodes),
        "ready": 0,
        "waiting": 0,
        "running": 0,
        "blocked": 0,
        "escalated": 0,
        "idle": 0,
        "completed": 0,
        "message_queues": 0,
        "wait_triggers": 0,
    }
    for node in nodes:
        state = _node_runtime_state(handoff, node)
        if state in counts:
            counts[state] += 1
        wait_status = str(node.get("wait_status", "none")).strip().lower()
        if wait_status not in {"", "none"}:
            counts["waiting"] += 0 if state == "waiting" else 1
        counts["message_queues"] += int(node.get("inbox_count", 0) or 0) + int(node.get("outbox_count", 0) or 0)
        counts["wait_triggers"] += len(node.get("wake_triggers", [])) if isinstance(node.get("wake_triggers"), list) else 0
    return counts


def _prince2_runtime_node(handoff: Any, node_id: str) -> dict[str, Any]:
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    if not runtime:
        raise ValueError("No materialized PRINCE2 node runtime. Approve a role-tree baseline first.")
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    node = next((item for item in nodes if str(item.get("node_id", "")).strip() == node_id), None)
    if node is None:
        raise ValueError(f"Node '{node_id}' not found in PRINCE2 node runtime.")
    handoff.prince2_node_runtime["nodes"] = nodes
    return node


def _node_tolerance_margin(handoff: Any, node: dict[str, Any]) -> float:
    try:
        margin = float(node.get("tolerance_margin_percent", 25.0) or 25.0)
    except (TypeError, ValueError):
        return 25.0
    if margin <= 0:
        return 25.0
    return min(margin, 100.0)


def _node_tolerance_pressure(handoff: Any, node: dict[str, Any]) -> float:
    try:
        pressure = float(node.get("tolerance_pressure_percent", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if pressure < 0:
        return 0.0
    return min(pressure, 100.0)


def _node_tolerance_state(handoff: Any, node: dict[str, Any]) -> str:
    state = str(node.get("state", "idle")).strip().lower() or "idle"
    if state == "completed":
        return state
    if state in {"escalated", "blocked"}:
        return state
    margin = _node_tolerance_margin(handoff, node)
    antagonist_pressure = _node_antagonist_pressure(handoff, node) * 0.25
    pressure = max(_node_tolerance_pressure(handoff, node), antagonist_pressure)
    if pressure > margin:
        return "escalated"
    return state


def _node_model_pricing(handoff: Any, node: dict[str, Any], catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    assignment = node.get("assignment", {}) if isinstance(node.get("assignment"), dict) else {}
    provider = str(assignment.get("provider", "")).strip()
    provider_model = str(assignment.get("provider_model", "")).strip()
    pricing = {
        "provider": provider or "none",
        "provider_model": provider_model or "none",
        "cost_per_input_token_usd": None,
        "cost_per_output_token_usd": None,
        "blended_price_usd_per_1m_tokens": None,
        "source": None,
    }
    if not provider or not provider_model or provider_model == "provider-default":
        return pricing
    catalog_data = catalog if catalog is not None else load_ai_models_catalog()
    entry = catalog_entry_for_provider_model(provider, provider_model, catalog_data)
    if not entry:
        return pricing
    pricing["cost_per_input_token_usd"] = _safe_price_per_token(entry.get("cost_per_input_token_usd"))
    pricing["cost_per_output_token_usd"] = _safe_price_per_token(entry.get("cost_per_output_token_usd"))
    pricing["blended_price_usd_per_1m_tokens"] = entry.get("blended_price_usd_per_1m_tokens")
    pricing["source"] = entry.get("source")
    return pricing


def _node_thread_token_profile(handoff: Any, node: dict[str, Any]) -> dict[str, Any]:
    text_parts = [
        str(node.get("label", "")),
        str(node.get("description", "")),
        str(node.get("accountability_boundary", "")),
        str(node.get("delegated_authority", "")),
        str(node.get("responsibility_domain", "")),
        str(node.get("context_scope", "")),
        str(node.get("autonomy_rule", "")),
    ]
    business_case_input_tokens = sum(len(part.split()) for part in text_parts if part.strip())
    if business_case_input_tokens <= 0:
        business_case_input_tokens = 1
    tolerance_profile = node.get("tolerance_profile", {})
    theme_scores = tolerance_profile.get("theme_scores", {}) if isinstance(tolerance_profile, dict) else {}
    kpi_token_counts: dict[str, int] = {}
    for theme in PRINCE2_THEME_NAMES:
        try:
            score = float(theme_scores.get(theme, 0.0))
        except (TypeError, ValueError):
            score = 0.0
        kpi_token_counts[theme] = max(0, int(round(business_case_input_tokens * score)))
    token_budget = node.get("token_budget")
    try:
        token_budget_value = int(token_budget) if token_budget not in {None, ""} else None
    except (TypeError, ValueError):
        token_budget_value = None
    pricing = _node_model_pricing(handoff, node)
    input_price = pricing.get("cost_per_input_token_usd")
    output_price = pricing.get("cost_per_output_token_usd")
    business_case_output_tokens = int(node.get("business_case_output_token_count", 0) or 0)
    business_case_input_cost_usd = round_usd(business_case_input_tokens * float(input_price or 0.0))
    business_case_output_cost_usd = round_usd(business_case_output_tokens * float(output_price or 0.0))
    return {
        "business_case_token_count": business_case_input_tokens + business_case_output_tokens,
        "business_case_input_token_count": business_case_input_tokens,
        "business_case_output_token_count": business_case_output_tokens,
        "business_case_input_cost_usd": business_case_input_cost_usd,
        "business_case_output_cost_usd": business_case_output_cost_usd,
        "business_case_cost_usd": round_usd(business_case_input_cost_usd + business_case_output_cost_usd),
        "kpi_token_counts": kpi_token_counts,
        "thread_token_count": business_case_input_tokens + business_case_output_tokens + sum(kpi_token_counts.values()),
        "token_budget": token_budget_value,
        "pricing": pricing,
    }


def _node_antagonist_evidence(handoff: Any, node: dict[str, Any]) -> dict[str, Any]:
    context_rule = node.get("context_rule", {}) if isinstance(node.get("context_rule"), dict) else {}
    include = [str(item).strip() for item in context_rule.get("include", []) if str(item).strip()]
    exclude = [str(item).strip() for item in context_rule.get("exclude", []) if str(item).strip()]
    inbox = [dict(item) for item in node.get("inbox", []) if isinstance(item, dict)] if isinstance(node.get("inbox", []), list) else []
    outbox = [dict(item) for item in node.get("outbox", []) if isinstance(item, dict)] if isinstance(node.get("outbox", []), list) else []
    transcript_refs = [str(item).strip() for item in node.get("transcript_refs", []) if str(item).strip()] if isinstance(node.get("transcript_refs", []), list) else []
    text_fragments = [
        str(node.get("label", "")),
        str(node.get("description", "")),
        str(node.get("accountability_boundary", "")),
        str(node.get("delegated_authority", "")),
        str(node.get("responsibility_domain", "")),
        str(node.get("context_scope", "")),
        str(node.get("autonomy_rule", "")),
        str(node.get("wait_reason", "")),
        str(node.get("spawn_reason", "")),
        str(node.get("spawn_source", "")),
    ]
    text_fragments.extend(include)
    text_fragments.extend(exclude)
    text_fragments.extend(transcript_refs)
    for message in inbox + outbox:
        text_fragments.extend(
            [
                str(message.get("summary", "")),
                str(message.get("validation_condition", "")),
                str(message.get("decision_authority", "")),
                str(message.get("return_path", "")),
                " ".join(str(scope) for scope in message.get("payload_scope", []) if str(scope).strip())
                if isinstance(message.get("payload_scope", []), list)
                else "",
                " ".join(str(scope) for scope in message.get("expected_evidence", []) if str(scope).strip())
                if isinstance(message.get("expected_evidence", []), list)
                else "",
                " ".join(str(scope) for scope in message.get("evidence_refs", []) if str(scope).strip())
                if isinstance(message.get("evidence_refs", []), list)
                else "",
            ]
        )
    joined = " ".join(fragment for fragment in text_fragments if fragment).lower()
    signal_patterns = {
        "failure": ("error", "failed", "failure", "traceback", "exception", "crash", "broken"),
        "control": ("denied", "unauthorized", "blocked", "reject", "forbidden", "permission"),
        "drift": ("drift", "slip", "creep", "mismatch", "regression", "stale", "missing"),
        "capacity": ("overrun", "budget", "limit", "token", "pressure", "backlog", "queue", "timeout", "stalled", "deadlock", "overload"),
        "risk": ("risk", "threat", "anti-benefit", "objection", "adversary", "attack", "hacker"),
        "coordination": ("handoff", "dependency", "upstream", "downstream", "blocked", "waiting"),
    }
    evidence_signals: list[str] = []
    for label, needles in signal_patterns.items():
        if any(needle in joined for needle in needles):
            evidence_signals.append(label)
    for message in inbox + outbox:
        combined = " ".join(
            str(part)
            for part in (
                message.get("summary", ""),
                message.get("detail", ""),
                message.get("validation_condition", ""),
                message.get("decision_authority", ""),
                message.get("return_path", ""),
            )
            if str(part).strip()
        ).lower()
        for label, needles in signal_patterns.items():
            if any(needle in combined for needle in needles) and label not in evidence_signals:
                evidence_signals.append(label)
    if not evidence_signals:
        if str(node.get("wait_status", "")).strip().lower() != "none":
            evidence_signals.append("waiting")
        elif inbox or outbox:
            evidence_signals.append("queue_pressure")
    evidence_refs: list[str] = []
    for ref in transcript_refs:
        if ref and ref not in evidence_refs:
            evidence_refs.append(ref)
    for message in inbox + outbox:
        for ref in message.get("evidence_refs", []):
            clean_ref = str(ref).strip()
            if clean_ref and clean_ref not in evidence_refs:
                evidence_refs.append(clean_ref)
    return {
        "context_rule": context_rule,
        "include": include,
        "exclude": exclude,
        "inbox": inbox,
        "outbox": outbox,
        "transcript_refs": transcript_refs,
        "evidence_signals": evidence_signals,
        "evidence_refs": evidence_refs,
    }


def _node_antagonist_profile(handoff: Any, node: dict[str, Any]) -> dict[str, Any]:
    evidence = _node_antagonist_evidence(handoff, node)
    owner = str(node.get("accountable_owner", "user")).strip() or "user"
    label = str(node.get("label", "Node")).strip() or "Node"
    role = str(node.get("role_type", "role")).strip() or "role"
    tolerance_margin = _node_tolerance_margin(handoff, node)
    tolerance_pressure = _node_tolerance_pressure(handoff, node)
    deviation = max(0.0, tolerance_pressure - tolerance_margin)
    risk_sources = list(evidence.get("evidence_signals", []))
    if str(node.get("spawn_reason", "")).strip():
        risk_sources.append(f"spawn_reason:{node.get('spawn_reason')}")
    if str(node.get("wait_reason", "")).strip():
        risk_sources.append(f"wait_reason:{node.get('wait_reason')}")
    pressure = min(100.0, round(max(tolerance_pressure, deviation + (10.0 if risk_sources else 0.0)), 2))
    threat_count = max(1 if deviation > 0 else 0, len(risk_sources), len(evidence.get("evidence_signals", [])))
    decision_kpis = {
        "antagonist_pressure_percent": pressure,
        "pressure_over_margin_percent": round(deviation, 2),
        "risk_source_count": len(risk_sources),
        "evidence_signal_count": len(evidence.get("evidence_signals", [])),
        "evidence_ref_count": len(evidence.get("evidence_refs", [])),
        "queued_message_count": len(evidence.get("inbox", [])) + len(evidence.get("outbox", [])),
        "threat_count": threat_count,
    }
    devil_advocate = (
        f"Assume {label} overstates control and underestimates antagonist pressure; "
        f"challenge {owner} on whether {role} can still deliver within its margin. "
        "Apply retrospettiva prospettica: assume this plan already failed and explain why before it starts."
    )
    return {
        "antagonist_name": f"{label} Antagonist",
        "owner": owner,
        "role": role,
        "evidence_signals": evidence.get("evidence_signals", []),
        "evidence_refs": evidence.get("evidence_refs", []),
        "countermeasures": [
            f"mitigate {item.split(':', 1)[-1]}" if ":" in item else f"mitigate {item}"
            for item in risk_sources[:3]
        ] or [f"mitigate {label.lower()} threats"],
        "decision_kpis": decision_kpis,
        "devil_advocate": devil_advocate,
        "decision_questions": [
            f"What log evidence contradicts the optimistic reading of {label}?",
            "Which queued messages or transcript refs still lack closure?",
            "What is the cheapest failure path if this node keeps assuming success?",
            "If the plan had already failed, what would be the first reason and where would the evidence appear?",
        ],
        "decision_process": (
            "Treat risks, anti-benefits, and wet-run log evidence as first-class inputs. "
            "Always play devil's advocate against the current plan using runtime signals, "
            "and also run retrospettiva prospettica by assuming the plan already failed and explaining why. "
            "Use queued messages, transcript refs, and role-specific failure modes as evidence. "
            "Spawned recovery children start with attenuated antagonist pressure; "
            "if pressure exceeds tolerance, escalate and spawn recovery work."
        ),
    }


def _node_antagonist_pressure(handoff: Any, node: dict[str, Any]) -> float:
    profile = node.get("antagonist_profile", {})
    if isinstance(profile, dict):
        decision_kpis = profile.get("decision_kpis", {})
        if isinstance(decision_kpis, dict):
            try:
                pressure = float(decision_kpis.get("antagonist_pressure_percent", 0.0) or 0.0)
            except (TypeError, ValueError):
                pressure = 0.0
            if pressure < 0:
                return 0.0
            return min(pressure, 100.0)
    return 0.0


def _node_flow_bucket(handoff: Any, flow_type: str) -> str:
    clean = str(flow_type).strip().lower()
    if clean in {"authorization", "board_decision"}:
        return "business_case"
    if clean in {"assurance", "quality"}:
        return "quality"
    if clean in {"exception"}:
        return "change"
    if clean in {"delegation"}:
        return "plans"
    if clean in {"record"}:
        return "organization"
    return "progress"


def _bump_node_thread_tokens(
    handoff: Any,
    node: dict[str, Any],
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    bucket: str | None = None,
) -> None:
    input_count = max(0, int(input_tokens))
    output_count = max(0, int(output_tokens))
    amount = input_count + output_count
    if amount <= 0:
        return
    node["thread_token_count"] = int(node.get("thread_token_count", 0) or 0) + amount
    node["business_case_input_token_count"] = int(node.get("business_case_input_token_count", 0) or 0) + input_count
    node["business_case_output_token_count"] = int(node.get("business_case_output_token_count", 0) or 0) + output_count
    node["business_case_token_count"] = int(node.get("business_case_input_token_count", 0) or 0) + int(node.get("business_case_output_token_count", 0) or 0)
    pricing = _node_model_pricing(handoff, node)
    input_price = float(pricing.get("cost_per_input_token_usd") or 0.0)
    output_price = float(pricing.get("cost_per_output_token_usd") or 0.0)
    node["business_case_input_cost_usd"] = round_usd(
        float(node.get("business_case_input_cost_usd", 0.0) or 0.0) + (input_count * input_price)
    )
    node["business_case_output_cost_usd"] = round_usd(
        float(node.get("business_case_output_cost_usd", 0.0) or 0.0) + (output_count * output_price)
    )
    node["business_case_cost_usd"] = round_usd(
        float(node.get("business_case_input_cost_usd", 0.0) or 0.0)
        + float(node.get("business_case_output_cost_usd", 0.0) or 0.0)
    )
    kpi_counts = node.get("kpi_token_counts", {})
    if isinstance(kpi_counts, dict) and bucket in PRINCE2_THEME_NAMES:
        kpi_counts[bucket] = int(kpi_counts.get(bucket, 0) or 0) + amount
        node["kpi_token_counts"] = kpi_counts


def _spawn_prince2_escalation_child(handoff: Any, *, node_id: str, reason: str) -> dict[str, Any] | None:
    baseline = handoff.prince2_role_tree_baseline if isinstance(handoff.prince2_role_tree_baseline, dict) else {}
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    nodes = [node for node in tree.get("nodes", []) if isinstance(node, dict)]
    parent = next((node for node in nodes if str(node.get("node_id", "")).strip() == node_id), None)
    if parent is None:
        return None
    existing_child = next(
        (
            node
            for node in nodes
            if str(node.get("parent_id", "")).strip() == node_id
            and str(node.get("spawn_source", "")).strip().lower() == "escalation"
        ),
        None,
    )
    if existing_child is not None:
        runtime_nodes = [node for node in (handoff.prince2_node_runtime or {}).get("nodes", []) if isinstance(node, dict)]
        runtime_child = next(
            (node for node in runtime_nodes if str(node.get("node_id", "")).strip() == str(existing_child.get("node_id", ""))),
            None,
        )
        return dict(runtime_child or existing_child)
    existing_ids = {str(node.get("node_id", "")).strip() for node in nodes if str(node.get("node_id", "")).strip()}
    base_child_id = f"{node_id}.escalation"
    child_id = base_child_id
    suffix = 2
    while child_id in existing_ids:
        child_id = f"{base_child_id}_{suffix}"
        suffix += 1
    parent_label = str(parent.get("label", node_id)).strip() or node_id
    parent_role = str(parent.get("role_type", "project_manager")).strip() or "project_manager"
    parent_profile = parent.get("tolerance_profile", {}) if isinstance(parent.get("tolerance_profile", {}), dict) else {}
    thread_profile = _node_thread_token_profile(handoff, parent)
    child = {
        "node_id": child_id,
        "role_type": parent_role,
        "label": f"{parent_label} Escalation Child",
        "description": f"Auto-generated escalation child for {parent_label} after {reason.replace('_', ' ')}.",
        "parent_id": node_id,
        "level": f"delegated_{str(parent.get('level', 'node')).strip() or 'node'}",
        "state": "ready" if parent.get("assignment") else "idle",
        "runtime_status": "active_actor",
        "wait_status": "none",
        "wait_reason": None,
        "wake_triggers": list((parent.get("context_rule") or {}).get("expansion_events", [])) if isinstance(parent.get("context_rule"), dict) else [],
        "context_rule": dict(parent.get("context_rule", {})) if isinstance(parent.get("context_rule"), dict) else {},
        "accountability_boundary": f"escalation recovery lane under {parent_label}",
        "delegated_authority": f"supports {parent_label} within approved tolerances after escalation.",
        "context_scope": str(parent.get("context_scope", "")) or "escalation recovery",
        "responsibility_domain": str(parent.get("responsibility_domain", "")) or "controlled project work",
        "accountable_owner": str(parent.get("accountable_owner", "user")) or "user",
        "tolerance_margin_percent": float(parent.get("tolerance_margin_percent", 25.0) or 25.0),
        "tolerance_pressure_percent": 0.0,
        "autonomy_rule": str(parent.get("autonomy_rule", "")) or "work autonomously within the margin and escalate when pressure exceeds the limit.",
        "escalation_target": str(parent.get("escalation_target", "board.executive")),
        "tolerance_profile": dict(parent_profile),
        "assignment": dict(parent.get("assignment", {})) if isinstance(parent.get("assignment", {}), dict) else {},
        "fallback_pool": list(parent.get("fallback_pool", [])) if isinstance(parent.get("fallback_pool", []), list) else [],
        "readiness": "escalation_spawned",
        "spawn_source": "escalation",
        "spawn_reason": reason,
        "spawned_from": node_id,
        "spawned_at": utc_now(),
        "business_case_token_count": thread_profile["business_case_token_count"],
        "business_case_input_token_count": thread_profile["business_case_input_token_count"],
        "business_case_output_token_count": thread_profile["business_case_output_token_count"],
        "business_case_input_cost_usd": thread_profile["business_case_input_cost_usd"],
        "business_case_output_cost_usd": thread_profile["business_case_output_cost_usd"],
        "business_case_cost_usd": thread_profile["business_case_cost_usd"],
        "kpi_token_counts": dict(thread_profile["kpi_token_counts"]),
        "thread_token_count": thread_profile["thread_token_count"],
        "token_budget": thread_profile["token_budget"],
        "pricing": dict(thread_profile.get("pricing", {})),
    }
    nodes.append(child)
    tree["nodes"] = nodes
    baseline["tree"] = tree
    baseline["status"] = "approved"
    baseline["source"] = "escalation_spawn"
    baseline["approved_at"] = utc_now()
    handoff.sync_prince2_role_tree_baseline(baseline)
    runtime_nodes = [node for node in (handoff.prince2_node_runtime or {}).get("nodes", []) if isinstance(node, dict)]
    return next((dict(node) for node in runtime_nodes if str(node.get("node_id", "")).strip() == child_id), dict(child))


def _node_runtime_state(handoff: Any, node: dict[str, Any]) -> str:
    return _node_tolerance_state(handoff, node)


def _materialize_prince2_node_runtime(handoff: Any, baseline: dict[str, Any]) -> dict[str, Any]:
    tree = baseline.get("tree", {}) if isinstance(baseline.get("tree"), dict) else {}
    flow = baseline.get("flow", {}) if isinstance(baseline.get("flow"), dict) else {}
    nodes = [node for node in tree.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
    child_ids_by_parent: dict[str, list[str]] = {}
    for raw_node in nodes:
        parent_id = str(raw_node.get("parent_id", "")).strip()
        node_id = str(raw_node.get("node_id", "")).strip()
        if not parent_id or not node_id:
            continue
        child_ids_by_parent.setdefault(parent_id, []).append(node_id)
    existing_runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    existing_nodes = {
        str(node.get("node_id")): node
        for node in existing_runtime.get("nodes", [])
        if isinstance(node, dict) and node.get("node_id")
    }
    materialized_nodes: list[dict[str, Any]] = []
    materialized_at = utc_now()
    for node in nodes:
        node_id = str(node.get("node_id", "")).strip()
        if not node_id:
            continue
        previous = existing_nodes.get(node_id, {})
        assignment = dict(node.get("assignment", {})) if isinstance(node.get("assignment"), dict) else {}
        wake_triggers = previous.get("wake_triggers")
        if not isinstance(wake_triggers, list) or not wake_triggers:
            wake_triggers = list((node.get("context_rule") or {}).get("expansion_events", [])) if isinstance(node.get("context_rule"), dict) else []
        context_rule = dict(node.get("context_rule", {})) if isinstance(node.get("context_rule"), dict) else {}
        inbox = [dict(item) for item in previous.get("inbox", []) if isinstance(item, dict)] if isinstance(previous.get("inbox", []), list) else []
        outbox = [dict(item) for item in previous.get("outbox", []) if isinstance(item, dict)] if isinstance(previous.get("outbox", []), list) else []
        transcript_refs = [str(item) for item in previous.get("transcript_refs", [])] if isinstance(previous.get("transcript_refs", []), list) else []
        default_state = "ready" if assignment else "idle"
        wait_status = str(previous.get("wait_status", "none")).strip().lower() or "none"
        wait_reason = str(previous.get("wait_reason", "")).strip() or None
        thread_tokens = _node_thread_token_profile(handoff, node)
        antagonist_profile = _node_antagonist_profile(handoff, node)
        child_ids = list(child_ids_by_parent.get(node_id, []))
        materialized_nodes.append(
            {
                "node_id": node_id,
                "mnemonic": str(node.get("mnemonic", node_id[:3].upper() or "NOD")),
                "role_type": str(node.get("role_type", "")),
                "team_name": str(node.get("team_name", "Unassigned")),
                "label": str(node.get("label", node_id)),
                "description": str(node.get("description", prince2_node_description(node))),
                "parent_id": str(node.get("parent_id")) if node.get("parent_id") not in {None, ""} else None,
                "level": str(node.get("level", "")),
                "state": str(previous.get("state", default_state)).strip().lower() or default_state,
                "runtime_status": "active_actor",
                "wait_status": wait_status,
                "wait_reason": wait_reason,
                "wake_triggers": wake_triggers,
                "context_rule": context_rule,
                "accountability_boundary": str(node.get("accountability_boundary", "")),
                "delegated_authority": str(node.get("delegated_authority", "")),
                "context_scope": str(node.get("context_scope", "")),
                "responsibility_domain": str(node.get("responsibility_domain", "")),
                "accountable_owner": str(node.get("accountable_owner", "user")) or "user",
                "tolerance_margin_percent": float(node.get("tolerance_margin_percent", 25.0) or 25.0),
                "tolerance_pressure_percent": float(node.get("tolerance_pressure_percent", 0.0) or 0.0),
                "autonomy_rule": str(node.get("autonomy_rule", "")),
                "escalation_target": str(node.get("escalation_target", "board.executive")),
                "tolerance_profile": dict(node.get("tolerance_profile", {}))
                if isinstance(node.get("tolerance_profile", {}), dict)
                else {},
                "assignment": assignment,
                "mode": str(assignment.get("mode", "manual")).strip() or "manual",
                "provider": str(assignment.get("provider", "")),
                "provider_model": str(assignment.get("provider_model", "")),
                "spawn_source": str(node.get("spawn_source", "")),
                "spawn_reason": str(node.get("spawn_reason", "")),
                "spawned_from": str(node.get("spawned_from", "")),
                "spawned_at": str(node.get("spawned_at", "")),
                "child_ids": child_ids,
                "child_count": len(child_ids),
                "business_case_token_count": int(previous.get("business_case_token_count", thread_tokens["business_case_token_count"]) or thread_tokens["business_case_token_count"]),
                "business_case_input_token_count": int(previous.get("business_case_input_token_count", thread_tokens["business_case_input_token_count"]) or thread_tokens["business_case_input_token_count"]),
                "business_case_output_token_count": int(previous.get("business_case_output_token_count", thread_tokens["business_case_output_token_count"]) or thread_tokens["business_case_output_token_count"]),
                "business_case_input_cost_usd": float(previous.get("business_case_input_cost_usd", thread_tokens["business_case_input_cost_usd"]) or thread_tokens["business_case_input_cost_usd"]),
                "business_case_output_cost_usd": float(previous.get("business_case_output_cost_usd", thread_tokens["business_case_output_cost_usd"]) or thread_tokens["business_case_output_cost_usd"]),
                "business_case_cost_usd": float(previous.get("business_case_cost_usd", thread_tokens["business_case_cost_usd"]) or thread_tokens["business_case_cost_usd"]),
                "kpi_token_counts": dict(previous.get("kpi_token_counts", thread_tokens["kpi_token_counts"]))
                if isinstance(previous.get("kpi_token_counts", thread_tokens["kpi_token_counts"]), dict)
                else dict(thread_tokens["kpi_token_counts"]),
                "thread_token_count": int(previous.get("thread_token_count", thread_tokens["thread_token_count"]) or thread_tokens["thread_token_count"]),
                "token_budget": thread_tokens["token_budget"],
                "pricing": dict(previous.get("pricing", thread_tokens.get("pricing", {})))
                if isinstance(previous.get("pricing", thread_tokens.get("pricing", {})), dict)
                else dict(thread_tokens.get("pricing", {})),
                "antagonist_profile": dict(antagonist_profile),
                "antagonist_name": str(antagonist_profile.get("antagonist_name", f"{node.get('label', node_id)} Antagonist")),
                "antagonist_pressure_percent": float(antagonist_profile.get("decision_kpis", {}).get("antagonist_pressure_percent", 0.0) or 0.0)
                if isinstance(antagonist_profile.get("decision_kpis", {}), dict)
                else 0.0,
                "devil_advocate": str(antagonist_profile.get("devil_advocate", "")),
                "evidence_signals": list(antagonist_profile.get("evidence_signals", []))
                if isinstance(antagonist_profile.get("evidence_signals", []), list)
                else [],
                "evidence_refs": list(antagonist_profile.get("evidence_refs", []))
                if isinstance(antagonist_profile.get("evidence_refs", []), list)
                else [],
                "decision_kpis": dict(antagonist_profile.get("decision_kpis", {}))
                if isinstance(antagonist_profile.get("decision_kpis", {}), dict)
                else {},
                "incoming_edges": [
                    str(edge.get("edge_id", ""))
                    for edge in edges
                    if str(edge.get("target_node", "")).strip() == node_id and str(edge.get("edge_id", "")).strip()
                ],
                "outgoing_edges": [
                    str(edge.get("edge_id", ""))
                    for edge in edges
                    if str(edge.get("source_node", "")).strip() == node_id and str(edge.get("edge_id", "")).strip()
                ],
                "inbox": inbox,
                "outbox": outbox,
                "inbox_count": len(inbox),
                "outbox_count": len(outbox),
                "transcript_refs": transcript_refs,
                "last_transition_at": str(previous.get("last_transition_at", materialized_at)),
            }
        )
    return {
        "command": "roles runtime",
        "status": "materialized" if materialized_nodes else "missing",
        "rule": "approved PRINCE2 role-tree nodes are materialized as active runtime actors with scoped context, local wait state, and governed message queues",
        "materialized_at": materialized_at,
        "baseline_source": str(baseline.get("source", "unknown")),
        "baseline_status": str(baseline.get("status", "unknown")),
        "nodes": materialized_nodes,
    }


def load_project_handoff(cls: type[Any], path: Path) -> Any:
    if not path.exists():
        return cls()
    payload = loads_text(read_text_utf8(path))
    context = cls(
        task=str(payload.get("task", "")),
        goal=dict(payload.get("goal", {})) if isinstance(payload.get("goal", {}), dict) else {},
        project_budget=dict(payload.get("project_budget", {})) if isinstance(payload.get("project_budget", {}), dict) else {},
        user_question=dict(payload.get("user_question", {})) if isinstance(payload.get("user_question", {}), dict) else {},
        user_question_log=[dict(item) for item in payload.get("user_question_log", []) if isinstance(item, dict)],
        project_brief={
            str(key).strip().lower(): str(value).strip()
            for key, value in payload.get("project_brief", {}).items()
            if str(key).strip() and value is not None
        }
        if isinstance(payload.get("project_brief", {}), dict)
        else {},
        status=str(payload.get("status", "idle")),
        waiting_reason=str(payload.get("waiting_reason", "")),
        current_step_id=str(payload["current_step_id"]) if payload.get("current_step_id") else None,
        current_step_title=str(payload["current_step_title"]) if payload.get("current_step_title") else None,
        current_step_status=str(payload["current_step_status"]) if payload.get("current_step_status") else None,
        latest_observation=str(payload.get("latest_observation", "")),
        plan_status=str(payload.get("plan_status", "")),
        git_head=str(payload["git_head"]) if payload.get("git_head") else None,
        git_head_baseline=str(payload["git_head_baseline"]) if payload.get("git_head_baseline") else None,
        risk_register=[dict(item) for item in payload.get("risk_register", []) if isinstance(item, dict)],
        issue_register=[dict(item) for item in payload.get("issue_register", []) if isinstance(item, dict)],
        quality_register=[dict(item) for item in payload.get("quality_register", []) if isinstance(item, dict)],
        lessons_log=[dict(item) for item in payload.get("lessons_log", []) if isinstance(item, dict)],
        exception_plan=[str(item) for item in payload.get("exception_plan", [])],
        implementation_backlog=[dict(item) for item in payload.get("implementation_backlog", []) if isinstance(item, dict)],
        prince2_roles={
            str(key): dict(value)
            for key, value in payload.get("prince2_roles", {}).items()
            if isinstance(value, dict)
        },
        prince2_role_tree_baseline=dict(payload.get("prince2_role_tree_baseline", {}))
        if isinstance(payload.get("prince2_role_tree_baseline", {}), dict)
        else {},
        prince2_node_runtime=dict(payload.get("prince2_node_runtime", {}))
        if isinstance(payload.get("prince2_node_runtime", {}), dict)
        else {},
        updated_at=str(payload.get("updated_at", utc_now())),
    )
    from .project_handoff import HandoffEntry

    for item in payload.get("entries", []):
        context.entries.append(
            HandoffEntry(
                timestamp=str(item.get("timestamp", utc_now())),
                phase=str(item.get("phase", "")),
                iteration=int(item.get("iteration", 0)),
                task=str(item.get("task", context.task)),
                summary=str(item.get("summary", "")),
                step_id=str(item["step_id"]) if item.get("step_id") else None,
                step_title=str(item["step_title"]) if item.get("step_title") else None,
                step_status=str(item["step_status"]) if item.get("step_status") else None,
                model=str(item["model"]) if item.get("model") else None,
                action_type=str(item["action_type"]) if item.get("action_type") else None,
                git_head=str(item["git_head"]) if item.get("git_head") else None,
                details=dict(item.get("details", {})),
            )
        )
    return context
