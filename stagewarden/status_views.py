from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime

from .agent import Agent
from .config import AgentConfig
from .json_schema_registry import json_schema
from .memory import MemoryStore
from .modelprefs import SUPPORTED_MODELS, account_key, extract_blocked_until, limit_snapshot_from_message
from . import project_state_views as _project_state_views
from .project_handoff import ProjectHandoff
from .tools.git import GitTool
from .secrets import SecretStore


def _main():
    from . import main as _main_module

    return _main_module


def _provider_limit_snapshot_is_stale(captured_at: object, *, stale_after_minutes: int = 15) -> bool:
    if not captured_at:
        return False
    try:
        captured = datetime.fromisoformat(str(captured_at))
    except ValueError:
        return True
    now = datetime.now(tz=captured.tzinfo) if captured.tzinfo is not None else datetime.now()
    if captured > now:
        return False
    return (now - captured).total_seconds() > stale_after_minutes * 60


def _provider_limit_windows(item: dict[str, object]) -> dict[str, object]:
    blocked_until = item.get("blocked_until")
    reason = item.get("last_error_reason")
    snapshot = item.get("limit_snapshot")
    base = {
        "status": "blocked" if blocked_until else "available",
        "reason": reason,
        "blocked_until": blocked_until,
        "primary_window": None,
        "secondary_window": None,
        "credits": None,
        "rate_limit_type": reason,
        "utilization": None,
        "overage_status": None,
        "overage_resets_at": None,
        "overage_disabled_reason": None,
        "stale": False,
        "captured_at": None,
    }
    if isinstance(snapshot, dict):
        for key in base:
            if snapshot.get(key) is not None:
                base[key] = snapshot[key]
        base["stale"] = _provider_limit_snapshot_is_stale(base.get("captured_at"))
        if blocked_until:
            base["status"] = "blocked"
            base["blocked_until"] = blocked_until
        if reason:
            base["reason"] = reason
        if base["rate_limit_type"] is None:
            base["rate_limit_type"] = base["reason"]
    return base


def _provider_limit_resets_at(windows: dict[str, object]) -> object:
    return windows.get("blocked_until") or windows.get("overage_resets_at")


def _provider_limit_account_view(account: dict[str, object]) -> dict[str, object]:
    snapshot = account.get("limit_snapshot")
    windows = _provider_limit_windows(
        {
            "blocked_until": account.get("blocked_until"),
            "last_error_reason": account.get("last_limit_reason"),
            "limit_snapshot": snapshot,
        }
    )
    return {
        "name": account["name"],
        "active": account["active"],
        "status": windows["status"],
        "blocked_until": windows["blocked_until"],
        "reason": windows["reason"],
        "rate_limit_type": windows["rate_limit_type"],
        "utilization": windows["utilization"],
        "resets_at": _provider_limit_resets_at(windows),
        "overage_status": windows["overage_status"],
        "overage_resets_at": windows["overage_resets_at"],
        "overage_disabled_reason": windows["overage_disabled_reason"],
        "stale": windows["stale"],
        "captured_at": windows["captured_at"],
        "snapshot": snapshot,
    }


def _provider_limit_entry_view(
    item: dict[str, object],
    *,
    include_accounts: bool = False,
) -> dict[str, object]:
    windows = _provider_limit_windows(item)
    blocked_accounts = [
        _provider_limit_account_view(account)
        for account in item.get("blocked_accounts", [])
        if isinstance(account, dict)
    ]
    view = {
        "provider": item["provider"],
        "account": item["active_account"],
        "variant": item["variant"],
        "provider_model": item["provider_model"],
        "provider_model_selection": item["provider_model_selection"],
        "provider_model_params": item["provider_model_params"],
        "status": windows["status"],
        "reason": windows["reason"],
        "blocked_until": windows["blocked_until"],
        "primary_window": windows["primary_window"],
        "secondary_window": windows["secondary_window"],
        "credits": windows["credits"],
        "rate_limit_type": windows["rate_limit_type"],
        "utilization": windows["utilization"],
        "resets_at": _provider_limit_resets_at(windows),
        "overage_status": windows["overage_status"],
        "overage_resets_at": windows["overage_resets_at"],
        "overage_disabled_reason": windows["overage_disabled_reason"],
        "stale": windows["stale"],
        "captured_at": windows["captured_at"],
        "blocked_accounts_count": len(blocked_accounts),
    }
    if include_accounts:
        view["blocked_accounts"] = blocked_accounts
    return view


def _provider_limit_summary_report(provider_limits: dict[str, object]) -> dict[str, object]:
    items = [item for item in provider_limits.get("providers", []) if isinstance(item, dict)]
    blocked_models = [str(item["provider"]) for item in items if item.get("blocked_until")]
    stale_models = [str(item["provider"]) for item in items if _provider_limit_windows(item).get("stale")]
    blocked_accounts = []
    stale_accounts = []
    last_errors = []
    routes = []
    for item in items:
        route = f"{item.get('provider')}:{item.get('variant')}->{item.get('provider_model')}"
        routes.append(route)
        if item.get("last_error_reason"):
            last_errors.append(str(item["last_error_reason"]))
        for account in item.get("blocked_accounts", []):
            if not isinstance(account, dict):
                continue
            if account.get("blocked_until"):
                blocked_accounts.append(f"{item.get('provider')}:{account['name']}")
            snapshot = account.get("limit_snapshot")
            captured_at = snapshot.get("captured_at") if isinstance(snapshot, dict) else None
            if _provider_limit_snapshot_is_stale(captured_at):
                stale_accounts.append(f"{item.get('provider')}:{account['name']}")
    return {
        "providers_count": len(items),
        "blocked_models": blocked_models,
        "stale_models": stale_models,
        "blocked_accounts": blocked_accounts,
        "stale_accounts": stale_accounts,
        "last_errors": last_errors,
        "routes": routes,
    }


