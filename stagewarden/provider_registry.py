from __future__ import annotations

import re
from dataclasses import dataclass


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
        model_aliases=(
            "provider-default",
            "qwen2.5-coder:7b",
            "qwen3.5:9b",
            "deepseek-r1:14b",
            "sqlcoder:15b",
            "gpt-oss:20b",
            "Qwen3-Coder:latest",
            "codestral:latest",
        ),
        default_model="provider-default",
        context_assumption="Local Ollama context depends on the selected local model; prefer tool-capable coding models for agentic execution.",
        supports_account_profiles=False,
        supports_browser_login=False,
        supports_api_key=False,
        token_env="",
        model_env="OLLAMA_MODEL",
        login_url="",
        login_hint="No login required. Configure Ollama and optionally OLLAMA_MODEL. For agentic use prefer qwen2.5-coder:7b or qwen3.5:9b over models that do not support tools.",
        source="workspace/provider setting + local Ollama operator guidance",
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
        ProviderModelSpec(
            id="qwen2.5-coder:7b",
            label="Qwen 2.5 Coder 7B",
            reasoning_efforts=("low", "medium"),
            reasoning_default="medium",
            context_window_hint="Recommended local agentic default for Codex-style file/tool work.",
            availability="local-agentic",
            source="local Ollama operator guidance",
        ),
        ProviderModelSpec(
            id="qwen3.5:9b",
            label="Qwen 3.5 9B",
            reasoning_efforts=("medium", "high"),
            reasoning_default="medium",
            context_window_hint="Stronger local general reasoning choice when qwen2.5-coder is insufficient.",
            availability="local-agentic",
            source="local Ollama operator guidance",
        ),
        ProviderModelSpec(
            id="deepseek-r1:14b",
            label="DeepSeek R1 14B",
            reasoning_efforts=("medium", "high"),
            reasoning_default="high",
            context_window_hint="Use for deeper local reasoning when latency is acceptable.",
            availability="local-agentic",
            source="local Ollama operator guidance",
        ),
        ProviderModelSpec(
            id="sqlcoder:15b",
            label="SQLCoder 15B",
            reasoning_efforts=("medium",),
            reasoning_default="medium",
            context_window_hint="Specialized local SQL work; narrower than the default coding path.",
            availability="local-specialized",
            source="local Ollama operator guidance",
        ),
        ProviderModelSpec(
            id="gpt-oss:20b",
            label="GPT-OSS 20B",
            reasoning_efforts=("medium", "high"),
            reasoning_default="medium",
            context_window_hint="Large local general model; validate tool behavior before using as the default agentic route.",
            availability="local-experimental",
            source="local Ollama operator guidance",
        ),
        ProviderModelSpec(
            id="Qwen3-Coder:latest",
            label="Qwen3 Coder Latest",
            reasoning_efforts=("medium", "high"),
            reasoning_default="medium",
            context_window_hint="Large local coding model; useful when RAM and latency allow.",
            availability="local-agentic",
            source="local Ollama operator guidance",
        ),
        ProviderModelSpec(
            id="codestral:latest",
            label="Codestral Latest",
            reasoning_efforts=("low", "medium"),
            reasoning_default="low",
            context_window_hint="Not suitable as the default agentic path when the local Codex/Ollama bridge reports no tool support.",
            availability="local-limited",
            source="local Ollama operator guidance",
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


def provider_capability(model: str) -> ProviderCapability:
    try:
        return PROVIDER_CAPABILITIES[model]
    except KeyError as exc:
        raise ValueError(f"Unsupported model '{model}'.") from exc


def available_model_variants(model: str) -> tuple[str, ...]:
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
            "fast": ("qwen2.5-coder:7b", {"reasoning_effort": "low"}),
            "balanced": ("qwen2.5-coder:7b", {"reasoning_effort": "medium"}),
            "deep": ("qwen3.5:9b", {"reasoning_effort": "high"}),
            "plan": ("deepseek-r1:14b", {"reasoning_effort": "high"}),
        },
    }
    provider_presets = presets.get(model, {})
    if normalized not in provider_presets:
        raise ValueError(
            f"Unsupported preset '{preset}' for {model}. Allowed: {', '.join(provider_presets) or 'none'}"
        )
    return provider_presets[normalized]
