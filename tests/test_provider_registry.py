from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from stagewarden.provider_registry import (
    SUPPORTED_MODELS,
    available_model_variants,
    canonicalize_model_variant,
    model_backends,
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
        self.assertEqual(SUPPORTED_MODELS, ("local", "cheap", "chatgpt", "openai", "claude"))
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
        self.assertEqual(canonicalize_model_variant("openai", "gpt-5.4-mini"), "gpt-5.4-mini")

    def test_local_provider_uses_dynamic_ollama_catalog_and_presets(self) -> None:
        original = os.environ.get("STAGEWARDEN_OLLAMA_BASE_URL")
        os.environ["STAGEWARDEN_OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
        self.addCleanup(lambda: os.environ.pop("STAGEWARDEN_OLLAMA_BASE_URL", None) if original is None else os.environ.__setitem__("STAGEWARDEN_OLLAMA_BASE_URL", original))
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
        with patch("stagewarden.provider_registry.urlopen", return_value=_FakeResponse(payload)):
            specs = {spec.id: spec for spec in provider_model_specs("local")}

            self.assertIn("qwen2.5-coder:7b", specs)
            self.assertIn("deepseek-r1:14b", specs)
            self.assertIn("codestral:latest", specs)
            self.assertEqual(specs["qwen2.5-coder:7b"].availability, "local-agentic")
            self.assertEqual(specs["codestral:latest"].availability, "local-limited")
            self.assertIn("validate tool support", specs["codestral:latest"].context_window_hint.lower())
            self.assertIn("qwen2.5-coder:7b", available_model_variants("local"))

            fast_model, fast_params = provider_model_preset("local", "fast")
            plan_model, plan_params = provider_model_preset("local", "plan")
            self.assertEqual(fast_model, "qwen2.5-coder:7b")
            self.assertEqual(fast_params["reasoning_effort"], "low")
            self.assertEqual(plan_model, "deepseek-r1:14b")
            self.assertEqual(plan_params["reasoning_effort"], "high")


if __name__ == "__main__":
    unittest.main()