def _provider_limit_status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    prefs = main._load_model_preferences(config)
    main._apply_model_preferences(agent, config)
    capabilities = main.detect_runtime_capabilities(config.workspace_root)
    providers = []
    for provider in main.REGISTRY_MODELS:
        provider_capability = main.provider_capability(provider)
        active_account = (prefs.active_account_by_model or {}).get(provider)
        provider_model = provider_capability.default_model
        snapshot = (prefs.provider_limit_snapshot_by_model or {}).get(provider)
        blocked_accounts = []
        for account in (prefs.accounts_by_model or {}).get(provider, []):
            key = account_key(provider, account)
            blocked_until = (prefs.blocked_until_by_account or {}).get(key)
            limit_snapshot = (prefs.provider_limit_snapshot_by_account or {}).get(key) or {}
            blocked_accounts.append(
                {
                    "name": account,
                    "active": active_account == account,
                    "blocked_until": blocked_until,
                    "last_limit_reason": limit_snapshot.get("reason") or limit_snapshot.get("rate_limit_type"),
                    "last_limit_message": (prefs.last_limit_message_by_account or {}).get(key),
                    "limit_snapshot": limit_snapshot,
                }
            )
        provider_reason = None
        if isinstance(snapshot, dict):
            provider_reason = snapshot.get("reason") or snapshot.get("rate_limit_type")
        if provider_reason is None:
            message_snapshot = limit_snapshot_from_message((prefs.last_limit_message_by_model or {}).get(provider, ""))
            if isinstance(message_snapshot, dict):
                provider_reason = message_snapshot.get("reason") or message_snapshot.get("rate_limit_type")
        if provider_reason is None:
            provider_reason = next(
                (account.get("last_limit_reason") for account in blocked_accounts if account.get("last_limit_reason")),
                None,
            )
        providers.append(
            {
                "provider": provider,
                "variant": provider_capability.default_model,
                "provider_model": provider_model,
                "provider_model_selection": "dynamic",
                "provider_model_params": {},
                "active_account": active_account,
                "blocked_until": (prefs.blocked_until_by_model or {}).get(provider),
                "last_error_reason": provider_reason or (prefs.last_limit_message_by_model or {}).get(provider),
                "limit_snapshot": snapshot,
                "blocked_accounts": blocked_accounts,
                "enabled": provider in capabilities.get("providers", []),
            }
        )
    return {
        "command": "provider limits",
        "schema": json_schema("provider limits"),
        "providers": providers,
    }


def _render_provider_limit_status(agent: Agent, config: AgentConfig) -> str:
    report = _provider_limit_status_report(agent, config)
    summary = _provider_limit_summary_report(report)
    lines = ["Provider/model limits:"]
    lines.append(
        "- summary: "
        f"blocked_models={','.join(summary['blocked_models']) if summary['blocked_models'] else 'none'} "
        f"stale_models={','.join(summary['stale_models']) if summary['stale_models'] else 'none'} "
        f"blocked_accounts={','.join(summary['blocked_accounts']) if summary['blocked_accounts'] else 'none'} "
        f"stale_accounts={','.join(summary['stale_accounts']) if summary['stale_accounts'] else 'none'}"
    )
    for item in report["providers"]:
        blocked = f" blocked_until={item['blocked_until']}" if item["blocked_until"] else ""
        reason = f" reason={item['last_error_reason']}" if item["last_error_reason"] else ""
        lines.append(
            f"- {item['provider']}: {'blocked' if item['blocked_until'] else 'available'}{blocked}{reason} "
            f"account={item['active_account'] or 'none'} provider_model={item['provider_model']}"
        )
    return "\n".join(lines)


def _render_model_status(agent: Agent, config: AgentConfig) -> str:
    main = _main()
    prefs = main._load_model_preferences(config)
    status = agent.router.status()
    lines = ["Provider configuration:"]
    for provider in SUPPORTED_MODELS:
        backend = main.MODEL_BACKENDS[provider]["label"]
        capability = main.provider_capability(provider)
        enabled = "enabled" if provider in status["enabled_models"] else "disabled"
        blocked_until = status["blocked_until_by_model"].get(provider)
        blocked = f" blocked-until={blocked_until}" if blocked_until else ""
        active = " active" if provider in status["active_models"] else " inactive"
        preferred = " preferred-provider" if status["preferred_model"] == provider else ""
        provider_model, selection_mode, default_model = main._provider_model_display(prefs, provider)
        params = main._provider_model_params_display(prefs, provider)
        auth = capability.auth_type
        profiles = "profiles=yes" if capability.supports_account_profiles else "profiles=no"
        params_text = (
            " params=" + ",".join(f"{key}={value}" for key, value in sorted(params.items()))
            if params
            else ""
        )
        lines.append(
            f"- {provider}: {enabled}{active}{preferred}{blocked} "
            f"provider_model={provider_model} selection={selection_mode} default_model={default_model} "
            f"auth={auth} {profiles}{params_text} ({backend})"
        )
        account_lines = main._render_account_lines(prefs, provider)
        lines.extend(account_lines)
    if status["preferred_model"] is None:
        lines.append("- preferred_provider: automatic routing")
    else:
        lines.append(f"- preferred_provider: {status['preferred_model']}")
    return "\n".join(lines)


def _selected_model_report(model_report: dict[str, object]) -> dict[str, object] | None:
    models = model_report.get("models", []) if isinstance(model_report, dict) else []
    if not isinstance(models, list):
        return None
    selected = next((item for item in models if isinstance(item, dict) and item.get("preferred")), None)
    if selected is None:
        selected = next((item for item in models if isinstance(item, dict) and item.get("active")), None)
    return selected if isinstance(selected, dict) else None


def _model_status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    prefs = main._load_model_preferences(config)
    status = agent.router.status()
    catalog = main.load_ai_models_catalog()
    models: list[dict[str, object]] = []
    for model in SUPPORTED_MODELS:
        capability = main.provider_capability(model)
        provider_catalog = main.catalog_entries_for_provider(model, catalog)
        provider_default_entry = next((item for item in provider_catalog if str(item.get("model_id")) == "provider-default"), None)
        provider_model, selection_mode, default_model = main._provider_model_display(prefs, model)
        params = main._provider_model_params_display(prefs, model)
        catalog_entry = main.catalog_entry_for_provider_model(model, provider_model, catalog)
        models.append(
            {
                "model": model,
                "provider": model,
                "enabled": model in status["enabled_models"],
                "active": model in status["active_models"],
                "preferred": status["preferred_model"] == model,
                "blocked_until": status["blocked_until_by_model"].get(model),
                "variant": prefs.variant_for_model(model) or "provider-default",
                "provider_model": provider_model,
                "provider_model_selection": selection_mode,
                "provider_model_default": default_model,
                "provider_model_params": params,
                "auth": capability.auth_type,
                "profiles": capability.supports_account_profiles,
                "backend": main.MODEL_BACKENDS[model]["label"],
                "catalog": main._catalog_entry_display(catalog_entry, None),
                "catalog_source": (catalog_entry or provider_default_entry or {}).get("source") if (catalog_entry or provider_default_entry) else None,
                "pricing_source": (catalog_entry or provider_default_entry or {}).get("pricing_source")
                if (catalog_entry or provider_default_entry)
                else None,
                "catalog_size": len(provider_catalog),
            }
        )
    return {
        "command": "models",
        "schema": json_schema("models"),
        "models": models,
        "preferred_model": status["preferred_model"],
        "preferred_provider": status["preferred_model"],
    }


