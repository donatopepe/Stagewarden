from __future__ import annotations

from typing import Any, TextIO

from .agent import Agent
from .config import AgentConfig
from .handoff import format_run_model
from .json_schema_registry import json_schema
from .model_catalog import catalog_entry_for_provider_model, catalog_path, load_ai_models_catalog, search_ai_models_catalog, write_ai_models_catalog
from .modelprefs import ModelPreferences, SUPPORTED_MODELS, provider_model_spec, provider_model_specs
from .provider_registry import provider_capability, provider_model_preset


def _main():
    from . import main as _main_module

    return _main_module


def _catalog_option_suffix(entry: dict[str, object] | None) -> str:
    return _main()._catalog_option_suffix(entry)


def _catalog_entry_display(entry: dict[str, object] | None, spec: object | None = None) -> dict[str, object]:
    return _main()._catalog_entry_display(entry, spec)


def _catalog_power_score(entry: dict[str, object] | None) -> float | None:
    return _main()._catalog_power_score(entry)


def _catalog_model_choice_key(provider: str, provider_model: str) -> str:
    return _main()._catalog_model_choice_key(provider, provider_model)


def _parse_catalog_model_choice(choice: str) -> tuple[str, str] | None:
    return _main()._parse_catalog_model_choice(choice)


def _inspect_provider_models(
    agent: Agent,
    config: AgentConfig,
    *,
    provider: str,
    provider_model: str | None = None,
) -> dict[str, object]:
    return _main()._inspect_provider_models(agent, config, provider=provider, provider_model=provider_model)


def _render_provider_model_inspection(report: dict[str, object]) -> str:
    return _main()._render_provider_model_inspection(report)


def _local_execution_candidates_report(
    config: AgentConfig,
    *,
    agent: Agent | None = None,
    use_ai: bool = False,
) -> dict[str, object]:
    return _main()._local_execution_candidates_report(config, agent=agent, use_ai=use_ai)


