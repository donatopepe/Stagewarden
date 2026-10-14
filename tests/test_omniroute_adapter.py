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
    def test_free_model_detection_rejects_incidental_free_substrings(self) -> None:
        accepted = (
            "provider/model:free",
            "auto/best-free",
            "coding-free-fallback",
        )
        rejected = (
            "provider/model-not-free",
            "provider/freebie/model",
            "provider/free/model",
            "provider/not-free/model",
            "provider/model:free-ish",
        )
        for model in accepted:
            with self.subTest(model=model):
                self.assertTrue(run_model_omniroute.is_explicitly_free_model(model))
        for model in rejected:
            with self.subTest(model=model):
                self.assertFalse(run_model_omniroute.is_explicitly_free_model(model))

    def test_paid_requested_model_is_never_sent_or_used_as_fallback(self) -> None:
        attempts: list[str] = []

        def fake_urlopen(request, timeout):
            attempts.append(json.loads(request.data)["model"])
            if len(attempts) == 1:
                raise run_model_omniroute.urllib.error.URLError("try next free route")
            return _Response("safe")

        env = {
            "STAGEWARDEN_PROVIDER_MODEL": "provider/paid-model",
            "STAGEWARDEN_OMNIROUTE_FREE_MODELS": "provider/no-cost:free,provider/also:free",
        }
        with patch.object(sys, "argv", ["run_model", "cheap", "test prompt"]), patch.object(
            run_model_omniroute.urllib.request, "urlopen", side_effect=fake_urlopen
        ), patch.dict(os.environ, env):
            self.assertEqual(run_model_omniroute.main(), 0)
        self.assertEqual(attempts, ["provider/no-cost:free", "provider/also:free"])
        self.assertTrue(all(run_model_omniroute.is_explicitly_free_model(model) for model in attempts))

    def test_invalid_output_token_limit_fails_before_http(self) -> None:
        attempted = False

        def unexpected_urlopen(request, timeout):
            nonlocal attempted
            attempted = True
            raise AssertionError("invalid output cap must block network call")

        for value in ("0", "-3", "nan", "many", "4096.0", "", "   ", "131073"):   
            with self.subTest(value=value):
                with patch.object(sys, "argv", ["run_model", "cheap", "test prompt"]), patch.object(
                    run_model_omniroute.urllib.request, "urlopen", side_effect=unexpected_urlopen
                ), patch.dict(os.environ, {
                    "STAGEWARDEN_PROVIDER_MODEL": "auto/coding:free",
                    "STAGEWARDEN_OMNIROUTE_MAX_TOKENS": value,
                }):
                    self.assertEqual(run_model_omniroute.main(), 2)
        self.assertFalse(attempted)

    def test_output_token_limit_accepts_documented_upper_bound(self) -> None:
        attempts: list[dict[str, object]] = []

        def fake_urlopen(request, timeout):
            attempts.append(json.loads(request.data))
            return _Response("ok")

        with patch.object(sys, "argv", ["run_model", "cheap", "test prompt"]), patch.object(
            run_model_omniroute.urllib.request, "urlopen", side_effect=fake_urlopen
        ), patch.dict(os.environ, {
            "STAGEWARDEN_PROVIDER_MODEL": "auto/coding:free",
            "STAGEWARDEN_OMNIROUTE_MAX_TOKENS": "131072",
        }):
            self.assertEqual(run_model_omniroute.main(), 0)
        self.assertEqual(attempts[0]["max_tokens"], 131072)

    def test_output_token_limit_rejects_overflow_before_http(self) -> None:
        attempted = False

        def unexpected_urlopen(request, timeout):
            nonlocal attempted
            attempted = True
            raise AssertionError("out-of-range output cap must block HTTP")

        with patch.object(sys, "argv", ["run_model", "cheap", "test prompt"]), patch.object(
            run_model_omniroute.urllib.request, "urlopen", side_effect=unexpected_urlopen
        ), patch.dict(os.environ, {
            "STAGEWARDEN_PROVIDER_MODEL": "auto/coding:free",
            "STAGEWARDEN_OMNIROUTE_MAX_TOKENS": "131073",
        }):
            self.assertEqual(run_model_omniroute.main(), 2)
        self.assertFalse(attempted)

    def test_nonfree_routes_fail_closed_when_no_free_candidate(self) -> None:
        attempted = False

        def unexpected_urlopen(request, timeout):
            nonlocal attempted
            attempted = True
            raise AssertionError("paid model must not be sent")

        with patch.object(sys, "argv", ["run_model", "cheap", "test prompt"]), patch.object(
            run_model_omniroute.urllib.request, "urlopen", side_effect=unexpected_urlopen
        ), patch.dict(os.environ, {
            "STAGEWARDEN_PROVIDER_MODEL": "provider/paid-model",
            "STAGEWARDEN_OMNIROUTE_FREE_MODELS": "provider/standard-model",
        }):
            self.assertEqual(run_model_omniroute.main(), 1)
        self.assertFalse(attempted)

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