def _model_limits_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    report = _provider_limit_status_report(agent, config)
    return {
        "command": "model limits",
        "schema": json_schema("model limits"),
        "summary": _provider_limit_summary_report(report),
        "providers": [_provider_limit_entry_view(item, include_accounts=True) for item in report["providers"]],
    }


def _render_model_limits(agent: Agent, config: AgentConfig) -> str:
    report = _model_limits_report(agent, config)
    lines = ["Model/provider limits:"]
    if not report["providers"]:
        lines.append("- none")
        return "\n".join(lines)
    summary = report["summary"]
    lines.append(
        "- summary: "
        f"blocked_models={','.join(summary['blocked_models']) if summary['blocked_models'] else 'none'} "
        f"stale_models={','.join(summary['stale_models']) if summary['stale_models'] else 'none'} "
        f"blocked_accounts={','.join(summary['blocked_accounts']) if summary['blocked_accounts'] else 'none'} "
        f"stale_accounts={','.join(summary['stale_accounts']) if summary['stale_accounts'] else 'none'}"
    )
    for item in report["providers"]:
        blocked = f" blocked_until={item['blocked_until']}" if item["blocked_until"] else ""
        reason = f" reason={item['reason']}" if item["reason"] else ""
        window = f" window={item['rate_limit_type']}" if item["rate_limit_type"] else ""
        utilization = f" utilization={item['utilization']}%" if item["utilization"] is not None else ""
        captured = f" captured_at={item['captured_at']}" if item["captured_at"] else ""
        lines.append(
            f"- {item['provider']}: {item['status']}{blocked}{reason}{window}{utilization}{captured} "
            f"account={item['account']} provider_model={item['provider_model']} "
            f"selection={item['provider_model_selection']}"
        )
        if item["provider_model_params"]:
            lines.append(
                "  params="
                + ",".join(f"{key}={value}" for key, value in sorted(item["provider_model_params"].items()))
            )
        for account in item["blocked_accounts"]:
            account_reason = f" reason={account['reason']}" if account["reason"] else ""
            lines.append(
                f"  account {account['name']}: blocked_until={account['blocked_until']}{account_reason}"
            )
    return "\n".join(lines)


def _render_model_usage(config: AgentConfig) -> str:
    try:
        return MemoryStore.load(config.memory_path).model_usage_summary()
    except (OSError, ValueError, TypeError):
        return "Model usage:\n- no model attempts recorded"


def _model_usage_report(config: AgentConfig) -> dict[str, object]:
    try:
        report = MemoryStore.load(config.memory_path).model_usage_stats()
    except (OSError, ValueError, TypeError):
        report = MemoryStore().model_usage_stats()
    return {
        "command": "models usage",
        "schema": json_schema("models usage"),
        "report": report,
        "policy": {
            "routing_budget": "prefer cloud analysis first (cheap/chatgpt/openai/claude); use local only when available and selected from discovered local-model characteristics or as fallback.",
        },
    }


def _status_pricing_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    model_report = _model_status_report(agent, config)
    selected = _selected_model_report(model_report)
    catalog = selected.get("catalog", {}) if isinstance(selected, dict) else {}
    pricing_source = None
    if isinstance(catalog, dict):
        pricing_source = catalog.get("pricing_source")
    if pricing_source is None and isinstance(selected, dict):
        pricing_source = selected.get("pricing_source")
    if pricing_source is None and isinstance(selected, dict):
        pricing_source = "local" if selected.get("model") == "local" else "openrouter"
    return {
        "active_model": None
        if selected is None
        else {
            "provider": selected.get("provider"),
            "provider_model": selected.get("provider_model"),
            "catalog_source": selected.get("catalog_source"),
        },
        "source": pricing_source or "unknown",
        "catalog_source": None if not isinstance(catalog, dict) else catalog.get("catalog_source"),
        "cost_per_input_token_usd": None if not isinstance(catalog, dict) else catalog.get("cost_per_input_token_usd"),
        "cost_per_output_token_usd": None if not isinstance(catalog, dict) else catalog.get("cost_per_output_token_usd"),
        "blended_price_usd_per_1m_tokens": None if not isinstance(catalog, dict) else catalog.get("blended_price_usd_per_1m_tokens"),
    }


def _status_cost_sidebar_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    handoff = ProjectHandoff.load(config.handoff_path)
    runtime = handoff.prince2_node_runtime if isinstance(handoff.prince2_node_runtime, dict) else {}
    nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
    total_input_cost = 0.0
    total_output_cost = 0.0
    total_cost = 0.0
    total_tokens = 0
    cost_nodes: list[dict[str, object]] = []
    for node in nodes:
        input_cost = float(node.get("business_case_input_cost_usd", 0.0) or 0.0)
        output_cost = float(node.get("business_case_output_cost_usd", 0.0) or 0.0)
        node_cost = float(node.get("business_case_cost_usd", input_cost + output_cost) or 0.0)
        total_input_cost += input_cost
        total_output_cost += output_cost
        total_cost += node_cost
        total_tokens += int(node.get("business_case_token_count", 0) or 0)
        cost_nodes.append(
            {
                "node_id": node.get("node_id"),
                "label": node.get("label"),
                "mnemonic": node.get("mnemonic"),
                "team_name": node.get("team_name"),
                "mode": node.get("mode", "manual"),
                "provider": node.get("provider"),
                "provider_model": node.get("provider_model"),
                "business_case_token_count": int(node.get("business_case_token_count", 0) or 0),
                "business_case_cost_usd": node_cost,
                "business_case_input_cost_usd": input_cost,
                "business_case_output_cost_usd": output_cost,
            }
        )
    cost_nodes.sort(key=lambda item: float(item.get("business_case_cost_usd", 0.0) or 0.0), reverse=True)
    pricing = _status_pricing_report(agent, config)
    usage = _model_usage_report(config)["report"]
    return {
        "command": "cost",
        "schema": json_schema("status"),
        "business_case": {
            "nodes": len(nodes),
            "tokens": total_tokens,
            "input_cost_usd": round(total_input_cost, 8),
            "output_cost_usd": round(total_output_cost, 8),
            "total_cost_usd": round(total_cost, 8),
        },
        "active_pricing": pricing,
        "model_usage": usage,
        "node_costs": cost_nodes,
        "top_nodes": cost_nodes[:5],
    }


