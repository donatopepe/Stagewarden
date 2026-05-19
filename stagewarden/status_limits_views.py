from __future__ import annotations

from datetime import datetime

from .agent import Agent
from .config import AgentConfig
from .json_schema_registry import json_schema
from .memory import MemoryStore
from .modelprefs import account_key, limit_snapshot_from_message
from . import model_views as _model_views
from .runtime_env import detect_runtime_capabilities
from .provider_registry import SUPPORTED_MODELS as REGISTRY_MODELS, provider_capability
from .handoff import MODEL_BACKENDS
from .tools.git import GitTool


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
    prefs = _model_views._load_model_preferences(config)
    _model_views._apply_model_preferences(agent, config)
    capabilities = detect_runtime_capabilities(config.workspace_root)
    memory = MemoryStore.load(config.memory_path)
    providers = []
    for provider in REGISTRY_MODELS:
        capability = provider_capability(provider)
        active_account = (prefs.active_account_by_model or {}).get(provider)
        if active_account and (prefs.blocked_until_by_account or {}).get(account_key(provider, active_account)):
            active_account = None
        provider_model = capability.default_model
        snapshot = (prefs.provider_limit_snapshot_by_model or {}).get(provider)
        provider_accounts: set[str] = set((prefs.accounts_by_model or {}).get(provider, []))
        for key in (prefs.blocked_until_by_account or {}).keys():
            if key.startswith(f"{provider}:"):
                provider_accounts.add(key.split(":", 1)[1])
        for key in (prefs.provider_limit_snapshot_by_account or {}).keys():
            if key.startswith(f"{provider}:"):
                provider_accounts.add(key.split(":", 1)[1])
        for key in (prefs.last_limit_message_by_account or {}).keys():
            if key.startswith(f"{provider}:"):
                provider_accounts.add(key.split(":", 1)[1])
        blocked_accounts = []
        for account in sorted(provider_accounts):
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
        provider_attempts = [item for item in memory.attempts if item.model == provider]
        last_attempt = provider_attempts[-1] if provider_attempts else None
        last_success = next((item for item in reversed(provider_attempts) if item.success), None)
        last_limit_message = (prefs.last_limit_message_by_model or {}).get(provider)
        if last_limit_message is None and isinstance(snapshot, dict):
            last_limit_message = snapshot.get("raw_message")
        if last_limit_message is None:
            last_limit_message = next(
                (account.get("last_limit_message") for account in blocked_accounts if account.get("last_limit_message")),
                None,
            )
        providers.append(
            {
                "provider": provider,
                "variant": capability.default_model,
                "provider_model": provider_model,
                "provider_model_selection": "dynamic",
                "provider_model_params": {},
                "active_account": active_account or "none",
                "blocked_until": (prefs.blocked_until_by_model or {}).get(provider),
                "last_error_reason": provider_reason or (prefs.last_limit_message_by_model or {}).get(provider),
                "last_limit_message": last_limit_message,
                "last_attempt": None
                if last_attempt is None
                else {
                    "iteration": last_attempt.iteration,
                    "step_id": last_attempt.step_id,
                    "account": last_attempt.account or "none",
                    "variant": last_attempt.variant or "provider-default",
                    "status": "ok" if last_attempt.success else f"failed:{last_attempt.error_type or 'unknown'}",
                    "model": last_attempt.model,
                    "action_type": last_attempt.action_type,
                    "observation": last_attempt.observation,
                },
                "last_success": None
                if last_success is None
                else {
                    "iteration": last_success.iteration,
                    "step_id": last_success.step_id,
                    "account": last_success.account or "none",
                    "variant": last_success.variant or "provider-default",
                    "status": "ok" if last_success.success else f"failed:{last_success.error_type or 'unknown'}",
                    "model": last_success.model,
                    "action_type": last_success.action_type,
                    "observation": last_success.observation,
                },
                "limit_snapshot": snapshot,
                "blocked_accounts": blocked_accounts,
                "auth": capability.auth_type,
                "profiles": capability.supports_account_profiles,
                "backend": MODEL_BACKENDS[provider]["label"],
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
    lines = ["Provider limit status:"]
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
        if item["blocked_accounts"]:
            for account in item["blocked_accounts"]:
                account_reason = f" reason={account['last_limit_reason']}" if account["last_limit_reason"] else ""
                lines.append(f"  account {account['name']}: blocked_until={account['blocked_until']}{account_reason}")
    return "\n".join(lines)


def _provider_limit_summary(agent: Agent, config: AgentConfig) -> str:
    report = _provider_limit_status_report(agent, config)
    summary = _provider_limit_summary_report(report)
    if not summary["providers_count"]:
        return "none"
    parts = [
        f"providers={summary['providers_count']}",
        f"blocked_models={len(summary['blocked_models'])}",
        f"stale_models={len(summary['stale_models'])}",
        f"blocked_accounts={len(summary['blocked_accounts'])}",
    ]
    return " ".join(parts)
