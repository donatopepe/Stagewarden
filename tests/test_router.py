from __future__ import annotations

import unittest

from stagewarden.router import ModelRouter


class RouterTests(unittest.TestCase):
    def test_simple_task_prefers_local(self) -> None:
        router = ModelRouter()
        self.assertEqual(router.choose_model("list files", "inspect workspace"), "local")

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
        self.assertEqual(router.choose_model("x", "y", failure_count=2), "chatgpt")
        self.assertEqual(router.choose_model("x", "y", failure_count=3), "claude")
        self.assertEqual(router.escalate("chatgpt"), "openai")
        self.assertEqual(router.escalate("openai"), "claude")
        self.assertEqual(router.fallback_for_api_failure("chatgpt"), "cheap")
        self.assertEqual(router.fallback_for_api_failure("openai"), "chatgpt")


if __name__ == "__main__":
    unittest.main()