def _render_cost_sidebar(agent: Agent, config: AgentConfig) -> str:
    report = _status_cost_sidebar_report(agent, config)
    business_case = report["business_case"] if isinstance(report.get("business_case"), dict) else {}
    active_pricing = report["active_pricing"] if isinstance(report.get("active_pricing"), dict) else {}
    usage = report["model_usage"] if isinstance(report.get("model_usage"), dict) else {}
    totals = usage.get("totals", {}) if isinstance(usage.get("totals"), dict) else {}
    try:
        failure_rate = float(totals.get("failure_rate", 0) or 0.0)
    except (TypeError, ValueError):
        failure_rate = 0.0
    lines = [
        "Cost sidebar:",
        f"- business_case_nodes: {business_case.get('nodes', 0)}",
        f"- business_case_tokens: {business_case.get('tokens', 0)}",
        f"- business_case_input_cost_usd: {business_case.get('input_cost_usd', 0)}",
        f"- business_case_output_cost_usd: {business_case.get('output_cost_usd', 0)}",
        f"- business_case_total_cost_usd: {business_case.get('total_cost_usd', 0)}",
        (
            "- active_pricing: "
            f"source={active_pricing.get('source', 'unknown')} "
            f"provider={active_pricing.get('active_model', {}).get('provider') if active_pricing.get('active_model') else 'none'} "
            f"provider_model={active_pricing.get('active_model', {}).get('provider_model') if active_pricing.get('active_model') else 'none'} "
            f"input={active_pricing.get('cost_per_input_token_usd', 'none')} "
            f"output={active_pricing.get('cost_per_output_token_usd', 'none')}"
        ),
        (
            "- model_usage: "
            f"calls={totals.get('calls', 0)} failures={totals.get('failures', 0)} "
            f"failure_rate={failure_rate:.2f}%"
        ),
    ]
    top_nodes = [node for node in report.get("top_nodes", []) if isinstance(node, dict)]
    if top_nodes:
        lines.append("- top_cost_nodes:")
        for node in top_nodes:
            lines.append(
                f"  - {node.get('label')} [{node.get('node_id')}]: mnemonic={node.get('mnemonic', 'none')} "
                f"team={node.get('team_name', 'none')} mode={node.get('mode', 'manual')} "
                f"provider={node.get('provider', 'none')} provider_model={node.get('provider_model', 'none')} "
                f"tokens={node.get('business_case_token_count', 0)} "
                f"cost_usd={node.get('business_case_cost_usd', 0)} "
                f"input_cost_usd={node.get('business_case_input_cost_usd', 0)} "
                f"output_cost_usd={node.get('business_case_output_cost_usd', 0)}"
            )
    else:
        lines.append("- top_cost_nodes: none")
    return "\n".join(lines)


def _status_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    main._apply_model_preferences(agent, config)
    caveman_state = agent.caveman.load_state(config)
    mode = f"caveman {caveman_state.level}" if caveman_state.active else "normal"
    handoff = ProjectHandoff.load(config.handoff_path)
    provider_limits = _provider_limit_status_report(agent, config)
    permissions = main._permissions_report(config)
    stage_view = handoff.stage_view()
    local_fallback = main._delivery_local_fallback_report(config)
    pricing = _status_pricing_report(agent, config)
    return {
        "command": "status",
        "schema": json_schema("status"),
        "workspace": str(config.workspace_root),
        "mode": mode,
        "files": {
            "memory": config.memory_path.name,
            "trace": config.trace_path.name,
            "handoff": config.handoff_path.name,
            "model_config": config.model_prefs_path.name,
        },
        "models": _model_status_report(agent, config),
        "baseline": main._agent_baseline_report(config),
        "goal": handoff.goal_view(),
        "provider_limits": provider_limits,
        "limits_summary": _provider_limit_summary_report(provider_limits),
        "runtime": main.detect_runtime_capabilities(config.workspace_root),
        "shell_backend": main._shell_backend_report(config),
        "focus": main._focus_snapshot(agent, config),
        "roles": main._prince2_roles_report(config),
        "permissions": permissions,
        "pricing": pricing,
        "handoff": {
            "summary": handoff.summary(),
            "operational_posture": handoff.rendered_operational_posture(),
            "stage_view": stage_view,
        },
        "local_fallback": local_fallback,
        "remediations": main._status_remediation_report(provider_limits=provider_limits, stage_view=stage_view, config=config),
    }


