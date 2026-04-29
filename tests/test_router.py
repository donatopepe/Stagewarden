from __future__ import annotations

import unittest

from stagewarden.router import ModelRouter
from stagewarden.provider_registry import available_model_variants


class RouterTests(unittest.TestCase):
    def test_simple_task_prefers_cloud_entry_tier(self) -> None:
        router = ModelRouter()
        self.assertEqual(router.choose_model("list files", "inspect workspace"), "cheap")

    def test_complex_debug_task_prefers_gpt(self) -> None:
        router = ModelRouter()
        model = router.choose_model("debug a complex traceback in production", "implement fix")
        self.assertEqual(model, "chatgpt")

    def test_risky_task_prefers_gpt(self) -> None:
        router = ModelRouter()
        model = router.choose_model("update auth flow in production", "review and validate")
        self.assertEqual(model, "chatgpt")

    def test_failure_escalation_progression(self) -> None:
        router = ModelRouter()
        self.assertEqual(router.choose_model("x", "y", failure_count=2), "openai")
        self.assertEqual(router.choose_model("x", "y", failure_count=3), "claude")
        self.assertEqual(router.escalate("chatgpt"), "openai")
        self.assertEqual(router.escalate("openai"), "claude")
        self.assertEqual(router.fallback_for_api_failure("chatgpt"), "openai")
        self.assertEqual(router.fallback_for_api_failure("openai"), "claude")

    def test_router_chooses_provider_specific_variants(self) -> None:
        router = ModelRouter()
        self.assertEqual(router.choose_variant("claude", "list files", "inspect workspace"), "haiku")
        self.assertEqual(router.choose_variant("claude", "debug a complex traceback in production", "implement fix"), "opus")
        self.assertEqual(router.choose_variant("claude", "design architecture roadmap", "planner stage"), "opusplan")
        self.assertEqual(router.choose_variant("openai", "list files", "inspect workspace"), "gpt-5.4-mini")
        self.assertEqual(router.choose_variant("openai", "debug a complex traceback in production", "implement fix"), "gpt-5.4")
        self.assertEqual(router.choose_variant("chatgpt", "list files", "inspect workspace"), "codex-mini-latest")
        self.assertEqual(router.choose_variant("chatgpt", "debug a complex traceback in production", "implement fix"), "gpt-5.3-codex")

    def test_router_accepts_kilocode_snapshot_providers(self) -> None:
        router = ModelRouter()
        router.configure(enabled_models=["kilo", "openai", "cheap"], preferred_model="kilo")
        self.assertIn("kilo", router.status()["active_models"])
        self.assertEqual(router.choose_model("inspect workspace", "list files"), "kilo")
        variant = router.choose_variant("kilo", "design architecture roadmap", "planner stage")
        self.assertIn(variant, available_model_variants("kilo"))
        self.assertNotEqual(variant, "provider-default")


if __name__ == "__main__":
    unittest.main()