def _guided_model_choice(
    *,
    requested_model: str | None,
    prefs: ModelPreferences,
    agent: Agent,
    config: AgentConfig,
    input_stream: TextIO | None,
    output_stream: TextIO | None,
    ) -> str:
    return _main()._guided_model_choice(
        requested_model=requested_model,
        prefs=prefs,
        agent=agent,
        config=config,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _render_model_params(config: AgentConfig, model: str) -> str:
    prefs = _main()._load_model_preferences(config)
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
    return "Usage: catalog status | catalog refresh [--aa] | catalog search <query> [provider=<provider>] [feature=<feature>]"


def _parse_catalog_refresh_flags(parts: list[str]) -> bool:
    include_artificial_analysis = False
    for token in parts:
        if token == "--aa":
            include_artificial_analysis = True
            continue
        raise ValueError(_catalog_usage())
    return include_artificial_analysis


def _catalog_status_report() -> dict[str, object]:
    catalog = load_ai_models_catalog()
    models = catalog.get("models", []) if isinstance(catalog, dict) else []
    model_count = len(models) if isinstance(models, list) else 0
    return {
        "command": "catalog status",
        "schema": json_schema("catalog status"),
        "ok": bool(catalog),
        "path": str(catalog_path()),
        "generated_at": catalog.get("generated_at") if isinstance(catalog, dict) else None,
        "model_count": model_count,
        "source_urls": catalog.get("source_urls", {}) if isinstance(catalog, dict) else {},
    }


def _catalog_search_report(query: str, provider: str | None = None, *, feature: str | None = None, limit: int = 10) -> dict[str, object]:
    catalog = load_ai_models_catalog()
    results = search_ai_models_catalog(query, provider=provider, feature=feature, catalog=catalog, limit=limit)
    return {
        "command": "catalog search",
        "schema": json_schema("catalog search"),
        "query": query,
        "provider": provider,
        "feature": feature,
        "path": str(catalog_path()),
        "model_count": len(catalog.get("models", [])) if isinstance(catalog, dict) and isinstance(catalog.get("models", []), list) else 0,
        "results": results,
    }


def _catalog_refresh_report(catalog: dict[str, object]) -> dict[str, object]:
    return {
        "command": "catalog refresh",
        "schema": json_schema("catalog refresh"),
        "ok": True,
        "include_artificial_analysis": bool(catalog.get("include_artificial_analysis", False)),
        "pricing_source": "artificial_analysis" if bool(catalog.get("include_artificial_analysis", False)) else "openrouter",
        "path": str(catalog_path()),
        "generated_at": catalog.get("generated_at"),
        "model_count": len(catalog.get("models", [])) if isinstance(catalog.get("models", []), list) else 0,
        "source_urls": catalog.get("source_urls", {}),
    }


def _model_usage() -> str:
    return (
        "Usage: model use <name> | model choose [name] | model add <name> | model list <name> | model inspect <provider> [provider_model] | "
        "model params <name> | model variant <name> <variant> | model variant-clear <name> | "
        "model preset <name> <fast|balanced|deep|plan> | "
        "model param set <name> <key> <value> | model param clear <name> <key> | "
        "model remove <name> | model block <name> until YYYY-MM-DDTHH:MM | "
        "model unblock <name> | model limits | model limit-record <name> <message> | "
        "model limit-clear <name> | model clear | catalog status | catalog refresh [--aa] | catalog search <query> [provider=<provider>] [feature=<feature>]"
    )


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
            return _main()._render_cost_sidebar(agent, config)
        return _main()._render_model_usage(config)
    if parts[0] == "models":
        if len(parts) == 2 and parts[1] == "usage":
            return _main()._render_model_usage(config)
        if len(parts) == 2 and parts[1] == "limits":
            _main()._apply_model_preferences(agent, config)
            return _main()._render_model_limits(agent, config)
        if len(parts) != 1:
            return "Usage: models | models usage | models limits"
        _main()._apply_model_preferences(agent, config)
        return _main()._render_model_status(agent, config)
    if parts[0] != "model":
        return None
    if len(parts) < 2:
        return _model_usage()
    prefs = _main()._load_model_preferences(config)
    if command.startswith("model limit-record "):
        fields = command[len("model limit-record ") :].split(maxsplit=1)
        if len(fields) != 2:
            return "Usage: model limit-record <model> <provider message>"
        model, message = fields
        result = _main()._record_limit_message(config, prefs, model=model, message=message)
        _main()._apply_model_preferences(agent, config)
        return result
    if command.startswith("model limit-clear "):
        fields = command[len("model limit-clear ") :].split(maxsplit=1)
        if len(fields) != 1:
            return "Usage: model limit-clear <model>"
        result = _main()._clear_limit_snapshot(config, prefs, model=fields[0])
        _main()._apply_model_preferences(agent, config)
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
            _main()._save_model_preferences(config, prefs)
            _main()._apply_model_preferences(agent, config)
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
            lines = [f"Models for {model}:"]
            lines.append(f"- provider: {capability.provider}")
            lines.append(f"- source: {capability.source}")
            lines.append(f"- feature: {capability.feature or 'unknown'}")
            lines.append(f"- reason: {capability.reason or 'unknown'}")
            for spec in specs:
                entry = catalog_entry_for_provider_model(model, spec.id, catalog)
                display = _catalog_entry_display(entry, spec)
                lines.append(f"- {spec.id}: {display.get('label', spec.label)}")
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
            _main()._save_model_preferences(config, prefs)
            _main()._apply_model_preferences(agent, config)
            return f"Variant for {model} set to {variant}."
        if action == "variant-clear":
            if len(parts) != 3:
                return "Usage: model variant-clear <name>"
            model = parts[2]
            prefs.clear_variant(model)
            _main()._save_model_preferences(config, prefs)
            _main()._apply_model_preferences(agent, config)
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
            _main()._save_model_preferences(config, prefs)
            _main()._apply_model_preferences(agent, config)
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
                _main()._save_model_preferences(config, prefs)
                _main()._apply_model_preferences(agent, config)
                return f"Set {key}={value} for {model}."
            if sub_action == "clear":
                if len(parts) != 5:
                    return "Usage: model param clear <name> <key>"
                key = parts[4]
                prefs.clear_model_param(model, key)
                _main()._save_model_preferences(config, prefs)
                _main()._apply_model_preferences(agent, config)
                return f"Cleared {key} for {model}."
        if action == "remove":
            if len(parts) != 3:
                return "Usage: model remove <name>"
            model = parts[2]
            prefs.remove_model(model)
            _main()._save_model_preferences(config, prefs)
            _main()._apply_model_preferences(agent, config)
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
            _main()._save_model_preferences(config, prefs)
            _main()._apply_model_preferences(agent, config)
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
            _main()._save_model_preferences(config, prefs)
            _main()._apply_model_preferences(agent, config)
            return f"Unblocked model {model}."
        if action == "clear":
            prefs.preferred_model = None
            _main()._save_model_preferences(config, prefs)
            _main()._apply_model_preferences(agent, config)
            return "Preferred provider cleared. Automatic routing restored."
    except ValueError as exc:
        return str(exc)

    return _model_usage()