def _status_dashboard_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    status = _status_report(agent, config)
    provider_limits = status["provider_limits"]
    model_report = status["models"]
    pricing = _status_pricing_report(agent, config)
    handoff = status["handoff"]["stage_view"]
    git = GitTool(config)
    git_status = git.status()
    git_head = git.head()
    workspace_settings = status["permissions"]["effective"]
    active_model = next((item for item in model_report["models"] if item["preferred"]), None)
    if active_model is None:
        active_model = next((item for item in model_report["models"] if item["active"]), None)
    providers = provider_limits["providers"]
    focus = main._focus_snapshot(agent, config)
    budget = _project_state_views.budget_report(config)["budget"]
    question = _project_state_views.question_report(config)["user_question"]
    return {
        "command": "status",
        "view": "full",
        "schema": json_schema("status"),
        "identity": {
            "name": "Stagewarden",
            "workspace": status["workspace"],
            "mode": status["mode"],
            "python": platform.python_version(),
        },
        "model": {
            "preferred_model": model_report["preferred_model"] or "automatic",
            "preferred_provider": model_report["preferred_provider"] or "automatic",
            "active_model": None if active_model is None else active_model["model"],
            "active_provider": None if active_model is None else active_model["model"],
            "active_variant": None if active_model is None else active_model["variant"],
            "active_provider_model": None if active_model is None else active_model["provider_model"],
            "active_provider_model_params": {} if active_model is None else active_model["provider_model_params"],
            "enabled": [item["model"] for item in model_report["models"] if item["enabled"]],
            "active": [item["model"] for item in model_report["models"] if item["active"]],
        },
        "account": {
            "active_accounts": {
                item["provider"]: item["active_account"]
                for item in providers
            },
            "auth_modes": {
                item["model"]: item["auth"]
                for item in model_report["models"]
            },
        },
        "limits": [_provider_limit_entry_view(item, include_accounts=True) for item in providers],
        "limits_summary": _provider_limit_summary_report(provider_limits),
        "workspace": {
            "cwd": status["workspace"],
            "files": status["files"],
        },
        "runtime": status["runtime"],
        "shell_backend": status["shell_backend"],
        "permissions": {
            "mode": workspace_settings["mode"],
            "allow": workspace_settings["allow"],
            "ask": workspace_settings["ask"],
            "deny": workspace_settings["deny"],
        },
        "pricing": pricing,
        "cost_sidebar": _status_cost_sidebar_report(agent, config),
        "git": {
            "ok": git_status.ok,
            "head": git_head.stdout.strip() if git_head.ok else None,
            "status": git_status.stdout.strip() if git_status.ok else git_status.error,
        },
        "handoff": {
            "stage_health": handoff["stage_health"],
            "recovery_state": handoff["recovery_state"],
            "boundary_decision": handoff["boundary_decision"],
            "next_action": handoff["next_action"],
            "git_boundary": handoff["git_boundary"],
            "register_statuses": handoff["register_statuses"],
            "backlog_statuses": handoff["backlog_statuses"],
            "node_runtime_summary": handoff["node_runtime_summary"],
        },
        "baseline": status["baseline"],
        "goal": status["goal"],
        "budget": budget,
        "user_question": question,
        "local_fallback": status["local_fallback"],
        "focus": focus,
        "usage": _model_usage_report(config)["report"],
        "quality_gates": {
            "wet_run_required": True,
            "dry_run_valid_checkpoint": False,
            "git_snapshot_required": True,
            "provider_limits_stale_after_minutes": 15,
        },
        "remediations": status["remediations"],
    }


def _render_status_full(agent: Agent, config: AgentConfig) -> str:
    report = _status_dashboard_report(agent, config)
    model = report["model"] if isinstance(report.get("model"), dict) else {}
    account = report["account"] if isinstance(report.get("account"), dict) else {}
    usage = report["usage"] if isinstance(report.get("usage"), dict) else {}
    cost_sidebar = report["cost_sidebar"] if isinstance(report.get("cost_sidebar"), dict) else {}
    lines = [
        "Stagewarden status (full):",
        f"- workspace: {report['identity']['workspace']}",
        f"- mode: {report['identity']['mode']}",
        f"- python: {report['identity']['python']}",
        (
            f"- model: preferred={model.get('preferred_model', 'automatic')} "
            f"active={model.get('active_model', 'none')} "
            f"variant={model.get('active_variant', 'none')} "
            f"provider_model={model.get('active_provider_model', 'none')}"
        ),
        (
            f"- account: active={account.get('active_accounts', {})} "
            f"auth_modes={account.get('auth_modes', {})}"
        ),
        (
            "- limits_summary: "
            f"blocked_models={','.join(report['limits_summary'].get('blocked_models', [])) if isinstance(report.get('limits_summary'), dict) and report['limits_summary'].get('blocked_models') else 'none'} "
            f"stale_models={','.join(report['limits_summary'].get('stale_models', [])) if isinstance(report.get('limits_summary'), dict) and report['limits_summary'].get('stale_models') else 'none'} "
            f"blocked_accounts={','.join(report['limits_summary'].get('blocked_accounts', [])) if isinstance(report.get('limits_summary'), dict) and report['limits_summary'].get('blocked_accounts') else 'none'} "
            f"stale_accounts={','.join(report['limits_summary'].get('stale_accounts', [])) if isinstance(report.get('limits_summary'), dict) and report['limits_summary'].get('stale_accounts') else 'none'}"
        ),
        f"- pricing_source: {report['pricing']['source'] if isinstance(report.get('pricing'), dict) else 'unknown'}",
        f"- budget: {report['budget']}",
        f"- goal: {report['goal']}",
        f"- user_question: {report['user_question']}",
        f"- git_head: {report['git']['head'] if isinstance(report.get('git'), dict) else 'unknown'}",
        f"- usage_calls: {usage.get('calls', 0)}",
        f"- usage_failures: {usage.get('failures', 0)}",
    ]
    if cost_sidebar:
        lines.append(
            f"- cost_sidebar: nodes={cost_sidebar.get('business_case', {}).get('nodes', 0) if isinstance(cost_sidebar.get('business_case'), dict) else 0} "
            f"tokens={cost_sidebar.get('business_case', {}).get('tokens', 0) if isinstance(cost_sidebar.get('business_case'), dict) else 0} "
            f"total_cost_usd={cost_sidebar.get('business_case', {}).get('total_cost_usd', 0) if isinstance(cost_sidebar.get('business_case'), dict) else 0}"
        )
        lines.append("Node cost breakdown:")
        for line in _render_cost_sidebar(agent, config).splitlines():
            lines.append(f"  {line}")
    lines.append(f"- quality_gates: {report['quality_gates']}")
    return "\n".join(lines)


def _statusline_rate_limit(item: dict[str, object]) -> dict[str, object]:
    entry = _provider_limit_entry_view(item, include_accounts=False)
    return {
        "provider": entry["provider"],
        "account": entry["account"],
        "status": entry["status"],
        "blocked_until": entry["blocked_until"],
        "reason": entry["reason"],
        "rate_limit_type": entry["rate_limit_type"],
        "stale": entry["stale"],
        "blocked_accounts": entry["blocked_accounts_count"],
        "used_percentage": entry["utilization"],
        "utilization": entry["utilization"],
        "resets_at": entry["resets_at"],
        "overage_status": entry["overage_status"],
        "overage_resets_at": entry["overage_resets_at"],
        "overage_disabled_reason": entry["overage_disabled_reason"],
    }


