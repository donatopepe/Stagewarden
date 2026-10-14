#!/usr/bin/env python3
"""Stagewarden model adapter for a local OpenAI-compatible OmniRoute instance.

Defaults deliberately target OmniRoute's free coding route. No external API key
is required when the service is bound to localhost with its default local key.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1").rstrip("/")
API_KEY = os.environ.get("OMNIROUTE_API_KEY", "omniroute-local")
DEFAULT_MODEL = os.environ.get("STAGEWARDEN_OMNIROUTE_MODEL", "auto/coding:free")
FREE_FALLBACKS = tuple(
    item.strip()
    for item in os.environ.get(
        "STAGEWARDEN_OMNIROUTE_FREE_MODELS",
        "auto/coding:free,auto/best-free,coding-free-fallback",
    ).split(",")
    if item.strip()
)
FREE_MODEL_MARKERS = (":free", "/free/")
DEFAULT_MAX_TOKENS = 4096
MIN_MAX_TOKENS = 1
MAX_MAX_TOKENS = 131072


def is_explicitly_free_model(model: str) -> bool:
    """Accept explicit free tiers; reject incidental words like ``not-free``."""
    normalized = model.strip().lower()
    if not normalized:
        return False
    return (
        normalized.endswith(":free")
        or "/free/" in normalized
        or normalized in {"auto/best-free", "coding-free-fallback"}
    )


def _free_model_candidates(requested: str, fallbacks: tuple[str, ...]) -> tuple[str, ...]:
    candidates = (requested, *fallbacks)
    return tuple(dict.fromkeys(model for model in candidates if is_explicitly_free_model(model)))


def _positive_int_env(name: str, default: int, *, maximum: int = MAX_MAX_TOKENS) -> int:
    raw = os.environ.get(name)
    if raw is not None and not raw.strip():
        raise ValueError(f"{name} must be a positive integer")
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value < MIN_MAX_TOKENS or value > maximum:
        raise ValueError(f"{name} must be an integer in [{MIN_MAX_TOKENS}, {maximum}]")
    return value


MODEL_MAP = {
    "local": DEFAULT_MODEL,
    "cheap": DEFAULT_MODEL,
    "openai": DEFAULT_MODEL,
    "chatgpt": DEFAULT_MODEL,
    "claude": DEFAULT_MODEL,
}


def main() -> int:
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: run_model_omniroute.py [--node-contract] <provider> <prompt>"}))
        return 2
    node_contract = sys.argv[1] == "--node-contract"
    argument_offset = 1 if node_contract else 0
    if len(sys.argv) < 3 + argument_offset:
        print(json.dumps({"error": "usage: run_model_omniroute.py [--node-contract] <provider> <prompt>"}))
        return 2
    provider, prompt = sys.argv[1 + argument_offset], sys.argv[2 + argument_offset]
    requested = os.environ.get("STAGEWARDEN_PROVIDER_MODEL") or MODEL_MAP.get(provider, DEFAULT_MODEL)
    free_fallbacks = tuple(
        item.strip()
        for item in os.environ.get(
            "STAGEWARDEN_OMNIROUTE_FREE_MODELS",
            "auto/coding:free,auto/best-free,coding-free-fallback",
        ).split(",")
        if item.strip()
    )
    models = _free_model_candidates(requested, free_fallbacks)
    if not models:
        print(json.dumps({"error": "no explicitly free OmniRoute model configured", "provider": provider}))
        return 1
    errors: list[dict[str, str]] = []
    is_critic = "devil advocate" in prompt.lower() or "project assurance critic" in prompt.lower()
    if node_contract:
        messages = [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object with only these top-level fields: "
                    "summary (non-empty string), messages (array of objects), output (string optional). "
                    "No markdown, prose, keyDecisions, taskProgress, or activeEntities."
                ),
            },
            {"role": "user", "content": prompt},
        ]
    else:
        messages = (
        [
            {"role": "system", "content": "You are a strict JSON critic. Return exactly one JSON object with top-level verdict equal to accept, revise, or block. Never repeat the primary action."},
            {"role": "user", "content": prompt},
        ]
            if is_critic
            else [{"role": "user", "content": prompt}]
        )
    try:
        max_tokens = _positive_int_env(
            "STAGEWARDEN_OMNIROUTE_MAX_TOKENS", DEFAULT_MAX_TOKENS,
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc), "provider": provider}))
        return 2
    for model in models:
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
        }).encode()
        request = urllib.request.Request(
            f"{BASE_URL}/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=float(os.environ.get("STAGEWARDEN_OMNIROUTE_TIMEOUT", "120"))) as response:
                data = json.load(response)
            content = data["choices"][0]["message"].get("content", "")
            if not content:
                raise ValueError("OmniRoute returned empty content")
            if node_contract:
                packet = json.loads(content)
                if not isinstance(packet, dict) or not isinstance(packet.get("summary"), str) or not packet["summary"].strip() or not isinstance(packet.get("messages", []), list):
                    raise ValueError("OmniRoute node contract requires non-empty summary and messages array")
                allowed = {"summary", "messages", "output"}
                unexpected = sorted(set(packet) - allowed)
                if unexpected:
                    raise ValueError(f"OmniRoute node contract has unexpected fields: {', '.join(unexpected)}")
                if not all(isinstance(item, dict) for item in packet["messages"]):
                    raise ValueError("OmniRoute node contract messages must contain objects")
                print(json.dumps(packet, ensure_ascii=True, sort_keys=True))
            else:
                print(content)
            return 0
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, AttributeError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"model": model, "error": str(exc)})
    print(json.dumps({"error": "all free OmniRoute routes failed", "provider": provider, "attempts": errors}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
