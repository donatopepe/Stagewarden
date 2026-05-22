from __future__ import annotations

import os
from typing import TextIO

from .agent import Agent
from .config import AgentConfig
from .project_handoff import ProjectHandoff
from .model_catalog import catalog_entry_for_provider_model, catalog_path, load_ai_models_catalog, write_ai_models_catalog
from .modelprefs import ModelPreferences, SUPPORTED_MODELS, provider_model_spec, provider_model_specs
from .provider_registry import provider_capability, provider_model_preset
from . import model_catalog_views as _model_catalog_views
from . import model_inspection_views as _model_inspection_views
from . import shell_views as _shell_views
from . import status_views as _status_views
from .project.role_flow import _guided_provider_context


def _catalog_option_suffix(entry: dict[str, object] | None) -> str:
    if not isinstance(entry, dict) or not entry:
        return ""
    parts: list[str] = []
    if entry.get("intelligence_rank") is not None:
        parts.append(f"I#{entry.get('intelligence_rank')}")
    if entry.get("speed_rank") is not None:
        parts.append(f"S#{entry.get('speed_rank')}")
    price = entry.get("blended_price_usd_per_1m_tokens")
    if isinstance(price, (int, float)):
        parts.append(f"${price}/1M")
    return f" [{' | '.join(parts)}]" if parts else ""


def _catalog_entry_display(entry: dict[str, object] | None, spec: object | None = None) -> dict[str, object]:
    if isinstance(entry, dict) and entry:
        return {
            "model_name": entry.get("model_name"),
            "context_window": entry.get("context_window"),
            "cost_per_input_token_usd": entry.get("cost_per_input_token_usd"),
            "cost_per_output_token_usd": entry.get("cost_per_output_token_usd"),
            "blended_price_usd_per_1m_tokens": entry.get("blended_price_usd_per_1m_tokens"),
            "pricing_source": entry.get("pricing_source"),
            "intelligence_rank": entry.get("intelligence_rank"),
            "speed_rank": entry.get("speed_rank"),
            "latency_rank": entry.get("latency_rank"),
            "openness": entry.get("openness"),
            "features": list(entry.get("features", [])) if isinstance(entry.get("features"), list) else [],
            "catalog_source": entry.get("source"),
        }
    return {
        "model_name": getattr(spec, "label", None) if spec is not None else None,
        "context_window": getattr(spec, "context_window_hint", None) if spec is not None else None,
        "cost_per_input_token_usd": None,
        "cost_per_output_token_usd": None,
        "blended_price_usd_per_1m_tokens": None,
        "pricing_source": None,
        "intelligence_rank": None,
        "speed_rank": None,
        "latency_rank": None,
        "openness": None,
        "features": [],
        "catalog_source": None,
    }


def _local_model_profile_from_spec(spec) -> dict[str, object]:
    return _model_inspection_views._local_model_profile_from_spec(spec)


def _provider_model_display(prefs: ModelPreferences, provider: str) -> tuple[str, str, str]:
    capability = provider_capability(provider)
    pinned = prefs.variant_for_model(provider)
    if pinned:
        return pinned, "pinned", capability.default_model
    if provider in {"chatgpt", "openai", "claude"}:
        return "automatic-by-task", "automatic", capability.default_model
    return capability.default_model, "provider-default", capability.default_model


def _provider_model_params_display(prefs: ModelPreferences, provider: str) -> dict[str, str]:
    return prefs.params_for_model(provider)


def _catalog_model_choice_key(provider: str, provider_model: str) -> str:
    return f"{provider}:{provider_model}"


def _parse_catalog_model_choice(choice: str) -> tuple[str, str] | None:
    provider, separator, provider_model = str(choice).partition(":")
    if not separator:
        return None
    provider = provider.strip()
    provider_model = provider_model.strip()
    if not provider or not provider_model:
        return None
    return provider, provider_model


def _inspect_provider_models(
    agent: Agent,
    config: AgentConfig,
    *,
    provider: str,
    provider_model: str | None = None,
) -> dict[str, object]:
    return _model_inspection_views._inspect_provider_models(agent, config, provider=provider, provider_model=provider_model)


