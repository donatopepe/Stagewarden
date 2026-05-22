from __future__ import annotations

from ..config import AgentConfig
from ..model_catalog import catalog_entry_for_provider_model, load_ai_models_catalog
from .. import model_views as _model_views
from ..provider_registry import SUPPORTED_MODELS
from ..modelprefs import provider_model_specs


def _catalog_power_score(entry: dict[str, object] | None) -> float | None:
    if not isinstance(entry, dict) or not entry:
        return None
    intelligence = entry.get("intelligence_rank")
    if isinstance(intelligence, (int, float)):
        return float(intelligence)
    speed = entry.get("speed_rank")
    if isinstance(speed, (int, float)):
        return float(speed)
    return None


def _node_local_fallback_candidates(node: dict[str, object]) -> list[dict[str, object]]:
    pools = node.get("assignment_pool", {}) if isinstance(node.get("assignment_pool"), dict) else {}
    routes = pools.get("fallback", []) if isinstance(pools.get("fallback"), list) else []
    local_routes = [dict(item) for item in routes if isinstance(item, dict) and item.get("provider") == "local"]
    local_routes.sort(key=lambda item: str(item.get("provider_model", "")))
    return local_routes


def _catalog_option_suffix(entry: dict[str, object] | None) -> str:
    if not isinstance(entry, dict) or not entry:
        return ""
    parts: list[str] = []
    if entry.get("context_window"):
        parts.append(f"context={entry['context_window']}")
    if entry.get("pricing_source"):
        parts.append(f"pricing={entry['pricing_source']}")
    if entry.get("availability"):
        parts.append(f"availability={entry['availability']}")
    if not parts:
        return ""
    return " [" + "; ".join(str(item) for item in parts) + "]"


def _node_model_recommendation(config: AgentConfig, node: dict[str, object]) -> dict[str, object]:
    prefs = _model_views._load_model_preferences(config)
    catalog = load_ai_models_catalog()
    assignment = node.get("assignment") if isinstance(node.get("assignment"), dict) else {}
    current_provider = str(assignment.get("provider", "")).strip()
    current_provider_model = str(assignment.get("provider_model", "")).strip()
    current_entry = catalog_entry_for_provider_model(current_provider, current_provider_model, catalog) if current_provider and current_provider_model else None
    current_score = _catalog_power_score(current_entry)
    current_label = "current assignment"
    if current_provider and current_provider_model:
        current_label = f"{current_provider}:{current_provider_model}"

    candidates: list[dict[str, object]] = []
    for provider in prefs.enabled_models or list(SUPPORTED_MODELS):
        for spec in provider_model_specs(provider):
            if spec.id == "provider-default":
                continue
            entry = catalog_entry_for_provider_model(provider, spec.id, catalog)
            score = _catalog_power_score(entry)
            if current_provider and current_provider_model and provider == current_provider and spec.id == current_provider_model:
                continue
            bucket = "peer"
            delta = None
            if current_score is not None and score is not None:
                delta = round(current_score - score, 3)
                if delta > 0:
                    bucket = "stronger"
                elif delta < 0:
                    bucket = "lighter"
            candidates.append(
                {
                    "provider": provider,
                    "provider_model": spec.id,
                    "label": f"{provider} / {spec.id} | {spec.label}{_catalog_option_suffix(entry)}",
                    "score": score,
                    "delta": delta,
                    "bucket": bucket,
                }
            )

    stronger = [item for item in candidates if item["bucket"] == "stronger"]
    lighter = [item for item in candidates if item["bucket"] == "lighter"]
    peers = [item for item in candidates if item["bucket"] == "peer"]

    stronger.sort(key=lambda item: (float(item["score"]) if isinstance(item.get("score"), (int, float)) else 999.0, str(item["provider"]), str(item["provider_model"])))
    lighter.sort(key=lambda item: (-(float(item["score"]) if isinstance(item.get("score"), (int, float)) else 0.0), str(item["provider"]), str(item["provider_model"])))
    peers.sort(key=lambda item: (str(item["provider"]), str(item["provider_model"])))

    try:
        node_margin = float(node.get("tolerance_margin_percent", 25.0) or 25.0)
    except (TypeError, ValueError):
        node_margin = 25.0
    try:
        node_pressure = float(node.get("tolerance_pressure_percent", 0.0) or 0.0)
    except (TypeError, ValueError):
        node_pressure = 0.0
    state = str(node.get("state", "")).strip().lower() or "idle"
    tolerance_state = str(node.get("tolerance_state") or state)
    direction = "hold"
    if tolerance_state == "escalated" or node_pressure > node_margin:
        direction = "stronger"
    elif node_pressure < node_margin * 0.5:
        direction = "lighter"

    suggested = None
    if direction == "stronger" and stronger:
        suggested = stronger[0]
    elif direction == "lighter" and lighter:
        suggested = lighter[0]
    elif current_provider and current_provider_model:
        suggested = {
            "provider": current_provider,
            "provider_model": current_provider_model,
            "label": current_label,
            "score": current_score,
            "delta": 0.0,
            "bucket": "current",
        }
    elif stronger:
        suggested = stronger[0]
    elif peers:
        suggested = peers[0]

    return {
        "current": {
            "provider": current_provider or None,
            "provider_model": current_provider_model or None,
            "label": current_label,
            "score": current_score,
        },
        "direction": direction,
        "suggested": suggested,
        "stronger": stronger[:6],
        "lighter": lighter[:6],
        "peers": peers[:8],
    }