def _statusline_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    status = _status_report(agent, config)
    usage = _model_usage_report(config)["report"]
    memory = MemoryStore.load(config.memory_path)
    git = GitTool(config)
    git_head = git.head()
    provider_limits = status["provider_limits"]["providers"]
    preferred = status["models"]["preferred_model"]
    active_model = next((item for item in status["models"]["models"] if item["preferred"]), None)
    if active_model is None:
        active_model = next((item for item in status["models"]["models"] if item["active"]), None)
    return {
        "command": "statusline",
        "schema": json_schema("statusline"),
        "workspace": {
            "current_dir": status["workspace"],
            "project_dir": status["workspace"],
            "added_dirs": [],
            "git_head": git_head.stdout.strip() if git_head.ok else None,
            "git_worktree": None,
        },
        "version": "stagewarden",
        "model": {
            "preferred": preferred or "automatic",
            "preferred_provider": preferred or "automatic",
            "active": None if active_model is None else active_model["model"],
            "active_provider": None if active_model is None else active_model["model"],
            "variant": None if active_model is None else active_model["variant"],
            "provider_model": None if active_model is None else active_model["provider_model"],
            "provider_model_selection": None if active_model is None else active_model["provider_model_selection"],
            "provider_model_params": {} if active_model is None else active_model["provider_model_params"],
        },
        "context_window": memory.context_window_stats(),
        "rate_limits": [_statusline_rate_limit(item) for item in provider_limits],
        "rate_limits_summary": _provider_limit_summary_report(status["provider_limits"]),
        "baseline": {
            "status": status["baseline"]["status"],
            "ok": status["baseline"]["ok"],
            "missing": status["baseline"]["missing"],
        },
        "local_fallback": status["local_fallback"],
        "goal": status["goal"],
        "handoff": status["handoff"]["stage_view"],
        "latest_handoff_action": status["focus"].get("latest_handoff_action"),
        "usage": usage["totals"],
    }


def _overview_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    return {
        "command": "overview",
        "schema": json_schema("overview"),
        "status": _status_report(agent, config),
        "board": main._board_report(config),
        "model_usage": _model_usage_report(config),
        "provider_limits": _provider_limit_status_report(agent, config),
        "transcript": main._transcript_report(config),
        "handoff": main._handoff_report(config),
    }


def _health_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    board = main._board_report(config)
    status = _status_report(agent, config)
    usage = _model_usage_report(config)["report"]
    transcript = main._transcript_report(config)["report"]
    log_errors = main._log_error_report(config)
    ready = (
        board["recommended_authorization"] in {"continue", "close"}
        and board["open_issues"] == 0
        and board["recovery_state"] == "none"
        and log_errors["count"] == 0
    )
    return {
        "command": "health",
        "schema": json_schema("health"),
        "workspace": status["workspace"],
        "mode": status["mode"],
        "ready": ready,
        "recommended_authorization": board["recommended_authorization"],
        "boundary_decision": board["boundary_decision"],
        "open_issues": board["open_issues"],
        "open_risks": board["open_risks"],
        "quality_open": board["quality_open"],
        "recovery_state": board["recovery_state"],
        "next_action": board["next_action"],
        "model_failures": usage["totals"]["failures"],
        "model_calls": usage["totals"]["calls"],
        "transcript_entries": transcript["count"],
        "log_errors": log_errors,
    }


def _preflight_remediations(
    *,
    doctor: dict[str, object],
    runtime: dict[str, object],
    shell_backend: dict[str, object],
    git_status: object,
    git_dirty: object,
    role_check: dict[str, object],
    provider_limits: dict[str, object],
    sources: dict[str, object],
    stage_view: dict[str, object],
    log_errors: dict[str, object],
) -> list[dict[str, str]]:
    main = _main()
    items: list[dict[str, str]] = []
    if not doctor.get("python", {}).get("ok"):  # type: ignore[union-attr]
        items.append({"severity": "blocker", "code": "python", "action": "Install Python 3.11+ and rerun `/preflight`."})
    if not doctor.get("git", {}).get("ok"):  # type: ignore[union-attr]
        items.append({"severity": "blocker", "code": "git", "action": "Install git; Stagewarden requires git for every project."})
    if not shell_backend.get("available"):
        items.append({"severity": "blocker", "code": "shell_backend", "action": "Choose an available backend with `/shell backend use <auto|bash|zsh|powershell|cmd>`."})
    runtime_shells = runtime.get("shells", {}) if isinstance(runtime, dict) else {}
    bash_info = runtime_shells.get("bash", {}) if isinstance(runtime_shells, dict) else {}
    if runtime.get("os_family") == "windows" and not bash_info.get("available"):
        items.append(
            {
                "severity": "warning",
                "code": "windows_shell_readiness",
                "action": "Bash is not available on this Windows runtime; bash-required or POSIX-only commands will be rejected unless you install bash or translate them.",
            }
        )
    if not role_check.get("ok"):
        items.append(
            {
                "severity": "blocker",
                "code": "roles",
                "action": "Run `/roles setup` or `/roles propose` and approve the baseline before role-routed work.",
            }
        )
    if not sources.get("ok"):
        items.append(
            {
                "severity": "warning",
                "code": "sources",
                "action": "Run `/sources status` and refresh any missing source references before source-derived implementation work.",
            }
        )
    if log_errors.get("count", 0) > 0:
        items.append(
            {
                "severity": "blocker",
                "code": "log_errors",
                "action": f"Recent logs contain {log_errors.get('count', 0)} error entry(s). Inspect `/transcript` and the memory log, then rerun the battery/preflight check.",
            }
        )
    if provider_limits.get("providers"):
        for item in provider_limits.get("providers", []):
            if not isinstance(item, dict) or not item.get("blocked_until"):
                continue
            items.append(
                {
                    "severity": "warning",
                    "code": f"provider_{item.get('provider')}",
                    "action": f"Provider {item.get('provider')} is blocked until {item.get('blocked_until')}; prefer a different provider or wait for the reset.",
                }
            )
    if stage_view.get("boundary_decision") in {"review_boundary:no_plan_status", "review_boundary:incomplete"}:
        items.append(
            {
                "severity": "warning",
                "code": "handoff_boundary",
                "action": "The current handoff boundary still needs review. Confirm the current stage and plan status before advancing.",
            }
        )
    if not items:
        items.append({"severity": "info", "code": "ready", "action": "All preflight checks passed."})
    return items


