from __future__ import annotations

import json
from pathlib import Path

from stagewarden.ljson import benchmark_sizes


def build_dataset(size: int = 500) -> list[dict[str, object]]:
    return [
        {
            "id": index,
            "name": f"user-{index}",
            "active": index % 2 == 0,
            "role": "admin" if index % 7 == 0 else "member",
            "meta": {"region": "eu", "score": index % 13},
            "note": None if index % 5 == 0 else f"note-{index}",
        }
        for index in range(size)
    ]


def main() -> None:
    dataset = build_dataset()
    results = {
        "standard": benchmark_sizes(dataset),
        "numeric": benchmark_sizes(dataset, numeric_keys=True),
        "standard_gzip": benchmark_sizes(dataset, gzip_enabled=True),
        "numeric_gzip": benchmark_sizes(dataset, numeric_keys=True, gzip_enabled=True),
    }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
