from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_model_omniroute


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps({"choices": [{"message": {"content": self.content}}]}).encode()


class _RawBodyResponse:
    """Return an arbitrary decoded JSON body, to exercise wrong-shape upstream payloads."""

    def __init__(self, body: object) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.body).encode()


class OmniRouteAdapterTests(unittest.TestCase):
    def test_wrong_shape_upstream_response_falls_back_instead_of_crashing(self) -> None:
        wrong_shapes = ([], {"choices": "not-a-list"}, {"choices": ["not-a-dict"]}, {"choices": 7})

        for body in wrong_shapes:
            with self.subTest(body=body):
                attempts: list[str] = []

                def fake_urlopen(request, timeout):
                    payload = json.loads(request.data)
                    attempts.append(payload["model"])
                    return _RawBodyResponse(body)

                with patch.object(sys, "argv", ["run_model", "--node-contract", "cheap", "test prompt"]), patch.object(
                    run_model_omniroute.urllib.request, "urlopen", side_effect=fake_urlopen
                ), patch.dict(os.environ, {"STAGEWARDEN_PROVIDER_MODEL": "auto/coding:free"}):
                    self.assertEqual(run_model_omniroute.main(), 1)
                self.assertEqual(
                    attempts,
                    ["auto/coding:free", "auto/best-free", "coding-free-fallback"],
                    f"every free route must be attempted before failing closed, got {attempts!r}",
                )

    def test_wrong_shape_upstream_response_then_recovers_on_free_fallback(self) -> None:
        attempts: list[str] = []

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data)
            attempts.append(payload["model"])
            if len(attempts) == 1:
                return _RawBodyResponse({"choices": "not-a-list"})
            return _Response(json.dumps({"summary": "recovered", "messages": []}))

        with patch.object(sys, "argv", ["run_model", "--node-contract", "cheap", "test prompt"]), patch.object(
            run_model_omniroute.urllib.request, "urlopen", side_effect=fake_urlopen
        ), patch.dict(os.environ, {"STAGEWARDEN_PROVIDER_MODEL": "auto/coding:free"}):
            self.assertEqual(run_model_omniroute.main(), 0)
        self.assertEqual(attempts[:2], ["auto/coding:free", "auto/best-free"])

    def test_node_contract_rejects_wrong_contract_and_uses_free_fallback(self) -> None:
        attempts: list[str] = []

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data)
            attempts.append(payload["model"])
            if len(attempts) == 1:
                return _Response(json.dumps({"summary": "wrong", "keyDecisions": "not allowed"}))
            return _Response(json.dumps({"summary": "valid node", "messages": [], "output": "evidence"}))

        with patch.object(sys, "argv", ["run_model", "--node-contract", "cheap", "test prompt"]), patch.object(
            run_model_omniroute.urllib.request, "urlopen", side_effect=fake_urlopen
        ), patch.dict(os.environ, {"STAGEWARDEN_PROVIDER_MODEL": "auto/coding:free"}):
            self.assertEqual(run_model_omniroute.main(), 0)
        self.assertEqual(attempts[:2], ["auto/coding:free", "auto/best-free"])

    def test_node_contract_rejects_prose_on_all_routes(self) -> None:
        attempts: list[str] = []

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data)
            attempts.append(payload["model"])
            return _Response("Sure, here is prose")

        with patch.object(sys, "argv", ["run_model", "--node-contract", "cheap", "test prompt"]), patch.object(
            run_model_omniroute.urllib.request, "urlopen", side_effect=fake_urlopen
        ), patch.dict(os.environ, {"STAGEWARDEN_PROVIDER_MODEL": "auto/coding:free"}):
            self.assertEqual(run_model_omniroute.main(), 1)
        self.assertEqual(len(attempts), 3)

    def test_adapter_uses_free_fallback_after_route_failure(self) -> None:
        attempts: list[str] = []

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data)
            attempts.append(payload["model"])
            if len(attempts) == 1:
                raise run_model_omniroute.urllib.error.URLError("route unavailable")
            return _Response("FREE_OK")

        with patch.object(sys, "argv", ["run_model", "cheap", "test prompt"]), patch.object(
            run_model_omniroute.urllib.request, "urlopen", side_effect=fake_urlopen
        ), patch.dict(os.environ, {"STAGEWARDEN_PROVIDER_MODEL": "auto/coding:free"}):
            self.assertEqual(run_model_omniroute.main(), 0)
        self.assertEqual(attempts[:2], ["auto/coding:free", "auto/best-free"])

    @unittest.skipUnless(os.environ.get("RUN_OMNIROUTE_LIVE_TEST") == "1", "set RUN_OMNIROUTE_LIVE_TEST=1")
    def test_local_free_route_live(self) -> None:
        script = Path(__file__).parents[1] / "scripts" / "test_omniroute_free.sh"
        completed = subprocess.run([str(script)], capture_output=True, text=True, timeout=300, check=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("OmniRoute free route OK", completed.stdout)


if __name__ == "__main__":
    unittest.main()
