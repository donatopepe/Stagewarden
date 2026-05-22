from __future__ import annotations

import json
import os
import re
import tomllib
from functools import lru_cache
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .kilocode_source import (
    kilocode_provider_ids,
    kilocode_provider_info,
    kilocode_provider_model_ids,
    kilocode_provider_models,
)


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    name: str
    provider_label: str
    backend_label: str
    auth_type: str
    model_aliases: tuple[str, ...]
    default_model: str
    context_assumption: str
    supports_account_profiles: bool
    supports_browser_login: bool
    supports_api_key: bool
    token_env: str
    model_env: str
    login_url: str
    login_hint: str
    source: str


@dataclass(frozen=True, slots=True)
class ProviderModelSpec:
    id: str
    label: str
    reasoning_efforts: tuple[str, ...]
    reasoning_default: str | None = None
    context_window_hint: str = ""
    availability: str = "general"
    source: str = ""


PROVIDER_CAPABILITIES: dict[str, ProviderCapability] = {
    "local": ProviderCapability(
        name="local",
        provider_label="ollama",
        backend_label="local/ollama",
        auth_type="none",
        model_aliases=(),
        default_model="provider-default",
        context_assumption="Local Ollama context depends on the selected local model discovered at runtime from the local Ollama registry.",
        supports_account_profiles=False,
        supports_browser_login=False,
        supports_api_key=False,
        token_env="",
        model_env="OLLAMA_MODEL",
        login_url="",
        login_hint="No login required. Configure Ollama and optionally OLLAMA_MODEL. Stagewarden discovers local models dynamically from Ollama.",
        source="workspace/provider setting + dynamic Ollama discovery",
    ),
    "cheap": ProviderCapability(
        name="cheap",
        provider_label="openrouter",
        backend_label="cheap/openrouter",
        auth_type="api_key",
        model_aliases=(),
        default_model="provider-default",
        context_assumption="OpenRouter context depends on the routed provider model.",
        supports_account_profiles=True,
        supports_browser_login=False,
        supports_api_key=True,
        token_env="OPENROUTER_API_KEY",
        model_env="OPENROUTER_MODEL",
        login_url="https://openrouter.ai/settings/keys",
        login_hint="Use an OpenRouter API key through OPENROUTER_API_KEY or account add cheap <name> ENV_VAR.",
        source="OpenRouter provider setting",
    ),
    "chatgpt": ProviderCapability(
        name="chatgpt",
        provider_label="ChatGPT",
        backend_label="chatgpt/chatgpt-plan",
        auth_type="chatgpt_plan_oauth",
        model_aliases=(),
        default_model="provider-default",
        context_assumption="ChatGPT plan semantics: use stored OAuth/session credentials, not OpenAI API keys.",
        supports_account_profiles=True,
        supports_browser_login=True,
        supports_api_key=False,
        token_env="CHATGPT_TOKEN",
        model_env="OPENAI_MODEL",
        login_url="https://chatgpt.com/",
        login_hint="Use account login chatgpt <profile>; Stagewarden delegates to Codex browser login and never scrapes browser tokens.",
        source="OpenAI Codex/OpenAI models docs",
    ),
    "openai": ProviderCapability(
        name="openai",
        provider_label="GPT-5.4",
        backend_label="openai/GPT-5.4",
        auth_type="openai_api_key",
        model_aliases=(),
        default_model="provider-default",
        context_assumption="OpenAI API semantics: API-key account profiles are distinct from ChatGPT plan login.",
        supports_account_profiles=True,
        supports_browser_login=True,
        supports_api_key=True,
        token_env="OPENAI_API_KEY",
        model_env="OPENAI_MODEL",
        login_url="https://platform.openai.com/api-keys",
        login_hint="Prefer OPENAI_API_KEY or account add openai <profile> ENV_VAR; device-code login is optional when configured.",
        source="OpenAI models docs",
    ),
    "claude": ProviderCapability(
        name="claude",
        provider_label="Claude Sonnet",
        backend_label="claude/sonnet",
        auth_type="anthropic_api_key_or_claude_code_credentials",
        model_aliases=(),
        default_model="provider-default",
        context_assumption="Claude Code style aliases are mapped by the provider backend.",
        supports_account_profiles=True,
        supports_browser_login=False,
        supports_api_key=True,
        token_env="ANTHROPIC_API_KEY",
        model_env="ANTHROPIC_MODEL",
        login_url="https://console.anthropic.com/settings/keys",
        login_hint="Use ANTHROPIC_API_KEY or import Claude Code credentials with account import claude <profile>.",
        source="Claude Code model configuration docs",
    ),
}


