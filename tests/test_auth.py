from __future__ import annotations

import os
import unittest

from stagewarden.auth import BrowserCallbackFlow, OpenAIDeviceCodeFlow


class BrowserAuthFlowTests(unittest.TestCase):
    def test_browser_flow_renders_manual_completion_page(self) -> None:
        flow = BrowserCallbackFlow(model="openai", account="lavoro", timeout_seconds=5)
        page = flow._render_launch_page()
        self.assertIn("Stagewarden browser login", page)
        self.assertIn('action="/complete"', page)
        self.assertIn("Open provider login page", page)
        self.assertIn(flow.state, page)

    def test_browser_flow_accepts_manual_token_params(self) -> None:
        flow = BrowserCallbackFlow(model="openai", account="lavoro", timeout_seconds=5)
        ok, _body, status = flow._consume_params({"state": [flow.state], "token": ["manual-browser-token"]})
        self.assertTrue(ok)
        self.assertEqual(status, 200)
        self.assertTrue(flow._result.ok)
        self.assertEqual(flow._result.token, "manual-browser-token")
        self.assertEqual(flow._result.message, "Browser flow completed.")

    def test_openai_device_code_flow_uses_mock_endpoints(self) -> None:
        original_client = os.environ.get("STAGEWARDEN_OPENAI_CLIENT_ID")
        original_issuer = os.environ.get("STAGEWARDEN_OPENAI_ISSUER")
        original_browser = os.environ.get("STAGEWARDEN_SKIP_BROWSER")
        os.environ["STAGEWARDEN_OPENAI_CLIENT_ID"] = "client-id"
        os.environ["STAGEWARDEN_OPENAI_ISSUER"] = "https://issuer.example"
        os.environ["STAGEWARDEN_SKIP_BROWSER"] = "1"
        flow = OpenAIDeviceCodeFlow(model="openai", account="lavoro", timeout_seconds=5)
        calls: list[tuple[str, dict[str, object]]] = []

        def fake_post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
            calls.append((url, payload))
            if url.endswith("/api/accounts/deviceauth/usercode"):
                return {"device_auth_id": "device-auth-123", "user_code": "CODE-12345", "interval": "0"}
            if url.endswith("/api/accounts/deviceauth/token"):
                return {
                    "authorization_code": "auth-code-321",
                    "code_challenge": "challenge-321",
                    "code_verifier": "verifier-321",
                }
            if url.endswith("/oauth/token"):
                return {
                    "access_token": "access-token-123",
                    "refresh_token": "refresh-token-123",
                    "id_token": "id-token-123",
                }
            raise AssertionError(url)

        original_post = flow._post_json
        flow._post_json = fake_post_json  # type: ignore[method-assign]
        try:
            result = flow.run()
        finally:
            flow._post_json = original_post  # type: ignore[method-assign]
            if original_client is None:
                os.environ.pop("STAGEWARDEN_OPENAI_CLIENT_ID", None)
            else:
                os.environ["STAGEWARDEN_OPENAI_CLIENT_ID"] = original_client
            if original_issuer is None:
                os.environ.pop("STAGEWARDEN_OPENAI_ISSUER", None)
            else:
                os.environ["STAGEWARDEN_OPENAI_ISSUER"] = original_issuer
            if original_browser is None:
                os.environ.pop("STAGEWARDEN_SKIP_BROWSER", None)
            else:
                os.environ["STAGEWARDEN_SKIP_BROWSER"] = original_browser

        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.token, "access-token-123")
        self.assertIn('"refresh_token":"refresh-token-123"', result.secret_payload)
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
