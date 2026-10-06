"""Optional decision-classifier backends; never changes primary LLM routing.

TypeSafe API follows Pi's System One contract. The local adapter follows the
Jev-Style-v3 llama.cpp verdict-slot readout documented in HermesVault. Both are
opt-in and return the same validated distribution contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    text: str
    labels: tuple[str, ...]
    context: Mapping[str, Any] | None = None
    question: str = "Choose the option best supported by the observed state."


@dataclass(frozen=True, slots=True)
class DecisionResult:
    label: str
    confidence: float
    backend: str
    model: str
    distribution: Mapping[str, float]


class DecisionClassifier(Protocol):
    backend: str

    def classify(self, request: DecisionRequest) -> DecisionResult: ...


class DecisionClassifierError(RuntimeError):
    """Configuration, transport, or model-output error."""


class DecisionClassifierUnavailable(DecisionClassifierError):
    """Backend could not be reached or returned an unsuccessful response."""


def _validate_request(request: DecisionRequest) -> None:
    if not request.text.strip():
        raise ValueError("Decision input text must not be empty.")
    if "\x00" in request.text:
        raise ValueError("Decision input must not contain NUL bytes.")
    if not request.question.strip():
        raise ValueError("Decision question must not be empty.")
    if not 2 <= len(request.labels) <= 20:
        raise ValueError("Decision requires between 2 and 20 labels.")
    if any(not label.strip() for label in request.labels) or len(set(request.labels)) != len(request.labels):
        raise ValueError("Decision labels must be non-empty and unique.")
    if len(request.text) > 32_000 or len(request.question) > 2_000:
        raise ValueError("Decision input exceeds configured size limits.")


def _distribution_result(distribution: Any, *, backend: str, model: str,
                         labels: tuple[str, ...]) -> DecisionResult:
    if not isinstance(distribution, dict) or set(distribution) != set(labels):
        raise DecisionClassifierError("Classifier must return probabilities for exactly all requested labels.")
    values: dict[str, float] = {}
    for label in labels:
        value = distribution[label]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise DecisionClassifierError("Classifier probabilities must be finite non-negative numbers.")
        values[label] = float(value)
    total = sum(values.values())
    if total <= 0 or abs(total - 1.0) > 0.02:
        raise DecisionClassifierError("Classifier probability distribution must sum to 1 (±0.02).")
    values = {label: score / total for label, score in values.items()}
    chosen = max(labels, key=lambda label: values[label])
    return DecisionResult(chosen, values[chosen], backend, model, values)


class _JsonHttpClassifier:
    backend = ""

    def __init__(self, *, endpoint: str, model: str, timeout_seconds: float = 10.0,
                 api_key: str | None = None, max_response_bytes: int = 64_000) -> None:
        parsed = urlsplit(endpoint)
        local_hosts = {"127.0.0.1", "localhost", "::1"}
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Endpoint must include host and must not embed credentials.")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in local_hosts):
            raise ValueError("Classifier endpoint must use HTTPS (HTTP allowed only for localhost).")
        if not 0 < timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be in (0, 120].")
        if not model.strip():
            raise ValueError("Classifier model must not be empty.")
        if not 256 <= max_response_bytes <= 1_000_000:
            raise ValueError("max_response_bytes must be between 256 and 1000000.")
        self.endpoint, self.model, self.timeout_seconds = endpoint, model, timeout_seconds
        self.api_key, self.max_response_bytes = api_key, max_response_bytes

    def _post(self, body: dict[str, Any]) -> Any:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(self.endpoint, data=data, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(self.max_response_bytes + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise DecisionClassifierUnavailable(f"Classifier request failed: {type(exc).__name__}") from exc
        if len(raw) > self.max_response_bytes:
            raise DecisionClassifierError("Classifier response exceeded configured size limit.")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise DecisionClassifierError("Classifier returned invalid JSON.") from exc


class TypeSafeSystemOneClassifier(_JsonHttpClassifier):
    """TypeSafe JEV using its native System One endpoint and typed choice answers."""
    backend = "api"

    def __init__(self, *, endpoint: str = "https://api.typesafe.ai/v1/systemone", model: str = "jev-latest",
                 timeout_seconds: float = 10.0, api_key: str | None = None,
                 max_response_bytes: int = 64_000) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or parsed.hostname != "api.typesafe.ai" or parsed.port not in (None, 443):
            raise DecisionClassifierError("TypeSafe JEV endpoint must use https://api.typesafe.ai.")
        if parsed.path != "/v1/systemone" or parsed.query or parsed.fragment:
            raise DecisionClassifierError("TypeSafe JEV endpoint path must be /v1/systemone without query or fragment.")
        super().__init__(endpoint=endpoint, model=model, timeout_seconds=timeout_seconds,
                         api_key=api_key, max_response_bytes=max_response_bytes)

    @classmethod
    def from_env(cls) -> "TypeSafeSystemOneClassifier":
        try:
            timeout = float(os.environ.get("STAGEWARDEN_DECISION_TIMEOUT", "10"))
        except ValueError as exc:
            raise DecisionClassifierError("STAGEWARDEN_DECISION_TIMEOUT must be numeric.") from exc
        endpoint = os.environ.get("STAGEWARDEN_JEV_API_URL", "https://api.typesafe.ai/v1/systemone")
        return cls(endpoint=endpoint, model=os.environ.get("STAGEWARDEN_JEV_MODEL", "jev-latest"),
                   api_key=os.environ.get("TYPESAFE_API_KEY"), timeout_seconds=timeout)

    def classify(self, request: DecisionRequest) -> DecisionResult:
        _validate_request(request)
        if not self.api_key:
            raise DecisionClassifierError("Set TYPESAFE_API_KEY to enable TypeSafe JEV API.")
        state = {"text": request.text}
        if request.context:
            state["context"] = dict(request.context)
        body = {
            "model": self.model,
            "state": state,
            "questions": {"decision": {"type": "choice", "instructions": request.question,
                                         "criteria": {label: label for label in request.labels}}},
        }
        response = self._post(body)
        try:
            answer = response["answers"]["decision"]
            if answer["type"] != "choice":
                raise ValueError("unexpected answer type")
            distribution = answer["probabilities"]
            choice = answer["choice"]
        except (TypeError, KeyError, ValueError) as exc:
            raise DecisionClassifierError("TypeSafe System One returned invalid choice answer.") from exc
        result = _distribution_result(distribution, backend=self.backend, model=self.model, labels=request.labels)
        if choice not in request.labels or choice != result.label:
            raise DecisionClassifierError("TypeSafe chosen option disagrees with probability argmax.")
        return result


class JEVApiClassifier(TypeSafeSystemOneClassifier):
    """Backward-compatible name for the native TypeSafe JEV API adapter."""


class LlamaCppJevStyleClassifier(_JsonHttpClassifier):
    """Local Jev-Style-v3 verdict-slot readout using llama.cpp /v1/completions."""
    backend = "llama_cpp"

    def __init__(self, *, endpoint: str = "http://127.0.0.1:8081/v1/completions", model: str = "jev",
                 timeout_seconds: float = 45.0, api_key: str | None = None,
                 max_response_bytes: int = 64_000) -> None:
        parsed = urlsplit(endpoint)
        allowed_path = parsed.path == "/v1/completions"
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("llama.cpp endpoint must use HTTP or HTTPS.")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Remote llama.cpp endpoints must use HTTPS.")
        if parsed.scheme == "https" and not api_key:
            raise ValueError("Remote llama.cpp endpoint requires API key authentication.")
        if not allowed_path or parsed.query or parsed.fragment:
            raise ValueError("JevStyle llama.cpp endpoint path must be /v1/completions.")
        super().__init__(endpoint=endpoint, model=model, timeout_seconds=timeout_seconds,
                         api_key=api_key, max_response_bytes=max_response_bytes)

    @classmethod
    def from_env(cls) -> "LlamaCppJevStyleClassifier":
        try:
            timeout = float(os.environ.get("STAGEWARDEN_DECISION_TIMEOUT", "45"))
            temperature = float(os.environ.get("STAGEWARDEN_JEV_TEMPERATURE", "0.8279"))
        except ValueError as exc:
            raise DecisionClassifierError("Decision timeout and temperature must be numeric.") from exc
        if not math.isfinite(temperature) or temperature <= 0:
            raise DecisionClassifierError("STAGEWARDEN_JEV_TEMPERATURE must be finite and positive.")
        endpoint = os.environ.get("STAGEWARDEN_LLAMA_CPP_URL", "http://127.0.0.1:8081/v1/completions")
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise DecisionClassifierError("Remote llama.cpp endpoints must use HTTPS.")
        if parsed.scheme == "https" and not os.environ.get("STAGEWARDEN_LLAMA_CPP_API_KEY"):
            raise DecisionClassifierError("Remote llama.cpp endpoint requires STAGEWARDEN_LLAMA_CPP_API_KEY.")
        return cls(endpoint=endpoint, model=os.environ.get("STAGEWARDEN_LLAMA_CPP_MODEL", "jev"),
                   api_key=os.environ.get("STAGEWARDEN_LLAMA_CPP_API_KEY"), timeout_seconds=timeout)

    @staticmethod
    def _slot_score(payload: Any) -> float:
        try:
            candidates = payload["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
        except (TypeError, KeyError, IndexError) as exc:
            raise DecisionClassifierError("llama.cpp response lacks verdict-slot log probabilities.") from exc
        verdicts: dict[str, float] = {}
        for candidate in candidates:
            token = str(candidate.get("token", "")).strip().lower()
            value = candidate.get("logprob")
            if token in {"yes", "no"} and token not in verdicts:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise DecisionClassifierError("llama.cpp returned invalid verdict log probability.")
                verdicts[token] = float(value)
        if not verdicts:
            raise DecisionClassifierError("llama.cpp returned no yes/no verdict token scores.")
        return verdicts.get("yes", -30.0) - verdicts.get("no", -30.0)

    def classify(self, request: DecisionRequest) -> DecisionResult:
        _validate_request(request)
        qtype = "noul" if len(request.labels) == 2 else "choice"
        option_lines = "\n".join(f"- {label}" for label in request.labels)
        header = (f"State:\n{request.text}\n\nQuestion [{qtype}]: {request.question}\n"
                  f"Options:\n{option_lines}\nJudge each option:\n")
        # The calibrated JevStyle v3 protocol requires one verdict slot per option.
        # Execute serially to preserve Stagewarden's serial execution contract.
        scores: list[float] = []
        for index, option in enumerate(request.labels):
            prompt = header + "".join(f"{item} ->\n" for item in request.labels[:index + 1])
            payload = self._post({"model": self.model, "prompt": prompt, "max_tokens": 1,
                                  "temperature": 0, "logprobs": 10})
            scores.append(self._slot_score(payload))
        try:
            temperature = float(os.environ.get("STAGEWARDEN_JEV_TEMPERATURE", "0.8279"))
        except ValueError as exc:
            raise DecisionClassifierError("STAGEWARDEN_JEV_TEMPERATURE must be numeric.") from exc
        if not math.isfinite(temperature) or temperature <= 0:
            raise DecisionClassifierError("STAGEWARDEN_JEV_TEMPERATURE must be finite and positive.")
        maximum = max(scores)
        exps = [math.exp((score - maximum) / temperature) for score in scores]
        total = sum(exps)
        distribution = {label: exps[index] / total for index, label in enumerate(request.labels)}
        return _distribution_result(distribution, backend=self.backend, model=self.model, labels=request.labels)


LlamaCppClassifier = LlamaCppJevStyleClassifier


def classifier_from_env() -> DecisionClassifier | None:
    """Construct only explicitly selected backend; no network on import or backend switch."""
    backend = os.environ.get("STAGEWARDEN_DECISION_BACKEND", "off").strip().lower()
    if backend in {"", "off", "disabled"}:
        return None
    if backend == "api":
        return TypeSafeSystemOneClassifier.from_env()
    if backend == "llama_cpp":
        return LlamaCppJevStyleClassifier.from_env()
    raise DecisionClassifierError("STAGEWARDEN_DECISION_BACKEND must be off, api, or llama_cpp.")