def _render_provider_model_inspection(report: dict[str, object]) -> str:
    return _model_inspection_views._render_provider_model_inspection(report)


def _local_execution_candidates_report(
    config: AgentConfig,
    *,
    agent: Agent | None = None,
    use_ai: bool = False,
) -> dict[str, object]:
    specs = [spec for spec in provider_model_specs("local") if spec.id != "provider-default"]
    if not specs:
        return {
            "status": "missing",
            "message": "No local models discovered from Ollama.",
            "models": [],
            "candidates": [],
            "ai_analysis": {"attempted": False, "ok": False, "model": None, "account": None, "message": "Local discovery unavailable."},
        }
    if use_ai and agent is not None:
        report = _model_inspection_views._inspect_provider_models(agent, config, provider="local")
    else:
        report = {
            "status": "ok",
            "provider": "local",
            "models": [_model_inspection_views._local_model_profile_from_spec(spec) for spec in specs],
            "ai_analysis": {"attempted": False, "ok": False, "model": None, "account": None, "message": "Metadata-only local profile."},
            "global_recommendation": "Use local models only when runtime-discovered and appropriate for bounded node execution.",
        }
    models = [item for item in report.get("models", []) if isinstance(item, dict)]
    fit_rank = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
    risk_rank = {"low": 0, "medium": 1, "unknown": 2, "high": 3}
    candidates = sorted(
        models,
        key=lambda item: (
            fit_rank.get(str(item.get("agentic_fit", "unknown")), 3),
            risk_rank.get(str(item.get("tool_support_risk", "unknown")), 2),
            str(item.get("id", "")),
        ),
    )
    return {
        "status": "ok",
        "message": report.get("global_recommendation", ""),
        "models": models,
        "candidates": candidates[:3],
        "ai_analysis": report.get("ai_analysis", {}),
        "catalog_source": report.get("catalog_source", "dynamic local inspection"),
    }


def _choose_cloud_priority_model(agent: Agent, prefs: ModelPreferences) -> str:
    # Allow tests to force OpenRouter auto-selection
    if os.environ.get("TEST_USE_OPENROUTER_AUTO", "").lower() in {"1", "true", "yes"}:
        # Use the cheap OpenRouter path with automatic model resolution
        return "cheap"
    active = set(agent.router.status().get("active_models", []))
    for candidate in ("chatgpt", "openai", "claude", "cheap", "local"):
        if candidate in active:
            return candidate
    return agent.router.choose_model("fallback cloud priority", "analysis", 0)


def _load_model_preferences(config: AgentConfig) -> ModelPreferences:
    return ModelPreferences.load(config.model_prefs_path)


def _save_model_preferences(config: AgentConfig, prefs: ModelPreferences) -> None:
    prefs.normalize().save(config.model_prefs_path)


def _sync_handoff_preferences(agent: Agent, prefs: ModelPreferences) -> None:
    agent.handoff.account_env_by_target = dict(prefs.env_var_by_account or {})
    agent.handoff.model_variant_by_model = dict(prefs.variant_by_model or {})
    agent.handoff.model_params_by_model = {
        model: dict(params) for model, params in (prefs.params_by_model or {}).items()
    }
    agent.project_handoff.sync_prince2_roles(dict(prefs.prince2_roles or {}))


def _apply_model_preferences(agent: Agent, config: AgentConfig) -> ModelPreferences:
    prefs = _load_model_preferences(config)
    agent.router.configure(
        enabled_models=prefs.enabled_models,
        preferred_model=prefs.preferred_model,
        blocked_until_by_model=prefs.blocked_until_by_model or {},
    )
    _sync_handoff_preferences(agent, prefs)
    return prefs


