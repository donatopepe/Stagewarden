from __future__ import annotations

from .config import AgentConfig
from .json_schema_registry import json_schema
from .project_handoff import ProjectHandoff


def goal_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "goal",
        "schema": json_schema("goal"),
        "goal": handoff.goal_view(),
    }


def budget_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "budget",
        "schema": json_schema("budget"),
        "budget": handoff.project_budget_view(),
    }


def question_report(config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    return {
        "command": "question",
        "schema": json_schema("question"),
        "user_question": handoff.user_question_view(),
        "latest_question": dict(handoff.user_question) if handoff.user_question else {},
        "question_log": [dict(item) for item in handoff.user_question_log[-10:]],
    }


def parse_goal_set_command(task: str) -> tuple[str, int | None]:
    rest = task.removeprefix("goal set").strip()
    token_budget = None
    marker = " --tokens "
    if marker in rest:
        objective, raw_budget = rest.rsplit(marker, 1)
        clean_budget = raw_budget.strip()
        if not clean_budget.isdigit():
            raise ValueError("Usage: goal set <objective> [--tokens N]")
        token_budget = int(clean_budget)
        rest = objective.strip()
    if not rest:
        raise ValueError("Usage: goal set <objective> [--tokens N]")
    return rest, token_budget


def parse_budget_set_command(task: str) -> tuple[float, str]:
    rest = task.removeprefix("budget set").strip()
    if not rest:
        raise ValueError("Usage: budget set <amount> [currency]")
    parts = rest.split()
    if not parts:
        raise ValueError("Usage: budget set <amount> [currency]")
    try:
        amount = float(parts[0])
    except ValueError as exc:
        raise ValueError("Usage: budget set <amount> [currency]") from exc
    currency = parts[1] if len(parts) > 1 else "USD"
    if len(parts) > 2:
        raise ValueError("Usage: budget set <amount> [currency]")
    return amount, currency


def parse_question_ask_command(task: str) -> str:
    rest = task.removeprefix("question ask").strip()
    if not rest:
        raise ValueError("Usage: question ask <question>")
    return rest


def parse_answer_command(task: str) -> str:
    rest = task.removeprefix("answer").strip()
    if not rest:
        raise ValueError("Usage: answer <response>")
    return rest


def goal_command_report(task: str, config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    try:
        if task == "goal":
            return goal_report(config)
        if task.startswith("goal set "):
            objective, token_budget = parse_goal_set_command(task)
            goal = handoff.set_goal(objective=objective, token_budget=token_budget)
            handoff.save(config.handoff_path)
            return {"command": "goal set", "schema": json_schema("goal set"), "ok": True, "goal": goal}
        if task.startswith("goal status "):
            status = task.split(maxsplit=2)[2]
            goal = handoff.update_goal_status(status)
            handoff.save(config.handoff_path)
            return {"command": "goal status", "schema": json_schema("goal status"), "ok": True, "goal": goal}
        if task == "goal clear":
            previous = handoff.clear_goal()
            handoff.save(config.handoff_path)
            return {
                "command": "goal clear",
                "schema": json_schema("goal clear"),
                "ok": True,
                "previous_goal": previous,
                "goal": handoff.goal_view(),
            }
    except ValueError as exc:
        command_name = task.split(maxsplit=2)[0]
        schema_command = command_name if command_name in {"goal", "goal set", "goal status", "goal clear"} else "goal"
        return {"command": command_name, "schema": json_schema(schema_command), "ok": False, "error": str(exc)}
    return {
        "command": task,
        "schema": json_schema("goal"),
        "ok": False,
        "error": "Usage: goal | goal set <objective> [--tokens N] | goal status <active|paused|budget_limited|complete> | goal clear",
    }


def budget_command_report(task: str, config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    try:
        if task == "budget":
            return budget_report(config)
        if task.startswith("budget set "):
            amount, currency = parse_budget_set_command(task)
            budget = handoff.set_project_budget(budget_usd=amount, currency=currency)
            handoff.save(config.handoff_path)
            return {"command": "budget set", "schema": json_schema("budget set"), "ok": True, "budget": budget}
        if task.startswith("budget status "):
            status = task.split(maxsplit=2)[2]
            budget = handoff.update_project_budget_status(status)
            handoff.save(config.handoff_path)
            return {"command": "budget status", "schema": json_schema("budget status"), "ok": True, "budget": budget}
        if task == "budget clear":
            previous = handoff.clear_project_budget()
            handoff.save(config.handoff_path)
            return {
                "command": "budget clear",
                "schema": json_schema("budget clear"),
                "ok": True,
                "previous_budget": previous,
                "budget": handoff.project_budget_view(),
            }
    except ValueError as exc:
        command_name = task.split(maxsplit=2)[0]
        schema_command = command_name if command_name in {"budget", "budget set", "budget status", "budget clear"} else "budget"
        return {"command": command_name, "schema": json_schema(schema_command), "ok": False, "error": str(exc)}
    return {
        "command": task,
        "schema": json_schema("budget"),
        "ok": False,
        "error": "Usage: budget | budget set <amount> [currency] | budget status <active|paused|budget_limited|complete> | budget clear",
    }


def question_command_report(task: str, config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    try:
        if task == "question":
            return question_report(config)
        if task.startswith("question ask "):
            question = parse_question_ask_command(task)
            record = handoff.ask_user(question=question, reason="manual_question", context={"source": "question ask"})
            handoff.save(config.handoff_path)
            return {"command": "question ask", "schema": json_schema("question ask"), "ok": True, "user_question": record}
        if task == "answer" or task.startswith("answer "):
            answer = parse_answer_command(task)
            record = handoff.answer_user_question(answer=answer)
            handoff.save(config.handoff_path)
            return {"command": "answer", "schema": json_schema("answer"), "ok": True, "user_question": record}
    except ValueError as exc:
        command_name = task.split(maxsplit=1)[0]
        schema_command = command_name if command_name in {"question", "question ask", "answer"} else "question"
        return {"command": command_name, "schema": json_schema(schema_command), "ok": False, "error": str(exc)}
    return {
        "command": task,
        "schema": json_schema("question"),
        "ok": False,
        "error": "Usage: question | question ask <question> | answer <response>",
    }


def render_goal_report(config: AgentConfig) -> str:
    goal = goal_report(config)["goal"]
    return "\n".join(
        [
            "Project goal:",
            f"- status: {goal['status']}",
            f"- objective: {goal['objective'] or 'none'}",
            f"- token_budget: {goal['token_budget'] if goal['token_budget'] is not None else 'none'}",
            f"- tokens_used: {goal['tokens_used']}",
            f"- token_budget_remaining: {goal['token_budget_remaining'] if goal['token_budget_remaining'] is not None else 'none'}",
            f"- budget_used_percentage: {goal['budget_used_percentage'] if goal['budget_used_percentage'] is not None else 'none'}",
            f"- terminal: {str(goal['terminal']).lower()}",
            f"- next_action: {goal['next_action']}",
        ]
    )


def render_budget_report(config: AgentConfig) -> str:
    budget = budget_report(config)["budget"]
    return "\n".join(
        [
            "Project budget:",
            f"- status: {budget['status']}",
            f"- budget_usd: {budget['budget_usd'] if budget['budget_usd'] is not None else 'none'}",
            f"- spend_usd: {budget['spend_usd']}",
            f"- remaining_usd: {budget['remaining_usd'] if budget['remaining_usd'] is not None else 'none'}",
            f"- budget_used_percentage: {budget['budget_used_percentage'] if budget['budget_used_percentage'] is not None else 'none'}",
            f"- currency: {budget['currency']}",
            f"- terminal: {str(budget['terminal']).lower()}",
            f"- next_action: {budget['next_action']}",
        ]
    )


def render_question_report(config: AgentConfig) -> str:
    question = question_report(config)["user_question"]
    pending = question.get("pending", {}) if isinstance(question, dict) else {}
    question_text = pending.get("question") if isinstance(pending, dict) else None
    answer_count = question.get("answered_count", 0) if isinstance(question, dict) else 0
    log_count = question.get("log_count", 0) if isinstance(question, dict) else 0
    next_action = question.get("next_action", "none") if isinstance(question, dict) else "none"
    return "\n".join(
        [
            "User question:",
            f"- status: {question['status']}",
            f"- pending: {question_text or 'none'}",
            f"- answered_count: {answer_count}",
            f"- log_count: {log_count}",
            f"- next_action: {next_action}",
        ]
    )
