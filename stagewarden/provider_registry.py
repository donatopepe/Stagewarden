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


PROVIDER_CAPABILITIES: dict[str, ProviderCapability] = {
    "local": ProviderCapability(
        name="local",
        provider_label="ollama",
        backend_label="local/ollama",
        auth_type="none",
        model_aliases=("provider-default",),
        default_model="provider-default",
        context_assumption="Local Ollama context depends on the selected local model.",
        supports_account_profiles=False,
        supports_browser_login=False,
        supports_api_key=False,
        token_env="",
        model_env="OLLAMA_MODEL",
        login_url="",
        login_hint="No login required. Configure Ollama and optionally OLLAMA_MODEL.",
        source="workspace/provider setting",
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
        login_hint="Use account login chatgpt <profile>; Stagewarden never scrapes browser tokens.",
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
