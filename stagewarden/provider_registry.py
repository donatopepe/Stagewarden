from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import urlopen


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
        model_aliases=("provider-default",),
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
        model_aliases=("provider-default",),
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
        model_aliases=(
            "provider-default",
            "codex-mini-latest",
            "gpt-5.1-codex",
            "gpt-5.1-codex-mini",
            "gpt-5.2-codex",
            "gpt-5.3-codex",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
        ),
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
        model_aliases=(
            "provider-default",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
            "gpt-5.3-codex",
            "gpt-5.2-codex",
            "gpt-5.1-codex",
            "gpt-5.1-codex-mini",
            "codex-mini-latest",
        ),
        default_model="gpt-5.4",
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
        model_aliases=("default", "sonnet", "opus", "haiku", "sonnet[1m]", "opusplan"),
        default_model="sonnet",
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


PROVIDER_MODEL_SPECS: dict[str, tuple[ProviderModelSpec, ...]] = {
    "local": (
        ProviderModelSpec(
            id="provider-default",
            label="Provider default",
            reasoning_efforts=(),
            reasoning_default=None,
            availability="workspace",
            source="workspace/provider setting",
        ),
    ),
    "cheap": (
        ProviderModelSpec(
            id="provider-default",
            label="Provider default",
            reasoning_efforts=("low", "medium"),
            reasoning_default="medium",
            availability="provider-default",
            source="OpenRouter provider setting",
        ),
    ),
    "chatgpt": (
        ProviderModelSpec("provider-default", "Provider default", ("low", "medium", "high"), "medium", source="OpenAI Codex/OpenAI models docs"),
        ProviderModelSpec("codex-mini-latest", "Codex Mini Latest", ("low", "medium"), "medium", source="OpenAI Codex/OpenAI models docs"),
        ProviderModelSpec("gpt-5.1-codex", "GPT-5.1 Codex", ("low", "medium", "high"), "medium", source="OpenAI Codex/OpenAI models docs"),
        ProviderModelSpec("gpt-5.1-codex-mini", "GPT-5.1 Codex Mini", ("medium", "high"), "medium", source="OpenAI Codex/OpenAI models docs"),
        ProviderModelSpec("gpt-5.2-codex", "GPT-5.2 Codex", ("low", "medium", "high"), "medium", source="OpenAI Codex/OpenAI models docs"),
        ProviderModelSpec("gpt-5.3-codex", "GPT-5.3 Codex", ("low", "medium", "high"), "medium", source="OpenAI Codex/OpenAI models docs"),
        ProviderModelSpec("gpt-5.4", "GPT-5.4", ("low", "medium", "high"), "medium", source="OpenAI Codex/OpenAI models docs"),
        ProviderModelSpec("gpt-5.4-mini", "GPT-5.4 Mini", ("low", "medium", "high"), "medium", source="OpenAI Codex/OpenAI models docs"),
        ProviderModelSpec("gpt-5.4-nano", "GPT-5.4 Nano", ("low", "medium"), "medium", source="OpenAI Codex/OpenAI models docs"),
    ),
    "openai": (
        ProviderModelSpec("provider-default", "Provider default", ("low", "medium", "high"), "medium", source="OpenAI models docs"),
        ProviderModelSpec("gpt-5.4", "GPT-5.4", ("low", "medium", "high"), "medium", source="OpenAI models docs"),
        ProviderModelSpec("gpt-5.4-mini", "GPT-5.4 Mini", ("low", "medium", "high"), "medium", source="OpenAI models docs"),
        ProviderModelSpec("gpt-5.4-nano", "GPT-5.4 Nano", ("low", "medium"), "medium", source="OpenAI models docs"),
        ProviderModelSpec("gpt-5.3-codex", "GPT-5.3 Codex", ("low", "medium", "high"), "medium", source="OpenAI models docs"),
        ProviderModelSpec("gpt-5.2-codex", "GPT-5.2 Codex", ("low", "medium", "high"), "medium", source="OpenAI models docs"),
        ProviderModelSpec("gpt-5.1-codex", "GPT-5.1 Codex", ("low", "medium", "high"), "medium", source="OpenAI models docs"),
        ProviderModelSpec("gpt-5.1-codex-mini", "GPT-5.1 Codex Mini", ("medium", "high"), "medium", source="OpenAI models docs"),
        ProviderModelSpec("codex-mini-latest", "Codex Mini Latest", ("low", "medium"), "medium", source="OpenAI models docs"),
    ),
    "claude": (
        ProviderModelSpec("default", "Default", ("low", "medium", "high"), "medium", source="Claude Code model configuration docs"),
        ProviderModelSpec("sonnet", "Claude Sonnet", ("low", "medium", "high"), "medium", source="Claude Code model configuration docs"),
        ProviderModelSpec("opus", "Claude Opus", ("medium", "high"), "high", source="Claude Code model configuration docs"),
        ProviderModelSpec("haiku", "Claude Haiku", ("low", "medium"), "medium", source="Claude Code model configuration docs"),
        ProviderModelSpec("sonnet[1m]", "Claude Sonnet 1M", ("medium", "high"), "medium", source="Claude Code model configuration docs"),
        ProviderModelSpec("opusplan", "Claude Opus Plan", ("high",), "high", source="Claude Code model configuration docs"),
    ),
}


