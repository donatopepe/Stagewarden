from __future__ import annotations

from .json_schema_registry import json_schema
from .model_catalog import catalog_path, load_ai_models_catalog, search_ai_models_catalog


def _catalog_usage() -> str:
    return "Usage: catalog status | catalog refresh [--aa] | catalog search <query> [provider=<provider>] [feature=<feature>]"


def _parse_catalog_refresh_flags(parts: list[str]) -> bool:
    include_artificial_analysis = False
    for token in parts:
        if token == "--aa":
            include_artificial_analysis = True
            continue
        raise ValueError(_catalog_usage())
    return include_artificial_analysis


def _catalog_status_report_from_catalog(catalog: dict[str, object]) -> dict[str, object]:
    models = catalog.get("models", []) if isinstance(catalog, dict) else []
    model_count = len(models) if isinstance(models, list) else 0
    return {
        "command": "catalog status",
        "schema": json_schema("catalog status"),
        "ok": bool(catalog),
        "path": str(catalog_path()),
        "generated_at": catalog.get("generated_at") if isinstance(catalog, dict) else None,
        "model_count": model_count,
        "source_urls": catalog.get("source_urls", {}) if isinstance(catalog, dict) else {},
    }


def _catalog_status_report() -> dict[str, object]:
    return _catalog_status_report_from_catalog(load_ai_models_catalog())


def _catalog_search_report_from_catalog(
    query: str,
    catalog: dict[str, object],
    provider: str | None = None,
    *,
    feature: str | None = None,
    limit: int = 10,
) -> dict[str, object]:
    results = search_ai_models_catalog(query, provider=provider, feature=feature, catalog=catalog, limit=limit)
    return {
        "command": "catalog search",
        "schema": json_schema("catalog search"),
        "query": query,
        "provider": provider,
        "feature": feature,
        "path": str(catalog_path()),
        "model_count": len(catalog.get("models", [])) if isinstance(catalog, dict) and isinstance(catalog.get("models", []), list) else 0,
        "results": results,
    }


def _catalog_search_report(query: str, provider: str | None = None, *, feature: str | None = None, limit: int = 10) -> dict[str, object]:
    return _catalog_search_report_from_catalog(query, load_ai_models_catalog(), provider=provider, feature=feature, limit=limit)


def _catalog_refresh_report_from_catalog(catalog: dict[str, object]) -> dict[str, object]:
    return {
        "command": "catalog refresh",
        "schema": json_schema("catalog refresh"),
        "ok": True,
        "include_artificial_analysis": bool(catalog.get("include_artificial_analysis", False)),
        "pricing_source": "artificial_analysis" if bool(catalog.get("include_artificial_analysis", False)) else "openrouter",
        "path": str(catalog_path()),
        "generated_at": catalog.get("generated_at"),
        "model_count": len(catalog.get("models", [])) if isinstance(catalog.get("models", []), list) else 0,
        "source_urls": catalog.get("source_urls", {}),
    }


def _catalog_refresh_report(catalog: dict[str, object]) -> dict[str, object]:
    return _catalog_refresh_report_from_catalog(catalog)


def _model_usage() -> str:
    return (
        "Usage: model use <name> | model choose [name] | model add <name> | model list <name> | model inspect <provider> [provider_model] | "
        "model params <name> | model variant <name> <variant> | model variant-clear <name> | "
        "model preset <name> <fast|balanced|deep|plan> | "
        "model param set <name> <key> <value> | model param clear <name> <key> | "
        "model remove <name> | model block <name> until YYYY-MM-DDTHH:MM | "
        "model unblock <name> | model limits | model limit-record <name> <message> | "
        "model limit-clear <name> | model clear | catalog status | catalog refresh [--aa] | catalog search <query> [provider=<provider>] [feature=<feature>]"
    )