def _ollama_base_url() -> str:
    return os.environ.get("STAGEWARDEN_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def _lm_studio_base_url() -> str:
    return os.environ.get("STAGEWARDEN_LM_STUDIO_BASE_URL", "http://127.0.0.1:1234").rstrip("/")


def _parse_parameter_size_billions(parameter_size: str) -> float | None:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*B", str(parameter_size), re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _dynamic_local_reasoning_efforts(name: str, parameter_size: str) -> tuple[tuple[str, ...], str | None]:
    lowered = name.lower()
    size_b = _parse_parameter_size_billions(parameter_size)
    if "sqlcoder" in lowered:
        return ("medium",), "medium"
    if "deepseek" in lowered or "r1" in lowered:
        return ("medium", "high"), "high"
    if "coder" in lowered:
        if size_b is not None and size_b <= 10:
            return ("low", "medium"), "medium"
        return ("medium", "high"), "medium"
    if size_b is not None and size_b <= 8:
        return ("low", "medium"), "medium"
    return ("medium", "high"), "medium"


def _dynamic_local_availability(name: str, remote_host: str) -> str:
    lowered = name.lower()
    if remote_host:
        return "local-remote"
    if "codestral" in lowered:
        return "local-limited"
    if "sqlcoder" in lowered:
        return "local-specialized"
    if "coder" in lowered or "deepseek" in lowered:
        return "local-agentic"
    return "local-available"


def _dynamic_local_hint(name: str, details: dict[str, object], remote_host: str) -> str:
    lowered = name.lower()
    parameter_size = str(details.get("parameter_size", "") or "").strip()
    family = str(details.get("family", "") or "").strip()
    quant = str(details.get("quantization_level", "") or "").strip()
    parts: list[str] = []
    if parameter_size:
        parts.append(f"size={parameter_size}")
    if family:
        parts.append(f"family={family}")
    if quant:
        parts.append(f"quant={quant}")
    if remote_host:
        parts.append(f"remote_host={remote_host}")
    if "codestral" in lowered:
        parts.append("validate tool support before agentic use")
    elif "sqlcoder" in lowered:
        parts.append("specialized for SQL-oriented work")
    elif "deepseek" in lowered or "r1" in lowered:
        parts.append("better fit for deeper local reasoning")
    elif "coder" in lowered:
        parts.append("strong candidate for local coding/tool workflows")
    return "; ".join(parts) or "Discovered dynamically from Ollama tags."


def _load_ai_models_catalog() -> dict[str, object]:
    try:
        from .model_catalog import load_ai_models_catalog
    except Exception:
        return {}
    try:
        catalog = load_ai_models_catalog()
    except Exception:
        return {}
    return catalog if isinstance(catalog, dict) else {}


def _catalog_entries_for_provider(provider: str) -> list[dict[str, object]]:
    try:
        from .model_catalog import catalog_entries_for_provider
    except Exception:
        return []
    catalog = _load_ai_models_catalog()
    entries = catalog_entries_for_provider(provider, catalog)
    return [entry for entry in entries if isinstance(entry, dict)]


def _catalog_reasoning_efforts(model_id: str, entry: dict[str, object]) -> tuple[tuple[str, ...], str | None]:
    features = {str(item).lower() for item in entry.get("features", []) if str(item).strip()}
    context_window = entry.get("context_window")
    context_value = int(context_window) if isinstance(context_window, (int, float)) else None
    if "reasoning" in features or "include_reasoning" in features:
        if "structured_output" in features or "tool_use" in features:
            return ("medium", "high"), "high"
        return ("medium", "high"), "medium"
    if context_value is not None and context_value <= 200_000:
        return ("low", "medium"), "low" if "reasoning" not in features else "medium"
    if context_value is not None and context_value >= 1_000_000:
        return ("low", "medium", "high"), "medium"
    if "tool_use" in features or "structured_output" in features:
        return ("low", "medium", "high"), "medium"
    return ("low", "medium", "high"), "medium"


def _catalog_provider_model_specs(provider: str) -> tuple[ProviderModelSpec, ...]:
    entries = _catalog_entries_for_provider(provider)
    if not entries:
        return ()
    specs: list[ProviderModelSpec] = []
    for entry in entries:
        model_id = str(entry.get("model_id", "")).strip()
        if not model_id:
            continue
        reasoning_efforts, reasoning_default = _catalog_reasoning_efforts(model_id, entry)
        context_window = entry.get("context_window")
        context_hint = f"context={int(context_window)}" if isinstance(context_window, (int, float)) else ""
        features = entry.get("features", [])
        if isinstance(features, list) and features:
            feature_hint = ", ".join(str(item) for item in features if str(item).strip())
            context_hint = f"{context_hint}; {feature_hint}" if context_hint else feature_hint
        specs.append(
            ProviderModelSpec(
                id=model_id,
                label=str(entry.get("model_name", model_id) or model_id),
                reasoning_efforts=reasoning_efforts,
                reasoning_default=reasoning_default,
                context_window_hint=context_hint,
                availability="provider-default" if model_id == "provider-default" else "general",
                source=str(entry.get("source", f"AI models catalog: {provider}") or f"AI models catalog: {provider}"),
            )
        )
    unique: dict[str, ProviderModelSpec] = {}
    for spec in specs:
        unique[spec.id] = spec
    return tuple(unique.values())


def _dynamic_local_label(name: str) -> str:
    base = name.split(":", 1)[0].replace("-", " ").replace("_", " ").strip()
    if not base:
        return name
    return " ".join(part.upper() if part.isupper() else part.capitalize() for part in base.split())


def _codex_config_path() -> Path:
    override = os.environ.get("STAGEWARDEN_CODEX_CONFIG", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codex" / "config.toml"


def _load_codex_config() -> dict[str, object]:
    path = _codex_config_path()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _openrouter_env_key_from_codex_config() -> str | None:
    data = _load_codex_config()
    providers = data.get("model_providers") if isinstance(data, dict) else None
    if not isinstance(providers, dict):
        return None
    openrouter = providers.get("openrouter")
    if not isinstance(openrouter, dict):
        return None
    candidate = str(openrouter.get("env_key", "") or "").strip()
    if not candidate or not re.fullmatch(r"[A-Z][A-Z0-9_]*", candidate):
        return None
    return candidate


def _discover_openrouter_provider_model_specs() -> tuple[ProviderModelSpec, ...]:
    discovered: list[ProviderModelSpec] = [
        ProviderModelSpec(
            id="provider-default",
            label="Provider default",
            reasoning_efforts=("low", "medium"),
            reasoning_default="medium",
            availability="provider-default",
            source="OpenRouter provider setting",
        )
    ]
    data = _load_codex_config()
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, dict):
        return tuple(discovered)
    for profile_name, profile_value in profiles.items():
        if not isinstance(profile_value, dict):
            continue
        provider = str(profile_value.get("model_provider", "") or "").strip().lower()
        if provider != "openrouter":
            continue
        model_id = str(profile_value.get("model", "") or "").strip()
        if not model_id:
            continue
        effort = str(profile_value.get("model_reasoning_effort", "") or "").strip().lower()
        allowed_efforts = ("low", "medium", "high")
        if effort not in allowed_efforts:
            reasoning_efforts = allowed_efforts
            reasoning_default = "medium"
        else:
            reasoning_efforts = (effort,)
            reasoning_default = effort
        discovered.append(
            ProviderModelSpec(
                id=model_id,
                label=_dynamic_local_label(model_id),
                reasoning_efforts=reasoning_efforts,
                reasoning_default=reasoning_default,
                context_window_hint=f"codex_profile={profile_name}",
                availability="codex-profile",
                source=f"{_codex_config_path()}:profiles.{profile_name}",
            )
        )
    unique: dict[str, ProviderModelSpec] = {}
    for spec in discovered:
        unique[spec.id] = spec
    return tuple(unique.values())


def _discover_lm_studio_provider_model_specs() -> tuple[ProviderModelSpec, ...]:
    try:
        base_url = _lm_studio_base_url()
        request_url = f"{base_url}/v1/models"
        with urlopen(request_url, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return ()
    models = payload.get("data", [])
    if not isinstance(models, list):
        return ()
    specs: list[ProviderModelSpec] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or item.get("name") or "").strip()
        if not model_id:
            continue
        reasoning_efforts, reasoning_default = _dynamic_local_reasoning_efforts(model_id, "")
        specs.append(
            ProviderModelSpec(
                id=model_id,
                label=_dynamic_local_label(model_id),
                reasoning_efforts=reasoning_efforts,
                reasoning_default=reasoning_default,
                context_window_hint=f"lm_studio_base_url={base_url}",
                availability="local-lm-studio",
                source=f"dynamic LM Studio discovery ({request_url})",
            )
        )
    unique: dict[str, ProviderModelSpec] = {}
    for spec in specs:
        unique[spec.id] = spec
    return tuple(unique.values())


def _discover_local_provider_model_specs() -> tuple[ProviderModelSpec, ...]:
    specs: list[ProviderModelSpec] = [
        ProviderModelSpec(
            id="provider-default",
            label="Provider default",
            reasoning_efforts=(),
            reasoning_default=None,
            availability="workspace",
            source="workspace/provider setting",
        )
    ]
    try:
        inline_payload = os.environ.get("STAGEWARDEN_OLLAMA_TAGS_JSON", "").strip()
        if inline_payload:
            payload = json.loads(inline_payload)
            request_url = "env:STAGEWARDEN_OLLAMA_TAGS_JSON"
        else:
            base_url = _ollama_base_url()
            request_url = f"{base_url}/api/tags"
            with urlopen(request_url, timeout=1.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        payload = {}
        request_url = ""
    models = payload.get("models", []) if isinstance(payload, dict) else []
    if isinstance(models, list):
        for item in models:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("name") or item.get("model") or "").strip()
            if not model_id:
                continue
            details = item.get("details", {})
            if not isinstance(details, dict):
                details = {}
            reasoning_efforts, reasoning_default = _dynamic_local_reasoning_efforts(
                model_id,
                str(details.get("parameter_size", "") or ""),
            )
            remote_host = str(item.get("remote_host", "") or "").strip()
            specs.append(
                ProviderModelSpec(
                    id=model_id,
                    label=_dynamic_local_label(model_id),
                    reasoning_efforts=reasoning_efforts,
                    reasoning_default=reasoning_default,
                    context_window_hint=_dynamic_local_hint(model_id, details, remote_host),
                    availability=_dynamic_local_availability(model_id, remote_host),
                    source=f"dynamic Ollama discovery ({request_url or _ollama_base_url()})",
                )
            )
    specs.extend(_discover_lm_studio_provider_model_specs())
    unique: dict[str, ProviderModelSpec] = {}
    for spec in specs:
        unique[spec.id] = spec
    return tuple(unique.values())


def _choose_dynamic_local_preset(discovered: tuple[ProviderModelSpec, ...], preset: str) -> tuple[str, dict[str, str]]:
    normalized = str(preset).strip().lower()
    ids = {spec.id: spec for spec in discovered}
    ordered_ids = [spec.id for spec in discovered if spec.id != "provider-default"]
    preference_groups: dict[str, tuple[str, ...]] = {
        "fast": ("qwen2.5-coder:7b", "qwen3.5:9b", "Qwen3-Coder:latest"),
        "balanced": ("qwen2.5-coder:7b", "qwen3.5:9b", "deepseek-r1:14b", "Qwen3-Coder:latest"),
        "deep": ("qwen3.5:9b", "deepseek-r1:14b", "Qwen3-Coder:latest", "gpt-oss:20b"),
        "plan": ("deepseek-r1:14b", "qwen3.5:9b", "gpt-oss:20b", "Qwen3-Coder:latest"),
    }
    defaults = {
        "fast": {"reasoning_effort": "low"},
        "balanced": {"reasoning_effort": "medium"},
        "deep": {"reasoning_effort": "high"},
        "plan": {"reasoning_effort": "high"},
    }
    if normalized not in defaults:
        raise ValueError(f"Unsupported preset '{preset}' for local. Allowed: fast, balanced, deep, plan")
    for candidate in preference_groups[normalized]:
        if candidate in ids:
            return candidate, dict(defaults[normalized])
    if ordered_ids:
        return ordered_ids[0], dict(defaults[normalized])
    return "provider-default", {}


@lru_cache(maxsize=1)
def _snapshot_provider_ids() -> tuple[str, ...]:
    return kilocode_provider_ids()


def _snapshot_model_features(model: dict[str, object]) -> tuple[str, ...]:
    features: set[str] = set()
    for modality in model.get("modalities", {}).get("input", []) if isinstance(model.get("modalities"), dict) else []:
        features.add(str(modality))
    for modality in model.get("modalities", {}).get("output", []) if isinstance(model.get("modalities"), dict) else []:
        features.add(f"output:{modality}")
    if model.get("reasoning"):
        features.add("reasoning")
    if model.get("tool_call"):
        features.add("tool_use")
    if model.get("attachment"):
        features.add("attachment")
    if model.get("temperature"):
        features.add("temperature")
    if model.get("structured_output"):
        features.add("structured_output")
    if model.get("open_weights"):
        features.add("open_weights")
    interleaved = model.get("interleaved")
    if isinstance(interleaved, dict):
        field = str(interleaved.get("field", "")).strip()
        if field:
            features.add(f"interleaved:{field}")
    return tuple(sorted(features))


def _snapshot_model_reasoning_efforts(model: dict[str, object]) -> tuple[tuple[str, ...], str | None]:
    if not model.get("reasoning"):
        return (), None
    name = str(model.get("name", model.get("id", ""))).lower()
    model_id = str(model.get("id", "")).lower()
    if any(token in name or token in model_id for token in ("thinking", "reasoning", "plan", "pro", "max")):
        return ("medium", "high"), "high"
    return ("low", "medium", "high"), "medium"


def _snapshot_model_context_hint(model: dict[str, object]) -> str:
    parts: list[str] = []
    limit = model.get("limit", {})
    if isinstance(limit, dict) and isinstance(limit.get("context"), (int, float)):
        parts.append(f"context={int(limit['context'])}")
    modalities = model.get("modalities", {})
    if isinstance(modalities, dict):
        input_modalities = ", ".join(str(item) for item in modalities.get("input", []) if str(item).strip())
        output_modalities = ", ".join(str(item) for item in modalities.get("output", []) if str(item).strip())
        if input_modalities:
            parts.append(f"input={input_modalities}")
        if output_modalities:
            parts.append(f"output={output_modalities}")
    if model.get("open_weights"):
        parts.append("open_weights")
    if model.get("tool_call"):
        parts.append("tool_use")
    if model.get("reasoning"):
        parts.append("reasoning")
    return "; ".join(parts)


def _snapshot_provider_default_model(provider: str, models: dict[str, dict[str, object]]) -> str:
    if not models:
        return "provider-default"
    preferred = sorted(
        models.items(),
        key=lambda item: (
            999_999 if item[1].get("preferredIndex") is None else int(item[1].get("preferredIndex", 999_999)),
            str(item[0]),
        ),
    )
    return str(preferred[0][0]) if preferred else "provider-default"


def _snapshot_provider_capability(provider: str) -> ProviderCapability | None:
    info = kilocode_provider_info(provider)
    if not info:
        return None
    model_ids = kilocode_provider_model_ids(provider)
    envs = tuple(str(item) for item in info.get("env", []) if str(item).strip())
    npm = str(info.get("npm", "") or "").strip()
    api = str(info.get("api", "") or "").strip()
    name = str(info.get("name", provider) or provider).strip() or provider
    default_model = _snapshot_provider_default_model(provider, kilocode_provider_models(provider))
    auth_type = "api_key" if envs else "none"
    if provider == "kilo":
        auth_type = "kilo_api_key"
    elif "copilot" in provider:
        auth_type = "oauth_or_token"
    elif provider == "azure":
        auth_type = "azure_api_key"
    elif provider == "google":
        auth_type = "google_api_key"
    elif provider == "openai":
        auth_type = "openai_api_key"
    elif provider == "openrouter":
        auth_type = "openrouter_api_key"
    elif provider == "anthropic":
        auth_type = "anthropic_api_key"
    elif provider == "opencode":
        auth_type = "opencode_api_key"
    elif provider == "ollama-cloud":
        auth_type = "ollama_api_key"
    model_aliases = model_ids or ("provider-default",)
    return ProviderCapability(
        name=provider,
        provider_label=name,
        backend_label=npm or api or provider,
        auth_type=auth_type,
        model_aliases=model_aliases,
        default_model=default_model,
        context_assumption=f"Snapshot-backed provider {name}.",
        supports_account_profiles=bool(envs),
        supports_browser_login=provider in {"kilo", "github-copilot", "github-models"},
        supports_api_key=bool(envs) or provider in {"kilo", "openrouter", "openai", "azure", "google", "github-copilot", "github-models"},
        token_env=envs[0] if envs else "",
        model_env=f"{provider.upper().replace('-', '_')}_MODEL",
        login_url=str(info.get("doc", "")) if isinstance(info.get("doc"), str) else "",
        login_hint=f"Configured from the KiloCode snapshot entry for {name}.",
        source=f"KiloCode snapshot: {provider}",
    )


def _snapshot_provider_model_specs(provider: str) -> tuple[ProviderModelSpec, ...]:
    models = kilocode_provider_models(provider)
    if not models:
        return ()
    specs: list[ProviderModelSpec] = []
    for model_id in kilocode_provider_model_ids(provider):
        model = models.get(model_id)
        if not model:
            continue
        reasoning_efforts, reasoning_default = _snapshot_model_reasoning_efforts(model)
        specs.append(
            ProviderModelSpec(
                id=model_id,
                label=str(model.get("name", model_id)),
                reasoning_efforts=reasoning_efforts,
                reasoning_default=reasoning_default,
                context_window_hint=_snapshot_model_context_hint(model),
                availability="general" if model.get("tool_call", True) else "limited",
                source=f"KiloCode snapshot: {provider}",
            )
        )
    return tuple(specs)


def provider_capability(model: str) -> ProviderCapability:
    def _dynamic_defaults(capability: ProviderCapability, provider_name: str) -> ProviderCapability:
        try:
            specs = provider_model_specs(provider_name)
        except Exception:
            specs = ()
        variants = tuple(spec.id for spec in specs if str(spec.id).strip())
        if not variants:
            return capability
        try:
            if provider_name == "local":
                default_model = next((spec.id for spec in specs if spec.id != "provider-default"), variants[0])
            else:
                default_model, _params = provider_model_preset(provider_name, "balanced")
        except Exception:
            default_model = next((spec.id for spec in specs if spec.id != "provider-default"), variants[0])
        return replace(capability, model_aliases=variants, default_model=default_model)

    if model == "cheap":
        snapshot = _snapshot_provider_capability("openrouter")
        if snapshot is not None:
            return _dynamic_defaults(
                ProviderCapability(
                name="cheap",
                provider_label="OpenRouter",
                backend_label="cheap/openrouter",
                auth_type="api_key",
                model_aliases=(),
                default_model="provider-default",
                context_assumption="OpenRouter-backed cheap provider alias.",
                supports_account_profiles=True,
                supports_browser_login=False,
                supports_api_key=True,
                token_env="OPENROUTER_API_KEY",
                model_env="OPENROUTER_MODEL",
                login_url="https://openrouter.ai/settings/keys",
                login_hint="Use OPENROUTER_API_KEY or account add cheap <name> ENV_VAR.",
                source="KiloCode snapshot: openrouter alias",
                ),
                "cheap",
            )
    if model in {"local", "chatgpt", "claude"}:
        try:
            return _dynamic_defaults(PROVIDER_CAPABILITIES[model], model)
        except KeyError as exc:
            raise ValueError(f"Unsupported model '{model}'.") from exc
    snapshot_capability = _snapshot_provider_capability(model)
    if snapshot_capability is not None:
        return _dynamic_defaults(snapshot_capability, model)
    try:
        return _dynamic_defaults(PROVIDER_CAPABILITIES[model], model)
    except KeyError as exc:
        raise ValueError(f"Unsupported model '{model}'.") from exc


def available_model_variants(model: str) -> tuple[str, ...]:
    return tuple(spec.id for spec in provider_model_specs(model))


def canonicalize_model_variant(model: str, variant: str) -> str:
    clean = str(variant).strip()
    if not clean:
        raise ValueError("Model variant cannot be empty.")
    if clean in available_model_variants(model):
        return clean
    if model in {"openai", "chatgpt"}:
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", clean):
            raise ValueError(f"Unsupported variant '{variant}' for model '{model}'.")
        return clean
    if model == "claude":
        if not re.fullmatch(r"[A-Za-z0-9._:@\-\[\]]+", clean):
            raise ValueError(f"Unsupported variant '{variant}' for model '{model}'.")
        return clean
    if not re.fullmatch(r"[A-Za-z0-9._:@/\-\[\]]+", clean):
        raise ValueError(f"Unsupported variant '{variant}' for model '{model}'.")
    return clean


def model_backends() -> dict[str, dict[str, str]]:
    return {
        name: {"provider": provider_capability(name).provider_label, "label": provider_capability(name).backend_label}
        for name in SUPPORTED_MODELS
    }


def model_variant_catalog() -> dict[str, dict[str, object]]:
    catalog: dict[str, dict[str, object]] = {}
    for name in SUPPORTED_MODELS:
        try:
            specs = provider_model_specs(name)
        except ValueError:
            specs = ()
        catalog[name] = {
            "variants": tuple(spec.id for spec in specs),
            "source": next((spec.source for spec in specs if spec.source), provider_capability(name).source),
        }
    return catalog


def model_token_env() -> dict[str, str]:
    env_map = {name: provider_capability(name).token_env for name in SUPPORTED_MODELS if provider_capability(name).token_env}
    openrouter_env = _openrouter_env_key_from_codex_config()
    if openrouter_env:
        env_map["cheap"] = openrouter_env
    return env_map


def model_name_env() -> dict[str, str]:
    return {name: provider_capability(name).model_env for name in SUPPORTED_MODELS if provider_capability(name).model_env}


def login_urls() -> dict[str, str]:
    return {name: provider_capability(name).login_url for name in SUPPORTED_MODELS if provider_capability(name).login_url}


def provider_model_specs(model: str) -> tuple[ProviderModelSpec, ...]:
    try:
        if model == "local":
            return _discover_local_provider_model_specs()
        if model == "cheap":
            catalog_specs = _catalog_provider_model_specs("cheap")
            if catalog_specs:
                return catalog_specs
            snapshot_specs = _snapshot_provider_model_specs("openrouter")
            if snapshot_specs:
                return (
                    ProviderModelSpec(
                        id="provider-default",
                        label="Provider default",
                        reasoning_efforts=("low", "medium"),
                        reasoning_default="medium",
                        availability="provider-default",
                        source="OpenRouter provider setting",
                    ),
                    *snapshot_specs,
                )
            return _discover_openrouter_provider_model_specs()
        catalog_specs = _catalog_provider_model_specs(model)
        if catalog_specs:
            return catalog_specs
        snapshot_specs = _snapshot_provider_model_specs(model)
        if snapshot_specs:
            return snapshot_specs
        if model in _snapshot_provider_ids():
            return _snapshot_provider_model_specs(model)
        return ()
    except KeyError as exc:
        raise ValueError(f"Unsupported model '{model}'.") from exc


def provider_model_spec(model: str, provider_model: str) -> ProviderModelSpec | None:
    for spec in provider_model_specs(model):
        if spec.id == provider_model:
            return spec
    return None


def provider_model_preset(model: str, preset: str) -> tuple[str, dict[str, str]]:
    normalized = str(preset).strip().lower()
    if model == "local":
        return _choose_dynamic_local_preset(provider_model_specs("local"), normalized)
    specs = list(provider_model_specs(model))
    usable = [spec for spec in specs if spec.id != "provider-default"] or list(specs)
    if not usable:
        raise ValueError(f"Unsupported model '{model}'.")
    try:
        from .model_catalog import catalog_entry_for_provider_model
    except Exception:
        catalog_entry_for_provider_model = None  # type: ignore[assignment]
    catalog = _load_ai_models_catalog()

    def _score(spec: ProviderModelSpec) -> float:
        entry = catalog_entry_for_provider_model(model, spec.id, catalog) if catalog_entry_for_provider_model else None
        features = {str(item).lower() for item in (entry.get("features", []) if isinstance(entry, dict) else [])}
        context_window = entry.get("context_window") if isinstance(entry, dict) else None
        blended = entry.get("blended_price_usd_per_1m_tokens") if isinstance(entry, dict) else None
        reasoning_default = str(spec.reasoning_default or "").lower()
        reasoning_efforts = {str(item).lower() for item in spec.reasoning_efforts}
        score = 0.0
        if normalized == "fast":
            score += 4.0 if "low" in reasoning_efforts else 0.0
            score += 1.0 if reasoning_default == "low" else 0.0
            if isinstance(blended, (int, float)):
                score -= float(blended) / 10.0
            if isinstance(context_window, (int, float)):
                score += max(0.0, 1.0 - (float(context_window) / 1_000_000.0))
        elif normalized == "balanced":
            score += 4.0 if "medium" in reasoning_efforts else 1.0 if reasoning_efforts else 0.0
            score += 1.0 if reasoning_default == "medium" else 0.0
            if isinstance(context_window, (int, float)):
                score += 1.0 - abs(float(context_window) - 400_000.0) / 1_000_000.0
            if "reasoning" in features:
                score += 0.5
        elif normalized in {"deep", "plan"}:
            score += 4.0 if "high" in reasoning_efforts else 1.0 if "medium" in reasoning_efforts else 0.0
            score += 1.0 if reasoning_default == "high" else 0.0
            if "reasoning" in features:
                score += 1.0
            if isinstance(context_window, (int, float)):
                score += min(float(context_window), 1_000_000.0) / 1_000_000.0
        else:
            raise ValueError(f"Unsupported preset '{preset}' for {model}. Allowed: fast, balanced, deep, plan")
        if model in {"cheap", "openai", "chatgpt", "claude"} and "tool_use" in features:
            score += 0.25
        return score

    ranked = sorted((( _score(spec), spec.id, spec) for spec in usable), key=lambda item: (item[0], item[1]), reverse=True)
    if not ranked:
        raise ValueError(f"Unsupported model '{model}'.")
    chosen = ranked[0][2]
    if normalized == "fast":
        effort = next((effort for effort in chosen.reasoning_efforts if effort == "low"), None) or chosen.reasoning_default or (chosen.reasoning_efforts[0] if chosen.reasoning_efforts else None)
    elif normalized == "balanced":
        effort = chosen.reasoning_default or next((effort for effort in chosen.reasoning_efforts if effort == "medium"), None) or (chosen.reasoning_efforts[0] if chosen.reasoning_efforts else None)
    else:
        effort = next((effort for effort in chosen.reasoning_efforts if effort == "high"), None) or chosen.reasoning_default or (chosen.reasoning_efforts[-1] if chosen.reasoning_efforts else None)
    params = {"reasoning_effort": effort} if effort else {}
    return chosen.id, params


def _build_supported_models() -> tuple[str, ...]:
    ordered = ["local", "cheap", "chatgpt", "claude", *list(_snapshot_provider_ids())]
    return tuple(dict.fromkeys(ordered))


SUPPORTED_MODELS = _build_supported_models()
