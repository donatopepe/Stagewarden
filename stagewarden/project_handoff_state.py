from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _round_usd(value: float) -> float:
    return round(max(0.0, float(value)), 8)


def _project_budget_spend_usd(handoff: Any) -> float:
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    nodes = runtime.get("nodes", []) if isinstance(runtime, dict) else []
    total = 0.0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        total += float(node.get("business_case_cost_usd", 0.0) or 0.0)
    return _round_usd(total)


def project_budget_view(handoff: Any) -> dict[str, Any]:
    if not isinstance(handoff.project_budget, dict) or not handoff.project_budget:
        return {
            "status": "missing",
            "budget_id": None,
            "objective": "",
            "currency": "USD",
            "budget_usd": None,
            "spend_usd": 0.0,
            "remaining_usd": None,
            "budget_used_percentage": None,
            "created_at": None,
            "updated_at": None,
            "terminal": False,
            "next_action": "Set a project budget with `budget set <amount> [currency]`.",
        }
    status = str(handoff.project_budget.get("status", "active")).strip().lower() or "active"
    budget_value = handoff.project_budget.get("budget_usd")
    budget_usd = None
    try:
        if budget_value is not None and str(budget_value).strip() != "":
            budget_usd = _round_usd(float(budget_value))
    except (TypeError, ValueError):
        budget_usd = None
    spend_usd = _project_budget_spend_usd(handoff)
    remaining = None
    used_percentage = None
    if isinstance(budget_usd, float) and budget_usd > 0:
        remaining = _round_usd(max(budget_usd - spend_usd, 0.0))
        used_percentage = round((spend_usd / budget_usd) * 100, 2)
        if spend_usd >= budget_usd and status not in {"paused", "complete"}:
            status = "budget_limited"
    next_action = "Continue execution within the approved project budget."
    if status == "paused":
        next_action = "Resume with `budget status active` or clear with `budget clear`."
    elif status == "budget_limited":
        next_action = "Review scope, raise budget with `budget set <amount> [currency]`, pause, or mark complete."
    elif status == "complete":
        next_action = "Budget complete; start a new budget if more work is needed."
    return {
        "status": status,
        "budget_id": handoff.project_budget.get("budget_id"),
        "objective": str(handoff.project_budget.get("objective") or handoff.goal.get("objective", "")),
        "currency": str(handoff.project_budget.get("currency", "USD")),
        "budget_usd": budget_usd,
        "spend_usd": spend_usd,
        "remaining_usd": remaining,
        "budget_used_percentage": used_percentage,
        "created_at": handoff.project_budget.get("created_at"),
        "updated_at": handoff.project_budget.get("updated_at"),
        "terminal": status in {"budget_limited", "complete"},
        "next_action": next_action,
    }


def set_project_budget(handoff: Any, *, budget_usd: float, currency: str = "USD") -> dict[str, Any]:
    amount = _round_usd(budget_usd)
    if amount <= 0:
        raise ValueError("Project budget must be a positive amount.")
    clean_currency = " ".join(str(currency).split()).strip().upper() or "USD"
    now = _utc_now()
    previous = project_budget_view(handoff)
    budget_id = str(previous.get("budget_id") or f"budget-{now.replace(':', '').replace('+', 'Z')}")
    objective = str(handoff.goal.get("objective", "")).strip()
    handoff.project_budget = {
        "budget_id": budget_id,
        "objective": objective,
        "status": "active",
        "currency": clean_currency,
        "budget_usd": amount,
        "created_at": previous.get("created_at") or now,
        "updated_at": now,
    }
    handoff.updated_at = now
    handoff.record_action(
        phase="project_budget_set",
        summary=f"Project budget set: {amount} {clean_currency}.",
        task=handoff.task,
        details={"budget": project_budget_view(handoff)},
    )
    return project_budget_view(handoff)


def update_project_budget_status(handoff: Any, status: str) -> dict[str, Any]:
    clean_status = str(status).strip().lower()
    if clean_status not in {"active", "paused", "budget_limited", "complete"}:
        raise ValueError("Project budget status must be one of: active, paused, budget_limited, complete.")
    if not handoff.project_budget:
        raise ValueError("No project budget is set.")
    handoff.project_budget["status"] = clean_status
    handoff.project_budget["updated_at"] = _utc_now()
    handoff.updated_at = str(handoff.project_budget["updated_at"])
    handoff.record_action(
        phase="project_budget_status",
        summary=f"Project budget status changed to {clean_status}.",
        task=handoff.task,
        details={"budget": project_budget_view(handoff)},
    )
    return project_budget_view(handoff)


