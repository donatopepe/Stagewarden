#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stagewarden.model_catalog import CATALOG_OUTPUT_PATH, build_ai_models_catalog, write_ai_models_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Stagewarden AI model catalog.")
    parser.add_argument(
        "--output",
        type=Path,
        default=CATALOG_OUTPUT_PATH,
        help="Output JSON path. Defaults to data/ai_models_catalog.json.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the generated catalog to stdout instead of writing a file.",
    )
    args = parser.parse_args()

    if args.stdout:
        catalog = build_ai_models_catalog()
        print(json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=True))
        return 0

    write_ai_models_catalog(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
