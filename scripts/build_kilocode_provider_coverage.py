#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stagewarden.kilocode_source import kilocode_provider_ids
from stagewarden.provider_registry import SUPPORTED_MODELS, provider_capability, provider_model_specs


DATA_PATH = ROOT / "data" / "kilocode_provider_coverage.json"
DOC_PATH = ROOT / "docs" / "kilocode_provider_coverage.md"
CORE_PROVIDERS = {"local", "cheap", "chatgpt", "openai", "claude"}


def _category(provider_id: str) -> str:
    return "core" if provider_id in CORE_PROVIDERS else "snapshot"


def _runtime_class(provider_id: str) -> str:
    return "core-runtime" if provider_id in CORE_PROVIDERS else "snapshot-runtime"


def _model_ids(provider_id: str) -> list[str]:
    return [spec.id for spec in provider_model_specs(provider_id)]


def build_report() -> dict[str, object]:
    providers: list[dict[str, object]] = []
    for provider_id in SUPPORTED_MODELS:
        capability = provider_capability(provider_id)
        model_ids = _model_ids(provider_id)
        providers.append(
            {
                "provider_id": provider_id,
                "category": _category(provider_id),
                "runtime_class": _runtime_class(provider_id),
                "backend_label": capability.backend_label,
                "provider_label": capability.provider_label,
                "auth_type": capability.auth_type,
                "default_model": capability.default_model,
                "model_count": len(model_ids),
                "model_ids": model_ids,
                "source": capability.source,
                "supports_account_profiles": capability.supports_account_profiles,
                "supports_browser_login": capability.supports_browser_login,
                "supports_api_key": capability.supports_api_key,
            }
        )
    core = [item for item in providers if item["category"] == "core"]
    snapshot = [item for item in providers if item["category"] == "snapshot"]
    return {
        "snapshot_provider_count": len(kilocode_provider_ids()),
        "supported_model_count": len(SUPPORTED_MODELS),
        "core_provider_count": len(core),
        "snapshot_runtime_provider_count": len(snapshot),
        "core_providers": core,
        "snapshot_providers": snapshot,
        "providers": providers,
    }


def render_markdown(report: dict[str, object]) -> str:
    providers = [item for item in report["providers"] if isinstance(item, dict)]
    core = [item for item in providers if item.get("category") == "core"]
    snapshot = [item for item in providers if item.get("category") == "snapshot"]

    def fmt_models(items: list[str], limit: int = 6) -> str:
        if not items:
            return "none"
        if len(items) <= limit:
            return ", ".join(items)
        return ", ".join(items[:limit]) + f", ... (+{len(items) - limit} more)"

    lines = [
        "# KiloCode Provider Coverage",
        "",
        "This report maps the local KiloCode snapshot into Stagewarden runtime categories.",
        "",
        f"- Snapshot providers discovered: {report['snapshot_provider_count']}",
        f"- Stagewarden supported models: {report['supported_model_count']}",
        f"- Core runtime providers: {report['core_provider_count']}",
        f"- Snapshot-backed runtime providers: {report['snapshot_runtime_provider_count']}",
        "",
        "## Core Runtime Providers",
        "",
        "| Provider | Backend | Auth | Default model | Model count | Model ids |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in core:
        lines.append(
            f"| `{item['provider_id']}` | `{item['backend_label']}` | `{item['auth_type']}` | "
            f"`{item['default_model']}` | {item['model_count']} | {fmt_models(item['model_ids'])} |"
        )

    lines.extend(
        [
            "",
            "## Snapshot-Backed Runtime Providers",
            "",
            "These providers are first-class runtime options because Stagewarden now consumes the KiloCode snapshot directly. The full model lists live in the JSON companion file.",
            "",
            "| Provider | Backend | Auth | Default model | Model count | Runtime class |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in snapshot:
        lines.append(
            f"| `{item['provider_id']}` | `{item['backend_label']}` | `{item['auth_type']}` | "
            f"`{item['default_model']}` | {item['model_count']} | `{item['runtime_class']}` |"
        )

    lines.extend(
        [
            "",
            "## Runtime Notes",
            "",
            "- Core providers keep bespoke UX, auth, and role defaults.",
            "- Snapshot-backed providers use the generic provider registry path for routing, variants, and metadata.",
            "- Use `stagewarden model list <provider>` or `stagewarden models --json` for the live runtime view.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    report = build_report()
    DATA_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    DOC_PATH.write_text(render_markdown(report), encoding="utf-8")
    print(DATA_PATH)
    print(DOC_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