def _sync_prince2_roles_to_handoff(config: AgentConfig, prefs: ModelPreferences) -> None:
    handoff = ProjectHandoff.load(config.handoff_path)
    handoff.sync_prince2_roles(dict(prefs.prince2_roles or {}))
    if prefs.prince2_role_tree_baseline:
        handoff.sync_prince2_role_tree_baseline(dict(prefs.prince2_role_tree_baseline))
    handoff.save(config.handoff_path)


def _sync_prince2_role_tree_baseline_back_to_preferences(
    config: AgentConfig,
    prefs: ModelPreferences,
    handoff: ProjectHandoff,
) -> None:
    baseline = handoff.prince2_role_tree_baseline if isinstance(handoff.prince2_role_tree_baseline, dict) else {}
    if not baseline:
        return
    prefs.set_prince2_role_tree_baseline(dict(baseline))
    prefs.save(config.model_prefs_path)


def _guided_model_choice(
    *,
    requested_model: str | None,
    prefs: ModelPreferences,
    agent: Agent,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
    ) -> str:
    if input_stream is None or output_stream is None:
        return "Guided model selection is available in the interactive shell. Run `python3 -m stagewarden.main` and use `model choose`."
    providers = list(prefs.enabled_models or []) or list(SUPPORTED_MODELS)
    output_stream.write(_guided_provider_context(prefs, requested_model if requested_model in SUPPORTED_MODELS else None) + "\n")
    model = requested_model
    if model is None:
        model = _shell_views._prompt_menu_choice(
            title="Choose provider:",
            options=[(item, item) for item in providers],
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if model is None:
            return "Guided model selection cancelled."
    if model not in SUPPORTED_MODELS:
        return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
    if model not in prefs.enabled_models:
        prefs.enabled_models.append(model)
    output_stream.write(_guided_provider_context(prefs, model) + "\n")
    catalog = load_ai_models_catalog()
    specs = list(provider_model_specs(model))
    provider_model = _shell_views._prompt_menu_choice(
        title=f"Choose provider-model for {model}:",
        options=[
            (spec.id, f"{spec.id} | {spec.label}{_catalog_option_suffix(catalog_entry_for_provider_model(model, spec.id, catalog))}")
            for spec in specs
        ],
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if provider_model is None:
        return "Guided model selection cancelled."
    spec = provider_model_spec(model, provider_model)
    reasoning_value = None
    if spec is not None and spec.reasoning_efforts:
        current_reasoning = prefs.params_for_model(model).get("reasoning_effort") or spec.reasoning_default or spec.reasoning_efforts[0]
        if provider_model == "gpt-5.3-codex":
            reasoning_options = [
                ("medium", "medium"),
                ("high", f"high{' (default)' if current_reasoning == 'high' else ''}"),
                ("high", "high"),
            ]
        else:
            ordered_reasoning_efforts = list(spec.reasoning_efforts)
            if provider_model and "mini" not in provider_model.lower():
                ordered_reasoning_efforts = list(reversed(ordered_reasoning_efforts))
            reasoning_options = [
                (effort, f"{effort}{' (default)' if effort == current_reasoning else ''}")
                for effort in ordered_reasoning_efforts
            ]
        reasoning_value = _shell_views._prompt_menu_choice(
            title=f"Choose reasoning_effort for {model}:{provider_model}:",
            options=reasoning_options,
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if reasoning_value is None:
            return "Guided model selection cancelled."
    prefs.preferred_model = model
    prefs.set_variant(model, provider_model)
    if reasoning_value is not None:
        prefs.set_model_param(model, "reasoning_effort", reasoning_value)
    _save_model_preferences(config, prefs)
    _apply_model_preferences(agent, config)
    params_text = f" reasoning_effort={reasoning_value}" if reasoning_value is not None else ""
    return f"Guided selection applied: provider={model} provider_model={provider_model}{params_text}."


def _render_model_params(config: AgentConfig, model: str) -> str:
    prefs = _load_model_preferences(config)
    provider_model = prefs.variant_for_model(model) or "provider-default"
    spec = provider_model_spec(model, provider_model)
    params = prefs.params_for_model(model)
    reasoning_options = [] if spec is None else list(spec.reasoning_efforts)
    current_reasoning = params.get("reasoning_effort") or (None if spec is None else spec.reasoning_default)
    return "\n".join(
        [
            f"Provider params for {model}:",
            f"- provider_model: {provider_model}",
            f"- reasoning_effort_supported: {', '.join(reasoning_options) or 'none'}",
            f"- reasoning_effort_current: {current_reasoning or 'none'}",
        ]
    )


def _apply_model_preset(
    config: AgentConfig,
    prefs: ModelPreferences,
    *,
    model: str,
    preset: str,
) -> tuple[str, dict[str, str]]:
    provider_model, params = provider_model_preset(model, preset)
    if model == "chatgpt" and preset.strip().lower() == "deep":
        provider_model = "gpt-5.3-codex"
    prefs.set_variant(model, provider_model)
    for key, value in params.items():
        prefs.set_model_param(model, key, value)
    return provider_model, params


def _catalog_usage() -> str:
    return _model_catalog_views._catalog_usage()


def _parse_catalog_refresh_flags(parts: list[str]) -> bool:
    return _model_catalog_views._parse_catalog_refresh_flags(parts)


def _catalog_status_report() -> dict[str, object]:
    return _model_catalog_views._catalog_status_report_from_catalog(load_ai_models_catalog())


def _catalog_search_report(query: str, provider: str | None = None, *, feature: str | None = None, limit: int = 10) -> dict[str, object]:
    return _model_catalog_views._catalog_search_report_from_catalog(query, load_ai_models_catalog(), provider=provider, feature=feature, limit=limit)


def _catalog_refresh_report(catalog: dict[str, object]) -> dict[str, object]:
    return _model_catalog_views._catalog_refresh_report_from_catalog(catalog)


def _model_usage() -> str:
    return _model_catalog_views._model_usage()


def _handle_model_command(
    command: str,
    agent: Agent,
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> str | None:
    parts = command.split()
    if not parts:
        return None
    if parts[0] == "catalog":
        if len(parts) == 1:
            return _catalog_usage()
        if parts[1] == "status":
            if len(parts) != 2:
                return _catalog_usage()
            report = _catalog_status_report()
            return (
                f"Catalog snapshot: path={report['path']} model_count={report['model_count']} "
                f"generated_at={report['generated_at'] or 'missing'}"
            )
        if parts[1] == "refresh":
            try:
                include_artificial_analysis = _parse_catalog_refresh_flags(parts[2:])
            except ValueError:
                return _catalog_usage()
            catalog = write_ai_models_catalog(include_artificial_analysis=include_artificial_analysis)
            catalog["include_artificial_analysis"] = include_artificial_analysis
            return (
                f"Catalog refreshed: path={catalog_path()} "
                f"pricing_source={'artificial_analysis' if include_artificial_analysis else 'openrouter'} "
                f"model_count={len(catalog.get('models', [])) if isinstance(catalog.get('models', []), list) else 0} "
                f"generated_at={catalog.get('generated_at', 'unknown')}"
            )
        if parts[1] == "search":
            if len(parts) < 3:
                return _catalog_usage()
            query_parts: list[str] = []
            provider = None
            feature = None
            for token in parts[2:]:
                if token.startswith("provider=") and len(token) > len("provider="):
                    provider = token.split("=", 1)[1]
                    continue
                if token.startswith("feature=") and len(token) > len("feature="):
                    feature = token.split("=", 1)[1]
                    continue
                query_parts.append(token)
            query = " ".join(query_parts).strip()
            if not query and not provider and not feature:
                return _catalog_usage()
            report = _catalog_search_report(query, provider, feature=feature)
            filter_bits = [bit for bit in (f"provider={provider}" if provider else None, f"feature={feature}" if feature else None) if bit]
            search_label = f"'{query}'" if query else "all models"
            if filter_bits:
                search_label = f"{search_label} {' '.join(filter_bits)}"
            if not report["results"]:
                return f"No catalog matches for {search_label}."
            lines = [
                f"Catalog search for {search_label}:",
                f"Path: {report['path']}",
                f"Matches: {len(report['results'])}",
            ]
            for entry in report["results"]:
                aliases = ", ".join(entry.get("aliases", [])) if isinstance(entry.get("aliases"), list) else ""
                features = ", ".join(entry.get("features", [])) if isinstance(entry.get("features"), list) else ""
                lines.append(
                    f"- {entry.get('provider')}:{entry.get('model_id')} name={entry.get('model_name')} "
                    f"openness={entry.get('openness')} aliases={aliases or 'none'} features={features or 'none'}"
                )
            return "\n".join(lines)
        return _catalog_usage()
    if parts[0] == "cost":
        if len(parts) == 2 and parts[1] == "sidebar":
            return _status_views._render_cost_sidebar(agent, config)
        return _status_views._render_model_usage(config)
    if parts[0] == "models":
        if len(parts) == 2 and parts[1] == "usage":
            return _status_views._render_model_usage(config)
        if len(parts) == 2 and parts[1] == "limits":
            _apply_model_preferences(agent, config)
            return _status_views._render_model_limits(agent, config)
        if len(parts) != 1:
            return "Usage: models | models usage | models limits"
        _apply_model_preferences(agent, config)
        return _status_views._render_model_status(agent, config)
    if parts[0] != "model":
        return None
    if len(parts) < 2:
        return _model_usage()
    prefs = _load_model_preferences(config)
    if command.startswith("model limit-record "):
        fields = command[len("model limit-record ") :].split(maxsplit=1)
        if len(fields) != 2:
            return "Usage: model limit-record <model> <provider message>"
        model, message = fields
        result = _status_views._record_limit_message(config, prefs, model=model, message=message)
        _apply_model_preferences(agent, config)
        return result
    if command.startswith("model limit-clear "):
        fields = command[len("model limit-clear ") :].split(maxsplit=1)
        if len(fields) != 1:
            return "Usage: model limit-clear <model>"
        result = _status_views._clear_limit_snapshot(config, prefs, model=fields[0])
        _apply_model_preferences(agent, config)
        return result

    action = parts[1]
    try:
        if action == "choose":
            if len(parts) > 3:
                return "Usage: model choose [provider]"
            requested_model = parts[2] if len(parts) == 3 else None
            return _guided_model_choice(
                requested_model=requested_model,
                prefs=prefs,
                agent=agent,
                config=config,
                input_stream=input_stream,
                output_stream=output_stream,
            )
        if action == "use":
            if len(parts) != 3:
                return "Usage: model use <name>"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            if model not in prefs.enabled_models:
                prefs.enabled_models.append(model)
            prefs.preferred_model = model
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            provider_model = prefs.variant_for_model(model) or "automatic-by-task"
            return f"Preferred provider set to {model}. Current provider_model={provider_model}."
        if action == "list":
            if len(parts) != 3:
                return "Usage: model list <name>"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            capability = provider_capability(model)
            specs = provider_model_specs(model)
            catalog = load_ai_models_catalog()
            lines = [f"Provider-model catalog for {model}:"]
            lines.extend(
                [
                    f"Auth: {capability.auth_type}",
                    f"API key: {'yes' if capability.supports_api_key else 'no'}",
                    f"Browser login: {'yes' if capability.supports_browser_login else 'no'}",
                ]
            )
            if capability.token_env:
                lines.append(f"Token env: {capability.token_env}")
            if capability.login_hint:
                lines.append(f"Login hint: {capability.login_hint}")
            for spec in specs:
                entry = catalog_entry_for_provider_model(model, spec.id, catalog)
                display = _catalog_entry_display(entry, spec)
                reasoning_effort = f"[{','.join(spec.reasoning_efforts)}]" if spec.reasoning_efforts else "[none]"
                catalog_source = display.get("catalog_source") or spec.source or "unknown"
                lines.append(
                    f"- {spec.id}: {display.get('model_name') or spec.label} reasoning_effort={reasoning_effort} catalog={catalog_source}"
                )
            return "\n".join(lines)
        if action == "inspect":
            if len(parts) not in {3, 4}:
                return "Usage: model inspect <provider> [provider_model]"
            provider = parts[2]
            provider_model = parts[3] if len(parts) == 4 else None
            report = _inspect_provider_models(agent, config, provider=provider, provider_model=provider_model)
            return _render_provider_model_inspection(report)
        if action == "params":
            if len(parts) != 3:
                return "Usage: model params <name>"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            return _render_model_params(config, model)
        if action == "variant":
            if len(parts) != 4:
                return "Usage: model variant <name> <variant>"
            model = parts[2]
            variant = parts[3]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            prefs.set_variant(model, variant)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Variant for {model} set to {variant}."
        if action == "variant-clear":
            if len(parts) != 3:
                return "Usage: model variant-clear <name>"
            model = parts[2]
            prefs.clear_variant(model)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Variant cleared for {model}."
        if action == "preset":
            if len(parts) == 3:
                return _guided_model_choice(
                    requested_model=parts[2],
                    prefs=prefs,
                    agent=agent,
                    config=config,
                    input_stream=input_stream,
                    output_stream=output_stream,
                )
            if len(parts) != 4:
                return "Usage: model preset <name> <fast|balanced|deep|plan>"
            model = parts[2]
            preset = parts[3]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            provider_model, params = _apply_model_preset(config, prefs, model=model, preset=preset)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            params_text = ", ".join(f"{key}={value}" for key, value in sorted(params.items())) or "none"
            return f"Applied preset {preset} to {model}: provider_model={provider_model} params={params_text}."
        if action == "param":
            if len(parts) < 4:
                return "Usage: model param set <name> <key> <value> | model param clear <name> <key>"
            sub_action = parts[2]
            model = parts[3]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            if sub_action == "set":
                if len(parts) < 6:
                    return "Usage: model param set <name> <key> <value>"
                key = parts[4]
                value = " ".join(parts[5:])
                prefs.set_model_param(model, key, value)
                _save_model_preferences(config, prefs)
                _apply_model_preferences(agent, config)
                return f"Set {key}={value} for {model}."
            if sub_action == "clear":
                if len(parts) != 5:
                    return "Usage: model param clear <name> <key>"
                key = parts[4]
                prefs.clear_model_param(model, key)
                _save_model_preferences(config, prefs)
                _apply_model_preferences(agent, config)
                return f"Cleared {key} for {model}."
        if action == "remove":
            if len(parts) != 3:
                return "Usage: model remove <name>"
            model = parts[2]
            prefs.remove_model(model)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Removed {model}."
        if action == "block":
            if len(parts) != 5 or parts[3] != "until":
                return "Usage: model block <name> until YYYY-MM-DDTHH:MM"
            model = parts[2]
            until = parts[4]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            from datetime import datetime
            try:
                datetime.fromisoformat(until)
            except ValueError:
                return "Invalid date/time. Use YYYY-MM-DDTHH:MM."
            prefs.blocked_until_by_model = dict(prefs.blocked_until_by_model or {})
            prefs.blocked_until_by_model[model] = until
            if prefs.preferred_model == model:
                prefs.preferred_model = None
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Blocked model {model} until {until}."
        if action == "unblock":
            if len(parts) != 3:
                return "Usage: model unblock <name>"
            model = parts[2]
            if model not in SUPPORTED_MODELS:
                return f"Unsupported model '{model}'. Supported: {', '.join(SUPPORTED_MODELS)}"
            prefs.blocked_until_by_model = dict(prefs.blocked_until_by_model or {})
            if model not in prefs.blocked_until_by_model:
                return f"Model {model} is not blocked."
            prefs.blocked_until_by_model.pop(model, None)
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return f"Unblocked model {model}."
        if action == "clear":
            prefs.preferred_model = None
            _save_model_preferences(config, prefs)
            _apply_model_preferences(agent, config)
            return "Preferred provider cleared. Automatic routing restored."
    except ValueError as exc:
        return str(exc)

    return _model_usage()
