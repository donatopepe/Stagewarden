from __future__ import annotations

import unittest

from stagewarden.provider_registry import (
    SUPPORTED_MODELS,
    available_model_variants,
    canonicalize_model_variant,
    model_backends,
    provider_capability,
    provider_model_preset,
    provider_model_specs,
)


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
        self.assertIn("qwen2.5-coder:7b", available_model_variants("local"))
        self.assertEqual(canonicalize_model_variant("openai", "gpt-5.4-mini"), "gpt-5.4-mini")

    def test_local_provider_exposes_agentic_safe_presets_and_specs(self) -> None:
        specs = {spec.id: spec for spec in provider_model_specs("local")}
        self.assertIn("qwen2.5-coder:7b", specs)
        self.assertIn("codestral:latest", specs)
        self.assertIn("tool support", specs["codestral:latest"].context_window_hint.lower())

        fast_model, fast_params = provider_model_preset("local", "fast")
        plan_model, plan_params = provider_model_preset("local", "plan")
        self.assertEqual(fast_model, "qwen2.5-coder:7b")
        self.assertEqual(fast_params["reasoning_effort"], "low")
        self.assertEqual(plan_model, "deepseek-r1:14b")
        self.assertEqual(plan_params["reasoning_effort"], "high")


if __name__ == "__main__":
    unittest.main()