SUPPORTED_MODELS = tuple(PROVIDER_CAPABILITIES.keys())


def _ollama_base_url() -> str:
    return os.environ.get("STAGEWARDEN_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


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


def _dynamic_local_label(name: str) -> str:
    base = name.split(":", 1)[0].replace("-", " ").replace("_", " ").strip()
    if not base:
        return name
    return " ".join(part.upper() if part.isupper() else part.capitalize() for part in base.split())


def _discover_local_provider_model_specs() -> tuple[ProviderModelSpec, ...]:
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
        return PROVIDER_MODEL_SPECS["local"]
    models = payload.get("models", [])
    if not isinstance(models, list):
        return PROVIDER_MODEL_SPECS["local"]
    specs: list[ProviderModelSpec] = [PROVIDER_MODEL_SPECS["local"][0]]
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
                source=f"dynamic Ollama discovery ({request_url})",
            )
        )
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


def provider_capability(model: str) -> ProviderCapability:
    try:
        return PROVIDER_CAPABILITIES[model]
    except KeyError as exc:
        raise ValueError(f"Unsupported model '{model}'.") from exc


def available_model_variants(model: str) -> tuple[str, ...]:
    if model == "local":
        return tuple(spec.id for spec in provider_model_specs(model))
    return provider_capability(model).model_aliases


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
        name: {"provider": capability.provider_label, "label": capability.backend_label}
        for name, capability in PROVIDER_CAPABILITIES.items()
    }


def model_variant_catalog() -> dict[str, dict[str, object]]:
    return {
        name: {"variants": capability.model_aliases, "source": capability.source}
        for name, capability in PROVIDER_CAPABILITIES.items()
    }


def model_token_env() -> dict[str, str]:
    return {name: capability.token_env for name, capability in PROVIDER_CAPABILITIES.items() if capability.token_env}


def model_name_env() -> dict[str, str]:
    return {name: capability.model_env for name, capability in PROVIDER_CAPABILITIES.items() if capability.model_env}


def login_urls() -> dict[str, str]:
    return {name: capability.login_url for name, capability in PROVIDER_CAPABILITIES.items() if capability.login_url}


def provider_model_specs(model: str) -> tuple[ProviderModelSpec, ...]:
    try:
        if model == "local":
            return _discover_local_provider_model_specs()
        return PROVIDER_MODEL_SPECS[model]
    except KeyError as exc:
        raise ValueError(f"Unsupported model '{model}'.") from exc


def provider_model_spec(model: str, provider_model: str) -> ProviderModelSpec | None:
    for spec in provider_model_specs(model):
        if spec.id == provider_model:
            return spec
    return None


def provider_model_preset(model: str, preset: str) -> tuple[str, dict[str, str]]:
    normalized = str(preset).strip().lower()
    presets: dict[str, dict[str, tuple[str, dict[str, str]]]] = {
        "chatgpt": {
            "fast": ("codex-mini-latest", {"reasoning_effort": "low"}),
            "balanced": ("gpt-5.1-codex-mini", {"reasoning_effort": "medium"}),
            "deep": ("gpt-5.3-codex", {"reasoning_effort": "high"}),
            "plan": ("gpt-5.4", {"reasoning_effort": "high"}),
        },
        "openai": {
            "fast": ("gpt-5.4-mini", {"reasoning_effort": "low"}),
            "balanced": ("gpt-5.2-codex", {"reasoning_effort": "medium"}),
            "deep": ("gpt-5.4", {"reasoning_effort": "high"}),
            "plan": ("gpt-5.4", {"reasoning_effort": "high"}),
        },
        "claude": {
            "fast": ("haiku", {"reasoning_effort": "low"}),
            "balanced": ("sonnet", {"reasoning_effort": "medium"}),
            "deep": ("opus", {"reasoning_effort": "high"}),
            "plan": ("opusplan", {"reasoning_effort": "high"}),
        },
        "cheap": {
            "fast": ("provider-default", {"reasoning_effort": "low"}),
            "balanced": ("provider-default", {"reasoning_effort": "medium"}),
        },
        "local": {
            "fast": ("provider-default", {}),
            "balanced": ("provider-default", {}),
        },
    }
    if model == "local":
        return _choose_dynamic_local_preset(provider_model_specs("local"), normalized)
    provider_presets = presets.get(model, {})
    if normalized not in provider_presets:
        raise ValueError(
            f"Unsupported preset '{preset}' for {model}. Allowed: {', '.join(provider_presets) or 'none'}"
        )
    return provider_presets[normalized]
