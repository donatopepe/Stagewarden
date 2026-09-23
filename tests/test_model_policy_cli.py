from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig
from stagewarden.model_views import _handle_model_command
from stagewarden import status_views


class ModelPolicyCliTests(unittest.TestCase):
    def test_policy_show_and_update_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AgentConfig(workspace_root=root, enforce_git=False, auto_git_commit=False)
            agent = Agent(config)
            self.assertIn("selection_mode=manual", _handle_model_command("model policy", agent, config) or "")
            result = _handle_model_command("model policy fallback on", agent, config)
            self.assertIn("allow_provider_fallback=True", result or "")
            self.assertIn("allow_provider_fallback=True", _handle_model_command("model policy", agent, config) or "")
            self.assertTrue(agent.router.status()["allow_provider_fallback"])
            self.assertFalse(agent.router.status()["allow_paid_provider"])
            self.assertEqual(
                status_views._model_status_report(agent, config)["models"][0]["provider_model_selection"],
                "manual-provider-default",
            )
            agent.close()

    def test_invalid_policy_command_does_not_change_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AgentConfig(workspace_root=root, enforce_git=False, auto_git_commit=False)
            agent = Agent(config)
            result = _handle_model_command("model policy paid maybe", agent, config)
            self.assertIn("Usage:", result or "")
            self.assertIn("allow_paid_provider=False", _handle_model_command("model policy", agent, config) or "")
            limits = status_views._model_limits_report(agent, config)
            self.assertEqual(limits["selection_policy"]["selection_mode"], "manual")
            self.assertEqual(agent.router.status()["selection_mode"], "manual")
            self.assertFalse(agent.router.status()["allow_provider_fallback"])
            self.assertFalse(agent.router.status()["allow_paid_provider"])
            agent.close()


if __name__ == "__main__":
    unittest.main()