def clear_project_budget(handoff: Any) -> dict[str, Any]:
    previous = project_budget_view(handoff)
    handoff.project_budget = {}
    handoff.updated_at = _utc_now()
    handoff.record_action(
        phase="project_budget_clear",
        summary="Project budget cleared.",
        task=handoff.task,
        details={"previous_budget": previous},
    )
    return previous


def ask_user(
    handoff: Any,
    *,
    question: str,
    reason: str = "clarification",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_question = str(question).strip()
    if not clean_question:
        raise ValueError("Question cannot be empty.")
    clean_reason = str(reason).strip().lower() or "clarification"
    now = _utc_now()
    question_id = f"question-{len(handoff.user_question_log) + 1}"
    record = {
        "question_id": question_id,
        "question": clean_question,
        "reason": clean_reason,
        "context": dict(context or {}),
        "status": "pending",
        "asked_at": now,
        "answered_at": None,
        "answer": None,
    }
    handoff.user_question = dict(record)
    handoff.user_question_log.append(dict(record))
    handoff.status = "waiting"
    handoff.waiting_reason = clean_reason
    handoff.current_step_status = "waiting"
    handoff.latest_observation = clean_question
    handoff.updated_at = now
    handoff.record_action(
        phase="user_question_asked",
        summary=f"Question asked: {clean_question[:120]}",
        task=handoff.task,
        details={"question": dict(record)},
    )
    return dict(record)


def answer_user_question(handoff: Any, *, answer: str) -> dict[str, Any]:
    clean_answer = str(answer).strip()
    if not clean_answer:
        raise ValueError("Answer cannot be empty.")
    if not handoff.user_question:
        raise ValueError("No pending user question.")
    now = _utc_now()
    record = dict(handoff.user_question)
    record["status"] = "answered"
    record["answered_at"] = now
    record["answer"] = clean_answer
    handoff.user_question = {}
    handoff.user_question_log.append(record)
    handoff.status = "executing"
    handoff.waiting_reason = ""
    if handoff.current_step_status == "waiting":
        handoff.current_step_status = "in_progress"
    handoff.latest_observation = clean_answer
    handoff.updated_at = now
    handoff.record_action(
        phase="user_question_answered",
        summary=f"Question answered: {clean_answer[:120]}",
        task=handoff.task,
        details={"question": record},
    )
    return dict(record)


def user_question_view(handoff: Any) -> dict[str, Any]:
    pending = dict(handoff.user_question) if handoff.user_question else {}
    log = [dict(item) for item in handoff.user_question_log]
    return {
        "status": "pending" if pending else "missing",
        "waiting_reason": handoff.waiting_reason or "none",
        "pending": pending,
        "log_count": len(log),
        "answered_count": sum(1 for item in log if str(item.get("status", "")).strip().lower() == "answered"),
    }


def goal_view(handoff: Any) -> dict[str, Any]:
    if not isinstance(handoff.goal, dict) or not handoff.goal:
        return {
            "status": "missing",
            "goal_id": None,
            "objective": "",
            "token_budget": None,
            "tokens_used": 0,
            "token_budget_remaining": None,
            "budget_used_percentage": None,
            "time_used_seconds": 0,
            "created_at": None,
            "updated_at": None,
            "terminal": False,
            "next_action": "Set a project goal with `goal set <objective> [--tokens N]`.",
        }
    status = str(handoff.goal.get("status", "active")).strip().lower() or "active"
    token_budget = handoff.goal.get("token_budget")
    tokens_used = int(handoff.goal.get("tokens_used", 0) or 0)
    remaining = None
    used_percentage = None
    if isinstance(token_budget, int) and token_budget > 0:
        remaining = max(token_budget - tokens_used, 0)
        used_percentage = round((tokens_used / token_budget) * 100, 2)
    next_action = "Continue controlled execution."
    if status == "paused":
        next_action = "Resume with `goal status active` or clear with `goal clear`."
    elif status == "budget_limited":
        next_action = "Review scope, raise budget with `goal set <objective> --tokens N`, pause, or mark complete."
    elif status == "complete":
        next_action = "Goal complete; start a new goal if more work is needed."
    return {
        "status": status,
        "goal_id": handoff.goal.get("goal_id"),
        "objective": str(handoff.goal.get("objective", "")),
        "token_budget": token_budget,
        "tokens_used": tokens_used,
        "token_budget_remaining": remaining,
        "budget_used_percentage": used_percentage,
        "time_used_seconds": int(handoff.goal.get("time_used_seconds", 0) or 0),
        "created_at": handoff.goal.get("created_at"),
        "updated_at": handoff.goal.get("updated_at"),
        "terminal": status in {"budget_limited", "complete"},
        "next_action": next_action,
    }


def set_goal(handoff: Any, *, objective: str, token_budget: int | None = None) -> dict[str, Any]:
    clean_objective = str(objective).strip()
    if not clean_objective:
        raise ValueError("Goal objective cannot be empty.")
    if token_budget is not None and int(token_budget) <= 0:
        raise ValueError("Goal token budget must be positive.")
    now = _utc_now()
    previous = goal_view(handoff)
    goal_id = str(previous.get("goal_id") or f"goal-{now.replace(':', '').replace('+', 'Z')}")
    handoff.goal = {
        "goal_id": goal_id,
        "objective": clean_objective,
        "status": "active",
        "token_budget": int(token_budget) if token_budget is not None else None,
        "tokens_used": int(previous.get("tokens_used", 0) or 0),
        "created_at": previous.get("created_at") or now,
        "updated_at": now,
    }
    handoff.updated_at = now
    handoff.record_action(
        phase="goal_set",
        summary=f"Goal set: {clean_objective[:120]}",
        task=handoff.task,
        details={"goal": goal_view(handoff)},
    )
    return goal_view(handoff)


def update_goal_status(handoff: Any, status: str) -> dict[str, Any]:
    clean_status = str(status).strip().lower()
    if clean_status not in {"active", "paused", "budget_limited", "complete"}:
        raise ValueError("Goal status must be one of: active, paused, budget_limited, complete.")
    if not handoff.goal:
        raise ValueError("No goal is set.")
    handoff.goal["status"] = clean_status
    handoff.goal["updated_at"] = _utc_now()
    handoff.updated_at = str(handoff.goal["updated_at"])
    handoff.record_action(
        phase="goal_status",
        summary=f"Goal status changed to {clean_status}.",
        task=handoff.task,
        details={"goal": goal_view(handoff)},
    )
    return goal_view(handoff)


def record_goal_token_usage(
    handoff: Any,
    *,
    model: str,
    step_id: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    current_usage: int | None = None,
) -> dict[str, Any]:
    if not handoff.goal:
        return goal_view(handoff)
    input_count = int(input_tokens or 0)
    output_count = int(output_tokens or 0)
    total = input_count + output_count
    if total <= 0:
        total = int(current_usage or 0)
    if total <= 0:
        return goal_view(handoff)
    previous = goal_view(handoff)
    handoff.goal["tokens_used"] = int(previous.get("tokens_used", 0) or 0) + total
    handoff.goal["updated_at"] = _utc_now()
    budget = handoff.goal.get("token_budget")
    if isinstance(budget, int) and budget > 0 and int(handoff.goal["tokens_used"]) >= budget:
        handoff.goal["status"] = "budget_limited"
    handoff.updated_at = str(handoff.goal["updated_at"])
    handoff.record_action(
        phase="goal_usage",
        summary=f"Goal token usage recorded: +{total} tokens via {model}.",
        task=handoff.task,
        details={
            "model": model,
            "step_id": step_id,
            "input_tokens": input_count or None,
            "output_tokens": output_count or None,
            "current_usage": current_usage,
            "tokens_added": total,
            "goal": goal_view(handoff),
        },
    )
    return goal_view(handoff)


def clear_goal(handoff: Any) -> dict[str, Any]:
    previous = goal_view(handoff)
    handoff.goal = {}
    handoff.updated_at = _utc_now()
    handoff.record_action(
        phase="goal_clear",
        summary="Goal cleared.",
        task=handoff.task,
        details={"previous_goal": previous},
    )
    return previous
