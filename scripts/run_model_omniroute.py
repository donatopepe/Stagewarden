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
MODEL_MAP = {
    "local": DEFAULT_MODEL,
    "cheap": DEFAULT_MODEL,
    "openai": DEFAULT_MODEL,
    "chatgpt": DEFAULT_MODEL,
    "claude": DEFAULT_MODEL,
}


def main() -> int:
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: run_model_omniroute.py <provider> <prompt>"}))
        return 2
    provider, prompt = sys.argv[1], sys.argv[2]
    requested = os.environ.get("STAGEWARDEN_PROVIDER_MODEL") or MODEL_MAP.get(provider, DEFAULT_MODEL)
    models = tuple(dict.fromkeys((requested, *FREE_FALLBACKS)))
    errors: list[dict[str, str]] = []
    for model in models:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": int(os.environ.get("STAGEWARDEN_OMNIROUTE_MAX_TOKENS", "4096")),
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
            print(content)
            return 0
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"model": model, "error": str(exc)})
    print(json.dumps({"error": "all free OmniRoute routes failed", "provider": provider, "attempts": errors}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
