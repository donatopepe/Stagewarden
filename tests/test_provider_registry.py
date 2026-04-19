from __future__ import annotations

import unittest

from stagewarden.provider_registry import (
    SUPPORTED_MODELS,
    available_model_variants,
    canonicalize_model_variant,
    model_backends,
    provider_capability,
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
        self.assertEqual(canonicalize_model_variant("openai", "gpt-5.4-mini"), "gpt-5.4-mini")


if __name__ == "__main__":
    unittest.main()
