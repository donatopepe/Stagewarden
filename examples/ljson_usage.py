from __future__ import annotations

import json

from agent_cli.ljson import LJSONOptions, decode, encode, stream_encode


def main() -> None:
    records = [
        {"id": 1, "name": "Mario", "active": True},
        {"id": 2, "name": "Luigi", "active": None},
    ]

    encoded = encode(records)
    numeric = encode(records, options=LJSONOptions(numeric_keys=True))
    decoded = decode(encoded)
    chunks = list(stream_encode(records, chunk_size=1))

    print("positional:")
    print(json.dumps(encoded, indent=2))
    print("numeric:")
    print(json.dumps(numeric, indent=2))
    print("decoded:")
    print(json.dumps(decoded, indent=2))
    print("chunks:")
    print(json.dumps(chunks, indent=2))


if __name__ == "__main__":
    main()
