from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from .kilocode_source import (
    kilocode_provider_ids,
    kilocode_provider_info,
    kilocode_provider_model_ids,
    kilocode_provider_models,
    load_kilocode_provider_snapshot,
)
from .provider_registry import provider_model_specs


CATALOG_OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "ai_models_catalog.json"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
CATALOG_PATH_ENV = "STAGEWARDEN_AI_MODELS_CATALOG_PATH"


AA_METRICS: dict[str, dict[str, int | None]] = {
    "openai/gpt-5.4": {"intelligence_rank": 2, "speed_rank": 45, "latency_rank": None},
    "openai/gpt-5.4-mini": {"intelligence_rank": 32, "speed_rank": 4, "latency_rank": None},
    "openai/gpt-5.4-nano": {"intelligence_rank": 13, "speed_rank": 3, "latency_rank": None},
    "openai/gpt-5.3-codex": {"intelligence_rank": 3, "speed_rank": 54, "latency_rank": None},
    "openai/gpt-5.2-codex": {"intelligence_rank": 13, "speed_rank": 27, "latency_rank": None},
    "openai/gpt-5.1-codex": {"intelligence_rank": 27, "speed_rank": 4, "latency_rank": None},
    "openai/gpt-5.1-codex-mini": {"intelligence_rank": 13, "speed_rank": 10, "latency_rank": None},
    "anthropic/claude-sonnet-4.6": {"intelligence_rank": 2, "speed_rank": 38, "latency_rank": None},
    "anthropic/claude-opus-4.1": {"intelligence_rank": 11, "speed_rank": 50, "latency_rank": None},
    "anthropic/claude-haiku-4.5": {"intelligence_rank": 19, "speed_rank": 15, "latency_rank": None},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _catalog_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    override = os.environ.get(CATALOG_PATH_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return CATALOG_OUTPUT_PATH


def catalog_path(path: str | Path | None = None) -> Path:
    return _catalog_path(path)


def _safe_float(value: object) -> float | None:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return None if number < 0 else number


def _blended_price_usd_per_1m_tokens(input_price: float | None, output_price: float | None) -> float | None:
    if input_price is None or output_price is None:
        return None
    blended = ((Decimal(str(input_price)) * 3) + Decimal(str(output_price))) / Decimal("4") * Decimal("1000000")
    return float(blended.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _catalog_features_from_openrouter(model: dict[str, Any]) -> list[str]:
    features: set[str] = set()
    architecture = model.get("architecture")
    if isinstance(architecture, dict):
        for modality in architecture.get("input_modalities", []) or []:
            features.add(str(modality))
        for modality in architecture.get("output_modalities", []) or []:
            features.add(f"output:{modality}")
    for parameter in model.get("supported_parameters", []) or []:
        param = str(parameter)
        if param in {"tools", "tool_choice"}:
            features.add("tool_use")
        elif param in {"structured_outputs", "response_format"}:
            features.add("structured_output")
        elif param == "reasoning":
            features.add("reasoning")
        elif param == "seed":
            features.add("seed")
        elif param == "max_tokens" or param == "max_completion_tokens":
            continue
        else:
            features.add(param)
    return sorted(features)


def _catalog_features_from_local(spec: Any) -> list[str]:
    features: set[str] = {"text"}
    hint = str(getattr(spec, "context_window_hint", "") or "")
    if "tool" in hint.lower():
        features.add("tool_use")
    if "vision" in hint.lower():
        features.add("image")
    if "sql" in hint.lower():
        features.add("sql")
    if "coder" in str(getattr(spec, "id", "")).lower():
        features.add("coding")
    return sorted(features)


def _catalog_aliases(provider: str, provider_model_id: str, model_name: str, source_model_id: str | None) -> list[str]:
    aliases = {
        provider_model_id,
        model_name,
        model_name.lower(),
        provider_model_id.lower(),
    }
    if source_model_id:
        aliases.add(source_model_id)
        aliases.add(source_model_id.lower())
    if provider in {"openai", "chatgpt", "claude"}:
        aliases.add(f"{provider}:{provider_model_id}")
        aliases.add(f"{provider}/{provider_model_id}")
    if provider == "cheap" and source_model_id:
        aliases.add(source_model_id.replace("/", ":"))
    if provider == "local":
        aliases.add(provider_model_id.split(":", 1)[0])
    aliases.discard("")
    return sorted(aliases)


def _catalog_features_from_kilocode_model(model: dict[str, Any]) -> list[str]:
    features: set[str] = set()
    modalities = model.get("modalities", {})
    if isinstance(modalities, dict):
        for modality in modalities.get("input", []) or []:
            features.add(str(modality))
        for modality in modalities.get("output", []) or []:
            features.add(f"output:{modality}")
    if model.get("reasoning"):
        features.add("reasoning")
    if model.get("tool_call"):
        features.add("tool_use")
    if model.get("attachment"):
        features.add("attachment")
    if model.get("temperature"):
        features.add("temperature")
    if model.get("open_weights"):
        features.add("open_weights")
    if model.get("structured_output"):
        features.add("structured_output")
    interleaved = model.get("interleaved")
    if isinstance(interleaved, dict):
        field = str(interleaved.get("field", "")).strip()
        if field:
            features.add(f"interleaved:{field}")
    return sorted(features)


def _snapshot_entry_from_provider_model(provider: str, model_id: str, model: dict[str, Any]) -> dict[str, Any]:
    model_name = str(model.get("name", model_id))
    limit = model.get("limit", {}) if isinstance(model.get("limit"), dict) else {}
    cost = model.get("cost", {}) if isinstance(model.get("cost"), dict) else {}
    input_price = _safe_float(cost.get("input"))
    output_price = _safe_float(cost.get("output"))
    blended: float | str | None
    if provider == "local":
        blended = "local"
        input_price = None
        output_price = None
    elif input_price is not None and output_price is not None:
        blended = _blended_price_usd_per_1m_tokens(input_price, output_price)
    else:
        blended = None
    context_window = None
    if isinstance(limit.get("context"), (int, float)):
        context_window = int(limit["context"])
    aliases = _catalog_aliases(provider, model_id, model_name, f"{provider}:{model_id}")
    if model_id not in aliases:
        aliases.append(model_id)
    return {
        "provider": provider,
        "model_name": model_name,
        "model_id": model_id,
        "context_window": context_window,
        "cost_per_input_token_usd": input_price,
        "cost_per_output_token_usd": output_price,
        "blended_price_usd_per_1m_tokens": blended,
        "intelligence_rank": model.get("preferredIndex"),
        "speed_rank": None,
        "latency_rank": None,
        "openness": "open_weights" if model.get("open_weights") else "proprietary",
        "features": _catalog_features_from_kilocode_model(model),
        "source": f"{provider}:{model_id}",
        "aliases": aliases,
    }


def _snapshot_catalog_entries() -> list[dict[str, Any]]:
    snapshot = load_kilocode_provider_snapshot()
    entries: list[dict[str, Any]] = []
    for provider in kilocode_provider_ids():
        models = kilocode_provider_models(provider)
        for model_id in kilocode_provider_model_ids(provider):
            model = models.get(model_id)
            if not model:
                continue
            entries.append(_snapshot_entry_from_provider_model(provider, model_id, model))
    return entries


def _catalog_source_provider(provider: str) -> str | None:
    if provider in kilocode_provider_ids():
        return provider
    if provider == "cheap":
        return "openrouter"
    if provider == "chatgpt":
        return "openai"
    return None


def _catalog_entry_for_provider_spec(
    provider: str,
    spec: Any,
    openrouter_models: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if str(getattr(spec, "id", "")).strip() == "provider-default":
        return _entry_from_spec(provider, spec, openrouter_models)
    source_provider = _catalog_source_provider(provider)
    if source_provider:
        model = kilocode_provider_models(source_provider).get(str(getattr(spec, "id", "")))
        if model is not None:
            return _snapshot_entry_from_provider_model(provider, str(getattr(spec, "id", "")), model)
    return _entry_from_spec(provider, spec, openrouter_models)


def _openrouter_model_index(urlopen_fn=urlopen) -> dict[str, dict[str, Any]]:
    try:
        with urlopen_fn(OPENROUTER_MODELS_URL, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    models = payload.get("data", [])
    if not isinstance(models, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for item in models:
        if isinstance(item, dict) and str(item.get("id", "")).strip():
            index[str(item["id"])] = item
    return index


def _provider_source_model_id(provider: str, provider_model_id: str) -> str | None:
    if provider in {"openai", "chatgpt"}:
        return f"openai/{provider_model_id}"
    if provider == "claude":
        if provider_model_id == "provider-default":
            return None
        return f"anthropic/{provider_model_id}"
    if provider == "cheap":
        return provider_model_id if "/" in provider_model_id else None
    return None


def _model_name(provider: str, provider_model_id: str, source_model: dict[str, Any] | None) -> str:
    if source_model and isinstance(source_model.get("name"), str):
        return str(source_model["name"]).replace("OpenAI: ", "").replace("Anthropic: ", "")
    if provider == "local":
        return provider_model_id
    if provider_model_id == "provider-default":
        return "Provider default"
    return provider_model_id


def _context_window(provider: str, provider_model_id: str, source_model: dict[str, Any] | None, spec: Any) -> int | None:
    if source_model and isinstance(source_model.get("context_length"), int):
        return int(source_model["context_length"])
    if provider_model_id == "provider-default":
        return None
    if provider == "local":
        return None
    context_hint = getattr(spec, "context_window_hint", "")
    if context_hint == "medium":
        return 400_000
    return None


def _openness(provider: str, source_model: dict[str, Any] | None) -> str:
    if provider == "local":
        return "self_hosted"
    if provider in {"cheap", "chatgpt", "openai", "claude"}:
        return "proprietary"
    return "unknown"


def _entry_from_spec(provider: str, spec: Any, openrouter_models: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source_model_id = _provider_source_model_id(provider, str(getattr(spec, "id", "")))
    source_model = openrouter_models.get(source_model_id) if source_model_id else None
    input_price = _safe_float((source_model or {}).get("pricing", {}).get("prompt")) if source_model else None
    output_price = _safe_float((source_model or {}).get("pricing", {}).get("completion")) if source_model else None
    metrics = AA_METRICS.get(source_model_id or "", {})
    if provider == "local":
        input_price = None
        output_price = None
    entry = {
        "provider": provider,
        "model_name": _model_name(provider, str(getattr(spec, "id", "")), source_model),
        "model_id": str(getattr(spec, "id", "")),
        "context_window": _context_window(provider, str(getattr(spec, "id", "")), source_model, spec),
        "cost_per_input_token_usd": input_price,
        "cost_per_output_token_usd": output_price,
        "blended_price_usd_per_1m_tokens": _blended_price_usd_per_1m_tokens(input_price, output_price),
        "intelligence_rank": metrics.get("intelligence_rank"),
        "speed_rank": metrics.get("speed_rank"),
        "latency_rank": metrics.get("latency_rank"),
        "openness": _openness(provider, source_model),
        "features": _catalog_features_from_local(spec) if provider == "local" else _catalog_features_from_openrouter(source_model) if source_model else [],
        "source": source_model_id or f"{provider}:{getattr(spec, 'id', '')}",
        "aliases": _catalog_aliases(provider, str(getattr(spec, "id", "")), _model_name(provider, str(getattr(spec, "id", "")), source_model), source_model_id),
    }
    if provider == "local":
        entry["blended_price_usd_per_1m_tokens"] = "local"
    if provider == "cheap" and source_model is None:
        entry["openness"] = "proprietary"
    if str(getattr(spec, "id", "")) == "provider-default":
        entry["features"] = []
    return entry


def build_ai_models_catalog(
    *,
    openrouter_models: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    index = openrouter_models if openrouter_models is not None else _openrouter_model_index()
    models: list[dict[str, Any]] = []
    for provider in ("local", "cheap", "chatgpt", "openai", "claude"):
        for spec in provider_model_specs(provider):
            models.append(_entry_from_spec(provider, spec, index))
    return {
        "generated_at": _utc_now(),
        "source_urls": {
            "openrouter_models": OPENROUTER_MODELS_URL,
            "artificial_analysis": "https://artificialanalysis.ai/leaderboards/models",
        },
        "models": models,
    }


def write_ai_models_catalog(path: str | Path = CATALOG_OUTPUT_PATH) -> dict[str, Any]:
    catalog = build_ai_models_catalog()
    output_path = _catalog_path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    return catalog


def load_ai_models_catalog(path: str | Path = CATALOG_OUTPUT_PATH) -> dict[str, Any]:
    catalog_path = _catalog_path(path)
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def catalog_entries_for_provider(provider: str, catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = catalog if catalog is not None else load_ai_models_catalog()
    models = data.get("models", []) if isinstance(data, dict) else []
    if not isinstance(models, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in models:
        if isinstance(item, dict) and str(item.get("provider", "")).strip() == provider:
            entries.append(item)
    return entries


def catalog_entry_for_provider_model(
    provider: str,
    provider_model: str,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    for item in catalog_entries_for_provider(provider, catalog):
        if str(item.get("model_id", "")).strip() == provider_model:
            return item
    return None


def search_ai_models_catalog(
    query: str,
    *,
    provider: str | None = None,
    feature: str | None = None,
    catalog: dict[str, Any] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    needle = str(query or "").strip().lower()
    provider_filter = str(provider or "").strip().lower() or None
    feature_filter = str(feature or "").strip().lower() or None
    if not needle and not provider_filter and not feature_filter:
        return []
    data = catalog if catalog is not None else load_ai_models_catalog()
    models = data.get("models", []) if isinstance(data, dict) else []
    if not isinstance(models, list):
        return []
    matches: list[tuple[int, dict[str, Any]]] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        if provider_filter and str(item.get("provider", "")).strip().lower() != provider_filter:
            continue
        if feature_filter:
            features = item.get("features", [])
            if not isinstance(features, list) or not any(feature_filter in str(value).lower() for value in features):
                continue
        if needle:
            haystack = " ".join(
                str(value).lower()
                for value in (
                    item.get("provider", ""),
                    item.get("model_id", ""),
                    item.get("model_name", ""),
                    " ".join(item.get("features", [])) if isinstance(item.get("features"), list) else "",
                    " ".join(item.get("aliases", [])) if isinstance(item.get("aliases"), list) else "",
                )
            )
            if needle not in haystack:
                continue
        score = 0
        if needle and str(item.get("model_id", "")).lower() == needle:
            score -= 100
        if needle and str(item.get("model_name", "")).lower() == needle:
            score -= 75
        aliases = item.get("aliases", [])
        if needle and isinstance(aliases, list) and needle in {str(alias).lower() for alias in aliases}:
            score -= 50
        if needle and needle in str(item.get("provider", "")).lower():
            score -= 10
        score += len(str(item.get("model_id", "")))
        matches.append((score, item))
    return [item for _, item in sorted(matches, key=lambda pair: (pair[0], str(pair[1].get("provider", "")), str(pair[1].get("model_id", ""))))[: max(1, limit)]]
