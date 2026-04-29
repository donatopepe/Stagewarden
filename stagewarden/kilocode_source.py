from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


KILOCODE_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[1]
    / "external_sources"
    / "kilocode"
    / "packages"
    / "opencode"
    / "src"
    / "provider"
    / "models-snapshot.ts"
)


@lru_cache(maxsize=1)
def load_kilocode_provider_snapshot() -> dict[str, Any]:
    try:
        text = KILOCODE_SNAPSHOT_PATH.read_text(encoding="utf-8")
    except OSError:
        return {}
    marker = "export const snapshot = "
    try:
        start = text.index(marker) + len(marker)
    except ValueError:
        return {}
    try:
        payload = json.loads(text[start:])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def kilocode_provider_ids() -> tuple[str, ...]:
    snapshot = load_kilocode_provider_snapshot()
    return tuple(snapshot.keys())


def kilocode_provider_info(provider_id: str) -> dict[str, Any] | None:
    snapshot = load_kilocode_provider_snapshot()
    info = snapshot.get(provider_id)
    return dict(info) if isinstance(info, dict) else None


def kilocode_provider_models(provider_id: str) -> dict[str, dict[str, Any]]:
    info = kilocode_provider_info(provider_id)
    if not info:
        return {}
    models = info.get("models", {})
    if not isinstance(models, dict):
        return {}
    return {
        str(model_id): dict(model_info)
        for model_id, model_info in models.items()
        if isinstance(model_info, dict)
    }


def kilocode_provider_model_ids(provider_id: str) -> tuple[str, ...]:
    models = kilocode_provider_models(provider_id)
    preferred = sorted(
        models.items(),
        key=lambda item: (
            999_999 if item[1].get("preferredIndex") is None else int(item[1].get("preferredIndex", 999_999)),
            str(item[0]),
        ),
    )
    return tuple(model_id for model_id, _ in preferred)
