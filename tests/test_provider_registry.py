from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stagewarden.provider_registry import (
    SUPPORTED_MODELS,
    available_model_variants,
    canonicalize_model_variant,
    model_backends,
    model_token_env,
    provider_capability,
    provider_model_preset,
    provider_model_specs,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self.payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class ProviderRegistryTests(unittest.TestCase):
    def test_registry_exposes_provider_capabilities(self) -> None:
        self.assertGreaterEqual(len(SUPPORTED_MODELS), 5)
        self.assertEqual(SUPPORTED_MODELS[:4], ("local", "cheap", "chatgpt", "claude"))
        self.assertIn("openai", provider_capability("openai").name)
        chatgpt = provider_capability("chatgpt")
        openai = provider_capability("openai")
        claude = provider_capability("claude")

        self.assertEqual(chatgpt.auth_type, "chatgpt_plan_oauth")
        self.assertFalse(chatgpt.supports_api_key)
        self.assertTrue(chatgpt.supports_browser_login)
        self.assertEqual(openai.auth_type, "openai_api_key")
        self.assertTrue(openai.supports_api_key)
        self.assertFalse(claude.supports_browser_login)
        self.assertTrue(claude.supports_api_key)

    def test_registry_drives_backend_and_variant_catalogs(self) -> None:
        backends = model_backends()
        self.assertEqual(backends["claude"]["label"], "claude/sonnet")
        self.assertIn("opusplan", available_model_variants("claude"))
        self.assertIn(canonicalize_model_variant("openai", "gpt-5.4-mini"), available_model_variants("openai"))

    def test_catalog_driven_provider_presets_are_dynamic(self) -> None:
        catalog = {
            "models": [
                {
                    "provider": "openai",
                    "model_id": "gpt-5.4-nano",
                    "model_name": "GPT-5.4 Nano",
                    "context_window": 128000,
                    "cost_per_input_token_usd": 1e-6,
                    "cost_per_output_token_usd": 4e-6,
                    "blended_price_usd_per_1m_tokens": 2.5,
                    "features": ["text"],
                    "source": "openrouter:gpt-5.4-nano",
                },
                {
                    "provider": "openai",
                    "model_id": "gpt-5.4",
                    "model_name": "GPT-5.4",
                    "context_window": 1048576,
                    "cost_per_input_token_usd": 2.5e-6,
                    "cost_per_output_token_usd": 1.5e-5,
                    "blended_price_usd_per_1m_tokens": 5.63,
                    "features": ["text", "reasoning", "tool_use", "structured_output"],
                    "source": "openrouter:gpt-5.4",
                },
                {
                    "provider": "claude",
                    "model_id": "haiku",
                    "model_name": "Claude Haiku",
                    "context_window": 200000,
                    "cost_per_input_token_usd": 8e-7,
                    "cost_per_output_token_usd": 4e-6,
                    "blended_price_usd_per_1m_tokens": 1.6,
                    "features": ["text"],
                    "source": "anthropic:haiku",
                },
                {
                    "provider": "claude",
                    "model_id": "opus",
                    "model_name": "Claude Opus",
                    "context_window": 1000000,
                    "cost_per_input_token_usd": 1.5e-5,
                    "cost_per_output_token_usd": 7.5e-5,
                    "blended_price_usd_per_1m_tokens": 33.75,
                    "features": ["text", "reasoning", "tool_use"],
                    "source": "anthropic:opus",
                },
                {
                    "provider": "cheap",
                    "model_id": "provider-default",
                    "model_name": "Provider default",
                    "features": [],
                    "source": "openrouter:provider-default",
                },
                {
                    "provider": "cheap",
                    "model_id": "cheap-fast",
                    "model_name": "Cheap Fast",
                    "context_window": 128000,
                    "cost_per_input_token_usd": 5e-7,
                    "cost_per_output_token_usd": 1e-6,
                    "blended_price_usd_per_1m_tokens": 0.88,
                    "features": ["text"],
                    "source": "openrouter:cheap-fast",
                },
                {
                    "provider": "cheap",
                    "model_id": "cheap-deep",
                    "model_name": "Cheap Deep",
                    "context_window": 1000000,
                    "cost_per_input_token_usd": 2e-6,
                    "cost_per_output_token_usd": 8e-6,
                    "blended_price_usd_per_1m_tokens": 3.5,
                    "features": ["text", "reasoning", "tool_use"],
                    "source": "openrouter:cheap-deep",
                },
            ]
        }
        with patch("stagewarden.provider_registry._load_ai_models_catalog", return_value=catalog):
            self.assertIn("gpt-5.4-nano", available_model_variants("openai"))
            self.assertEqual(provider_model_preset("openai", "fast")[0], "gpt-5.4-nano")
            self.assertEqual(provider_model_preset("openai", "deep")[0], "gpt-5.4")
            self.assertEqual(provider_model_preset("claude", "fast")[0], "haiku")
            self.assertEqual(provider_model_preset("claude", "plan")[0], "opus")
            self.assertEqual(provider_model_preset("cheap", "fast")[0], "cheap-fast")
            self.assertEqual(provider_model_preset("cheap", "deep")[0], "cheap-deep")

    def test_local_provider_uses_dynamic_ollama_catalog_and_presets(self) -> None:
        original = os.environ.get("STAGEWARDEN_OLLAMA_BASE_URL")
        original_lm_studio = os.environ.get("STAGEWARDEN_LM_STUDIO_BASE_URL")
        os.environ["STAGEWARDEN_OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
        os.environ["STAGEWARDEN_LM_STUDIO_BASE_URL"] = "http://127.0.0.1:1234"
        self.addCleanup(lambda: os.environ.pop("STAGEWARDEN_OLLAMA_BASE_URL", None) if original is None else os.environ.__setitem__("STAGEWARDEN_OLLAMA_BASE_URL", original))
        self.addCleanup(lambda: os.environ.pop("STAGEWARDEN_LM_STUDIO_BASE_URL", None) if original_lm_studio is None else os.environ.__setitem__("STAGEWARDEN_LM_STUDIO_BASE_URL", original_lm_studio))
        payload = {
            "models": [
                {
                    "name": "qwen2.5-coder:7b",
                    "details": {"family": "qwen2", "parameter_size": "7.6B", "quantization_level": "Q4_K_M"},
                },
                {
                    "name": "deepseek-r1:14b",
                    "details": {"family": "qwen2", "parameter_size": "14.8B", "quantization_level": "Q4_K_M"},
                },
                {
                    "name": "codestral:latest",
                    "details": {"family": "llama", "parameter_size": "22.2B", "quantization_level": "Q4_0"},
                },
            ]
        }
        lm_studio_payload = {
            "data": [
                {"id": "llama-3.1-8b-instruct"},
                {"id": "deepseek-r1-distill-qwen-14b"},
            ]
        }

        def fake_urlopen(request, timeout=0):
            url = getattr(request, "full_url", request)
            if str(url).endswith("/api/tags"):
                return _FakeResponse(payload)
            if str(url).endswith("/v1/models"):
                return _FakeResponse(lm_studio_payload)
            raise AssertionError(f"Unexpected request: {url}")

        with patch("stagewarden.provider_registry.urlopen", side_effect=fake_urlopen):
            specs = {spec.id: spec for spec in provider_model_specs("local")}

            self.assertIn("qwen2.5-coder:7b", specs)
            self.assertIn("deepseek-r1:14b", specs)
            self.assertIn("codestral:latest", specs)
            self.assertIn("llama-3.1-8b-instruct", specs)
            self.assertIn("deepseek-r1-distill-qwen-14b", specs)
            self.assertEqual(specs["qwen2.5-coder:7b"].availability, "local-agentic")
            self.assertEqual(specs["codestral:latest"].availability, "local-limited")
            self.assertEqual(specs["llama-3.1-8b-instruct"].availability, "local-lm-studio")
            self.assertIn("validate tool support", specs["codestral:latest"].context_window_hint.lower())
            self.assertIn("qwen2.5-coder:7b", available_model_variants("local"))

            fast_model, fast_params = provider_model_preset("local", "fast")
            plan_model, plan_params = provider_model_preset("local", "plan")
            self.assertEqual(fast_model, "qwen2.5-coder:7b")
            self.assertEqual(fast_params["reasoning_effort"], "low")
            self.assertEqual(plan_model, "deepseek-r1:14b")
            self.assertEqual(plan_params["reasoning_effort"], "high")

    def test_cheap_provider_reads_openrouter_models_and_env_key_from_codex_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                """
[model_providers.openrouter]
env_key = "OPENROUTER_STAGEWARDEN"

[profiles.or-gpt54]
model_provider = "openrouter"
model = "openai/gpt-5.4"
model_reasoning_effort = "medium"

[profiles.or-sonnet]
model_provider = "openrouter"
model = "anthropic/claude-sonnet-4.6"
model_reasoning_effort = "high"

[profiles.local]
model_provider = "ollama"
model = "qwen2.5-coder:7b"
""".strip(),
                encoding="utf-8",
            )
            original = os.environ.get("STAGEWARDEN_CODEX_CONFIG")
            os.environ["STAGEWARDEN_CODEX_CONFIG"] = str(config_path)
            self.addCleanup(lambda: os.environ.pop("STAGEWARDEN_CODEX_CONFIG", None) if original is None else os.environ.__setitem__("STAGEWARDEN_CODEX_CONFIG", original))

            specs = {spec.id: spec for spec in provider_model_specs("cheap")}
            env_map = model_token_env()

            self.assertIn("provider-default", specs)
            self.assertIn("openai/gpt-5.4", specs)
            self.assertIn("anthropic/claude-sonnet-4.6", specs)
            self.assertIn(specs["anthropic/claude-sonnet-4.6"].reasoning_default, {"high", "medium"})
            self.assertTrue(specs["openai/gpt-5.4"].context_window_hint.startswith("context="))
            self.assertIn("reasoning", specs["openai/gpt-5.4"].context_window_hint)
            self.assertEqual(env_map["cheap"], "OPENROUTER_STAGEWARDEN")


if __name__ == "__main__":
    unittest.main()
