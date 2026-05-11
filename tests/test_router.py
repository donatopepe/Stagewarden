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

    def test_regulatory_task_prefers_deeper_provider(self) -> None:
        router = ModelRouter()
        model = router.choose_model(
            "regulatory compliance audit for DPIA, retention, and security governance",
            "prepare the board pack",
        )
        self.assertIn(model, {"openai", "claude"})
        variant = router.choose_variant(
            model,
            "regulatory compliance audit for DPIA, retention, and security governance",
            "prepare the board pack",
        )
        self.assertIsNotNone(variant)
        self.assertIn(variant, available_model_variants(model))
        self.assertNotEqual(variant, "provider-default")

    def test_legal_task_prefers_deeper_provider(self) -> None:
        router = ModelRouter()
        model = router.choose_model(
            "legal hold and contract disclosure risk for a board escalation",
            "prepare the evidence pack",
        )
        self.assertIn(model, {"openai", "claude"})
        variant = router.choose_variant(
            model,
            "legal hold and contract disclosure risk for a board escalation",
            "prepare the evidence pack",
        )
        self.assertIsNotNone(variant)
        self.assertIn(variant, available_model_variants(model))
        self.assertNotEqual(variant, "provider-default")

    def test_incident_task_prefers_deeper_provider(self) -> None:
        router = ModelRouter()
        model = router.choose_model(
            "incident response for a breach, rollback, and outage recovery",
            "prepare the recovery pack",
        )
        self.assertIn(model, {"openai", "claude"})
        variant = router.choose_variant(
            model,
            "incident response for a breach, rollback, and outage recovery",
            "prepare the recovery pack",
        )
        self.assertIsNotNone(variant)
        self.assertIn(variant, available_model_variants(model))
        self.assertNotEqual(variant, "provider-default")

    def test_vendor_task_prefers_deeper_provider(self) -> None:
        router = ModelRouter()
        model = router.choose_model(
            "vendor failure and supplier collapse during delivery",
            "prepare the contingency pack",
        )
        self.assertIn(model, {"openai", "claude"})
        variant = router.choose_variant(
            model,
            "vendor failure and supplier collapse during delivery",
            "prepare the contingency pack",
        )
        self.assertIsNotNone(variant)
        self.assertIn(variant, available_model_variants(model))
        self.assertNotEqual(variant, "provider-default")

    def test_multi_vendor_task_prefers_deeper_provider(self) -> None:
        router = ModelRouter()
        model = router.choose_model(
            "multi-vendor crisis with cascading dependency failure",
            "prepare the recovery decision tree",
        )
        self.assertIn(model, {"openai", "claude"})
        variant = router.choose_variant(
            model,
            "multi-vendor crisis with cascading dependency failure",
            "prepare the recovery decision tree",
        )
        self.assertIsNotNone(variant)
        self.assertIn(variant, available_model_variants(model))
        self.assertNotEqual(variant, "provider-default")

    def test_supply_chain_task_prefers_deeper_provider(self) -> None:
        router = ModelRouter()
        model = router.choose_model(
            "supply chain failure with logistics breakdown and inventory shortages",
            "prepare the continuity pack",
        )
        self.assertIn(model, {"openai", "claude"})
        variant = router.choose_variant(
            model,
            "supply chain failure with logistics breakdown and inventory shortages",
            "prepare the continuity pack",
        )
        self.assertIsNotNone(variant)
        self.assertIn(variant, available_model_variants(model))
        self.assertNotEqual(variant, "provider-default")

    def test_regulatory_war_room_prefers_deeper_provider(self) -> None:
        router = ModelRouter()
        model = router.choose_model(
            "regulatory war room with breach, vendor outage, and legal hold",
            "prepare the board recovery tree",
        )
        self.assertIn(model, {"openai", "claude"})
        variant = router.choose_variant(
            model,
            "regulatory war room with breach, vendor outage, and legal hold",
            "prepare the board recovery tree",
        )
        self.assertIsNotNone(variant)
        self.assertIn(variant, available_model_variants(model))
        self.assertNotEqual(variant, "provider-default")

    def test_board_crisis_prefers_deeper_provider(self) -> None:
        router = ModelRouter()
        model = router.choose_model(
            "board crisis with quorum failure and supplier outage",
            "prepare the executive recovery packet",
        )
        self.assertIn(model, {"openai", "claude"})
        variant = router.choose_variant(
            model,
            "board crisis with quorum failure and supplier outage",
            "prepare the executive recovery packet",
        )
        self.assertIsNotNone(variant)
        self.assertIn(variant, available_model_variants(model))
        self.assertNotEqual(variant, "provider-default")

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
        claude_fast = router.choose_variant("claude", "list files", "inspect workspace")
        claude_deep = router.choose_variant("claude", "debug a complex traceback in production", "implement fix")
        claude_plan = router.choose_variant("claude", "design architecture roadmap", "planner stage")
        openai_fast = router.choose_variant("openai", "list files", "inspect workspace")
        openai_deep = router.choose_variant("openai", "debug a complex traceback in production", "implement fix")
        chatgpt_fast = router.choose_variant("chatgpt", "list files", "inspect workspace")
        chatgpt_deep = router.choose_variant("chatgpt", "debug a complex traceback in production", "implement fix")

        self.assertIn(claude_fast, available_model_variants("claude"))
        self.assertIn(claude_deep, available_model_variants("claude"))
        self.assertIn(claude_plan, available_model_variants("claude"))
        self.assertIn(openai_fast, available_model_variants("openai"))
        self.assertIn(openai_deep, available_model_variants("openai"))
        self.assertIn(chatgpt_fast, available_model_variants("chatgpt"))
        self.assertIn(chatgpt_deep, available_model_variants("chatgpt"))
        self.assertNotEqual(claude_fast, "provider-default")
        self.assertNotEqual(openai_fast, "provider-default")
        self.assertNotEqual(chatgpt_fast, "provider-default")

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