def _status_remediation_report(
    *,
    provider_limits: dict[str, object],
    stage_view: dict[str, object],
    config: AgentConfig,
) -> list[dict[str, str]]:
    main = _main()
    git = GitTool(config)
    git_status = git.status()
    git_dirty = git.status_porcelain()
    items = _preflight_remediations(
        doctor={"python": {"ok": True}, "git": {"ok": True}},
        runtime=main.detect_runtime_capabilities(config.workspace_root),
        shell_backend=main._shell_backend_report(config),
        git_status=git_status,
        git_dirty=git_dirty,
        role_check=main._prince2_role_check_report(config),
        provider_limits=provider_limits,
        sources=main._sources_status_report(config),
        stage_view=stage_view,
        log_errors=main._log_error_report(config),
    )
    local_fallback = main._delivery_local_fallback_report(config)
    if local_fallback["status"] == "available":
        items.append(
            {
                "severity": "warning",
                "code": "local_fallback_partial",
                "action": (
                    "Discovered local fallback candidates exist but are not preloaded on every delivery node. "
                    "Run `/roles setup`, `/role assign`, or `/project start` to preload the recommended local fallback routes."
                ),
            }
        )
    elif local_fallback["status"] == "missing" and int(local_fallback.get("delivery_nodes", 0) or 0) > 0:
        items.append(
            {
                "severity": "info",
                "code": "local_fallback_missing",
                "action": (
                    "No local fallback candidates are available for the current delivery nodes. "
                    "Continue on cloud providers or start Ollama and rerun discovery before planning local fallback execution."
                ),
            }
        )
    return items


