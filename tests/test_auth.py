from __future__ import annotations

import unittest

from stagewarden.auth import BrowserCallbackFlow


class BrowserAuthFlowTests(unittest.TestCase):
    def test_browser_flow_renders_manual_completion_page(self) -> None:
        flow = BrowserCallbackFlow(model="gpt", account="lavoro", timeout_seconds=5)
        page = flow._render_launch_page()
        self.assertIn("Stagewarden browser login", page)
        self.assertIn('action="/complete"', page)
        self.assertIn("Open provider login page", page)
        self.assertIn(flow.state, page)

    def test_browser_flow_accepts_manual_token_params(self) -> None:
        flow = BrowserCallbackFlow(model="gpt", account="lavoro", timeout_seconds=5)
        ok, _body, status = flow._consume_params({"state": [flow.state], "token": ["manual-browser-token"]})
        self.assertTrue(ok)
        self.assertEqual(status, 200)
        self.assertTrue(flow._result.ok)
        self.assertEqual(flow._result.token, "manual-browser-token")
        self.assertEqual(flow._result.message, "Browser flow completed.")


if __name__ == "__main__":
    unittest.main()
