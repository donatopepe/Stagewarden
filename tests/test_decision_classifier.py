from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from stagewarden.decision_classifier import (
    DecisionClassifierError,
    DecisionRequest,
    JEVApiClassifier,
    LlamaCppClassifier,
    TypeSafeSystemOneClassifier,
    classifier_from_env,
)


@pytest.fixture
def request_data() -> DecisionRequest:
    return DecisionRequest("Should this task be escalated?", ("accept", "escalate"))


def test_classifier_backend_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("STAGEWARDEN_DECISION_BACKEND", raising=False)
    assert classifier_from_env() is None


def test_backend_selection_is_explicit_and_invalid_is_rejected(monkeypatch):
    monkeypatch.setenv("STAGEWARDEN_DECISION_BACKEND", "invalid")
    with pytest.raises(DecisionClassifierError):
        classifier_from_env()


def test_api_backend_defaults_endpoint_but_requires_key(monkeypatch):
    monkeypatch.setenv("STAGEWARDEN_DECISION_BACKEND", "api")
    monkeypatch.delenv("STAGEWARDEN_JEV_API_URL", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    classifier = classifier_from_env()
    assert isinstance(classifier, TypeSafeSystemOneClassifier)
    with pytest.raises(DecisionClassifierError, match="TYPESAFE_API_KEY"):
        classifier.classify(DecisionRequest("x", ("yes", "no")))


def test_api_classifier_validates_typed_result(request_data):
    classifier = JEVApiClassifier(endpoint="https://api.typesafe.ai/v1/systemone", model="jev-latest", api_key="test-key")
    response = {"answers": {"decision": {"type": "choice", "choice": "accept",
                                             "probabilities": {"accept": 0.91, "escalate": 0.09}}}}
    with patch.object(classifier, "_post", return_value=response) as post:
        result = classifier.classify(request_data)
    assert result.label == "accept"
    assert result.backend == "api"
    assert result.confidence == pytest.approx(0.91)
    assert post.call_args.args[0]["questions"]["decision"]["type"] == "choice"
    assert post.call_args.args[0]["model"] == "jev-latest"


@pytest.mark.parametrize("payload", [
    {"answers": {"decision": {"type": "choice", "choice": "unknown",
                                 "probabilities": {"accept": 0.9, "escalate": 0.1}}}},
    {"answers": {"decision": {"type": "choice", "choice": "accept",
                                 "probabilities": {"accept": 0.7, "escalate": 0.1}}}},
    {"answers": {"decision": {"type": "score", "choice": "accept",
                                 "probabilities": {"accept": 0.9, "escalate": 0.1}}}},
    ["accept", 0.9],
])
def test_api_classifier_rejects_invalid_result(request_data, payload):
    classifier = JEVApiClassifier(endpoint="https://api.typesafe.ai/v1/systemone", model="jev-latest", api_key="key")
    with patch.object(classifier, "_post", return_value=payload):
        with pytest.raises(DecisionClassifierError):
            classifier.classify(request_data)


def test_llama_cpp_classifier_uses_jev_verdict_slot_readout(request_data):
    classifier = LlamaCppClassifier(endpoint="http://127.0.0.1:8081/v1/completions", model="jev")
    slot = {"choices": [{"logprobs": {"content": [{"top_logprobs": [
        {"token": " yes", "logprob": -0.1}, {"token": " no", "logprob": -2.1}
    ]}]}}]}
    weaker = {"choices": [{"logprobs": {"content": [{"top_logprobs": [
        {"token": " yes", "logprob": -2.0}, {"token": " no", "logprob": -0.1}
    ]}]}}]}
    with patch.object(classifier, "_post", side_effect=[slot, weaker]) as post:
        result = classifier.classify(request_data)
    assert result.label == "accept"
    assert result.backend == "llama_cpp"
    assert result.confidence > 0.5
    assert post.call_count == 2
    assert post.call_args_list[0].args[0]["max_tokens"] == 1
    assert post.call_args_list[0].args[0]["logprobs"] == 10
    assert "accept ->" in post.call_args_list[0].args[0]["prompt"]
    assert "escalate ->" in post.call_args_list[1].args[0]["prompt"]


def test_classifier_rejects_nonlocal_http_and_embedded_credentials(request_data):
    with pytest.raises(ValueError):
        LlamaCppClassifier(endpoint="http://example.com/v1/completions", model="jev")
    with pytest.raises(ValueError):
        JEVApiClassifier(endpoint="https://user:password@api.typesafe.ai/v1/systemone", model="jev")


def test_classifier_rejects_empty_input(request_data):
    classifier = LlamaCppClassifier(endpoint="http://localhost:8081/v1/completions", model="jev")
    with pytest.raises(ValueError):
        classifier.classify(DecisionRequest(" ", request_data.labels))
    with pytest.raises(ValueError):
        classifier.classify(DecisionRequest("bad\x00text", request_data.labels))


def test_llama_cpp_rejects_missing_verdict_logprobs(request_data):
    classifier = LlamaCppClassifier(endpoint="http://localhost:8081/v1/completions", model="jev")
    with patch.object(classifier, "_post", return_value={"choices": [{"text": "yes"}]}):
        with pytest.raises(DecisionClassifierError, match="log probabilities"):
            classifier.classify(request_data)


def test_classifier_selection_never_silently_falls_back(monkeypatch):
    monkeypatch.setenv("STAGEWARDEN_DECISION_BACKEND", "llama_cpp")
    monkeypatch.setenv("STAGEWARDEN_LLAMA_CPP_URL", "http://127.0.0.1:9999/v1/completions")
    classifier = classifier_from_env()
    assert isinstance(classifier, LlamaCppClassifier)
    assert classifier.backend == "llama_cpp"


def test_typesafe_requires_api_key(request_data):
    classifier = TypeSafeSystemOneClassifier(endpoint="https://api.typesafe.ai/v1/systemone", model="jev-latest")
    with pytest.raises(DecisionClassifierError, match="TYPESAFE_API_KEY"):
        classifier.classify(request_data)


def test_typesafe_system_one_wire_contract(request_data):
    classifier = TypeSafeSystemOneClassifier(endpoint="https://api.typesafe.ai/v1/systemone",
                                             model="jev-latest", api_key="test")
    wire = {"answers": {"decision": {"type": "choice", "choice": "accept",
                                        "probabilities": {"accept": .8, "escalate": .2},
                                        "confidence": .8}}}
    with patch.object(classifier, "_post", return_value=wire) as post:
        result = classifier.classify(request_data)
    body = post.call_args.args[0]
    assert result.label == "accept"
    assert body["model"] == "jev-latest"
    assert body["questions"]["decision"]["criteria"] == {"accept": "accept", "escalate": "escalate"}
    assert body["state"]["text"] == request_data.text
    assert post.call_args.args[0] == {
        "model": "jev-latest",
        "state": {"text": request_data.text},
        "questions": {"decision": {"type": "choice",
                                      "instructions": request_data.question,
                                      "criteria": {"accept": "accept", "escalate": "escalate"}}},
    }


def test_local_classifier_requires_tls_and_auth_for_remote_server():
    with pytest.raises(ValueError, match="HTTPS"):
        LlamaCppClassifier(endpoint="http://192.168.1.40:8081/v1/completions", model="jev")
    with pytest.raises(ValueError, match="API key"):
        LlamaCppClassifier(endpoint="https://decision-box.example/v1/completions", model="jev")


def test_typesafe_refuses_noncanonical_host():
    with pytest.raises(DecisionClassifierError, match="api.typesafe.ai"):
        TypeSafeSystemOneClassifier(endpoint="https://attacker.invalid/v1/systemone", model="jev-latest")
    with pytest.raises(DecisionClassifierError, match="path"):
        TypeSafeSystemOneClassifier(endpoint="https://api.typesafe.ai/v1/other", model="jev-latest")