def _preflight_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    doctor = _doctor_report(config)
    git = GitTool(config)
    git_status = git.status()
    git_head = git.head()
    git_dirty = git.status_porcelain()
    role_check = main._prince2_role_check_report(config)
    provider_limits = _provider_limit_status_report(agent, config)
    sources = main._sources_status_report(config)
    handoff = ProjectHandoff.load(config.handoff_path)
    log_errors = main._log_error_report(config)
    stage_view = handoff.stage_view()
    remediations = _preflight_remediations(
        doctor=doctor,
        runtime=doctor["runtime"],
        shell_backend=main._shell_backend_report(config),
        git_status=git_status,
        git_dirty=git_dirty,
        role_check=role_check,
        provider_limits=provider_limits,
        sources=sources,
        stage_view=stage_view,
        log_errors=log_errors,
    )
    ready = not any(item["severity"] == "blocker" for item in remediations) and log_errors["count"] == 0
    return {
        "command": "preflight",
        "schema": json_schema("preflight"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "ready": ready,
        "doctor": doctor,
        "runtime": doctor["runtime"],
        "shell_backend": main._shell_backend_report(config),
        "git": {
            "ok": git_status.ok,
            "head": git_head.stdout.strip() if git_head.ok else None,
            "status": git_status.stdout.strip() if git_status.ok else git_status.error,
            "dirty": bool(git_dirty.ok and git_dirty.stdout.strip()),
            "dirty_paths": git_dirty.stdout.splitlines() if git_dirty.ok and git_dirty.stdout else [],
        },
        "roles_check": role_check,
        "provider_limits": provider_limits,
        "baseline": main._agent_baseline_report(config),
        "sources": sources,
        "permissions": main._permissions_report(config),
        "handoff": {
            "summary": handoff.summary(),
            "stage_view": stage_view,
        },
        "log_errors": log_errors,
        "remediations": remediations,
    }


def _report_report(agent: Agent, config: AgentConfig) -> dict[str, object]:
    main = _main()
    handoff = ProjectHandoff.load(config.handoff_path)
    board = main._board_report(config)
    usage = _model_usage_report(config)["report"]
    transcript = main._transcript_report(config)["report"]
    stage_view = handoff.stage_view()
    register_statuses = stage_view["register_statuses"]
    governance_status = (
        "clean"
        if register_statuses["issues_open"] == 0
        and register_statuses["risks_open"] == 0
        and register_statuses["quality_open"] == 0
        else "residual_controls"
    )
    lessons = [
        f"[{item.get('type', 'lesson')}] {item.get('step_id', '-')} :: {item.get('lesson', '')}"
        for item in handoff.lessons_log[-3:]
    ]
    backlog = [
        f"[{str(item.get('status', 'planned')).strip().lower() or 'planned'}] {item.get('step_id', '-')} :: {item.get('title', '')}"
        for item in handoff.implementation_backlog[:5]
    ]
    return {
        "command": "report",
        "schema": json_schema("report"),
        "task": handoff.task or "unknown",
        "project_status": handoff.status,
        "current_step": handoff.current_step_id or "none",
        "stage_health": stage_view["stage_health"],
        "recommended_authorization": board["recommended_authorization"],
        "boundary_decision": board["boundary_decision"],
        "next_action": board["next_action"],
        "open_issues": board["open_issues"],
        "open_risks": board["open_risks"],
        "quality_open": board["quality_open"],
        "recovery_state": board["recovery_state"],
        "governance_status": governance_status,
        "model_calls": usage["totals"]["calls"],
        "model_failures": usage["totals"]["failures"],
        "escalation_path": usage["totals"]["escalation_path"],
        "provider_limits": _provider_limit_status_report(agent, config),
        "transcript_entries": transcript["count"],
        "recent_lessons": lessons,
        "backlog_preview": backlog,
    }


def _doctor_report(config: AgentConfig) -> dict[str, object]:
    python_ok = sys.version_info >= (3, 11)
    report: dict[str, object] = {
        "command": "doctor",
        "schema": json_schema("doctor"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "python": {
            "ok": python_ok,
            "status": "OK" if python_ok else "FAIL",
            "version": platform.python_version(),
            "required": ">=3.11",
            "executable": sys.executable,
        },
        "git": {},
        "path_launcher": {},
        "repository": {},
        "runtime": _main().detect_runtime_capabilities(config.workspace_root),
        "baseline": _main()._agent_baseline_report(config),
        "providers": [],
        "policy": {
            "silent_install": False,
            "note": "no prerequisites are installed silently by doctor.",
        },
    }

    git_path = shutil.which("git")
    if git_path:
        git_available = GitTool(config).ensure_available()
        if git_available.ok:
            version = git_available.stdout.strip() or "git available"
            report["git"] = {
                "ok": True,
                "status": "OK",
                "message": version,
                "path": git_path,
            }
        else:
            report["git"] = {
                "ok": False,
                "status": "FAIL",
                "message": git_available.error or "git is not usable",
                "path": git_path,
            }
    else:
        report["git"] = {
            "ok": False,
            "status": "FAIL",
            "message": "git executable not found in PATH. Install git before running Stagewarden.",
            "path": None,
        }

    launcher = shutil.which("stagewarden")
    if launcher:
        report["path_launcher"] = {
            "ok": True,
            "status": "OK",
            "path": launcher,
            "message": launcher,
        }
    else:
        report["path_launcher"] = {
            "ok": False,
            "status": "WARN",
            "path": None,
            "message": "`stagewarden` not found in PATH; run setup.sh/setup.ps1 or use python -m stagewarden.main.",
        }

    repo_probe = GitTool(config)._run(["git", "rev-parse", "--is-inside-work-tree"])
    if repo_probe.ok and repo_probe.stdout.strip() == "true":
        report["repository"] = {
            "ok": True,
            "status": "OK",
            "message": "current workspace is a git worktree",
        }
    else:
        report["repository"] = {
            "ok": False,
            "status": "WARN",
            "message": "current workspace is not a git worktree; Stagewarden will initialize one during normal agent startup.",
        }

    providers: list[dict[str, object]] = []
    main = _main()
    for model in main.REGISTRY_MODELS:
        capability = main.provider_capability(model)
        token_state = "n/a"
        if capability.token_env:
            token_state = "set" if os.environ.get(capability.token_env) else f"missing:{capability.token_env}"
        providers.append(
            {
                "provider": model,
                "auth": capability.auth_type,
                "profiles": capability.supports_account_profiles,
                "browser_login": capability.supports_browser_login,
                "api_key": capability.supports_api_key,
                "token_env": token_state,
                "default_model": capability.default_model,
            }
        )
    report["providers"] = providers
    return report


def _doctor_ok(rendered: str) -> bool:
    return "\n- Python: FAIL" not in rendered and "\n- Git: FAIL" not in rendered


def _render_preflight(agent: Agent, config: AgentConfig) -> str:
    report = _preflight_report(agent, config)
    lines = [
        "Stagewarden preflight:",
        f"- ready: {str(report['ready']).lower()}",
        f"- log_errors: {report['log_errors']['status']} count={report['log_errors']['count']}",
        "Remediations:",
    ]
    if report["remediations"]:
        for item in report["remediations"]:
            lines.append(f"- {item['severity']} {item['code']}: {item['action']}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def _render_report(agent: Agent, config: AgentConfig) -> str:
    report = _report_report(agent, config)
    lines = [
        "Project report:",
        f"- task: {report['task']}",
        f"- project_status: {report['project_status']}",
        f"- current_step: {report['current_step']}",
        f"- stage_health: {report['stage_health']}",
        f"- governance_status: {report['governance_status']}",
        f"- recommended_authorization: {report['recommended_authorization']}",
        f"- boundary_decision: {report['boundary_decision']}",
        f"- next_action: {report['next_action']}",
        f"- open_issues: {report['open_issues']}",
        f"- open_risks: {report['open_risks']}",
        f"- quality_open: {report['quality_open']}",
        f"- recovery_state: {report['recovery_state']}",
        f"- model_calls: {report['model_calls']}",
        f"- model_failures: {report['model_failures']}",
        f"- escalation_path: {report['escalation_path']}",
        f"- provider_limits: {_main()._provider_limit_summary(agent, config)}",
        f"- transcript_entries: {report['transcript_entries']}",
        "Recent lessons:",
    ]
    if report["recent_lessons"]:
        for item in report["recent_lessons"]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("Backlog preview:")
    if report["backlog_preview"]:
        for item in report["backlog_preview"]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def _render_doctor(config: AgentConfig) -> str:
    report = _doctor_report(config)
    python_info = report["python"]
    git_info = report["git"]
    path_info = report["path_launcher"]
    repo_info = report["repository"]
    runtime_info = report["runtime"]
    shell_backend = _main()._shell_backend_report(config)
    providers = report["providers"]
    policy_info = report["policy"]
    baseline_info = report["baseline"]
    lines = ["Stagewarden doctor:"]
    lines.append(
        f"- Python: {python_info['status']} {python_info['version']} "
        f"(required {python_info['required']}, executable={python_info['executable']})"
    )
    if git_info.get("ok"):
        lines.append(f"- Git: OK {git_info['message']} ({git_info['path']})")
    else:
        lines.append(f"- Git: FAIL {git_info['message']}")
    if path_info.get("ok"):
        lines.append(f"- PATH launcher: OK {path_info['message']}")
    else:
        lines.append(f"- PATH launcher: WARN {path_info['message']}")
    lines.append(f"- Repository: {repo_info['status']} {repo_info['message']}")
    lines.append(
        f"- Runtime: os={runtime_info['os_family']} shell={runtime_info['recommended_shell']} "
        f"default={runtime_info['default_shell'] or 'none'} line_ending={runtime_info['line_ending']}"
    )
    lines.append(
        f"- Shell backend: configured={shell_backend['configured']} selected={shell_backend['selected'] or 'none'} "
        f"available={str(shell_backend['available']).lower()}"
    )
    lines.append(
        f"- Baseline: {baseline_info['status']} "
        f"missing={len(baseline_info['missing'])} groups={len(baseline_info['groups'])}"
    )
    if baseline_info["remediations"]:
        lines.append("Baseline remediations:")
        for item in baseline_info["remediations"]:
            lines.append(f"- {item['code']}: {item['action']}")
    lines.append("Provider capabilities:")
    for provider in providers:
        lines.append(
            f"- {provider['provider']}: auth={provider['auth']} profiles={'yes' if provider['profiles'] else 'no'} "
            f"browser_login={'yes' if provider['browser_login'] else 'no'} api_key={'yes' if provider['api_key'] else 'no'} "
            f"token_env={provider['token_env']} default_model={provider['default_model']}"
        )
    lines.append(f"- Policy: {policy_info['note']}")
    return "\n".join(lines)
