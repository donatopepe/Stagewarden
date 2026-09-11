#!/usr/bin/env python3
"""Generate models/providers/*.json from Stagewarden model catalog."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data" / "ai_models_catalog.json"
DEFAULT_OUTPUT = ROOT / "models" / "providers"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def generate(source: Path = DEFAULT_SOURCE, output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    catalog = _read_json(source)
    records = catalog.get("models")
    if not isinstance(records, list):
        raise ValueError("catalog requires a models list")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("catalog models must contain JSON objects")
        provider = str(record.get("provider", "")).strip()
        if not provider or "/" in provider or "\\" in provider or provider in {".", ".."}:
            raise ValueError(f"invalid provider ID: {provider!r}")
        grouped[provider].append(record)

    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.json"):
        if stale.name != "index.json" and stale.stem not in grouped:
            stale.unlink()
    provider_rows: list[dict[str, Any]] = []
    for provider, provider_records in sorted(grouped.items()):
        path = output / f"{provider}.json"
        payload = {
            "_format": "stagewarden_provider_models",
            "_version": 1,
            "provider": provider,
            "source": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
            "generated_at": catalog.get("generated_at", ""),
            "models": provider_records,
        }
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        provider_rows.append({"id": provider, "file": path.name, "model_count": len(provider_records)})

    manifest = {
        "_format": "stagewarden_provider_model_manifest",
        "_version": 1,
        "source": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
        "generated_at": catalog.get("generated_at", ""),
        "provider_directory": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
        "providers": provider_rows,
        "model_count": len(records),
    }
    (output / "index.json").write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        manifest = generate(args.source.resolve(), args.output.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True, indent=2))
        return 1
    print(json.dumps({"ok": True, **manifest}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
