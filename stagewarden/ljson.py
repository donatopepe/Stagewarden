from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8


MISSING = None
LJSON_VERSION = 1


@dataclass(slots=True)
class LJSONOptions:
    version: int = LJSON_VERSION
    numeric_keys: bool = False
    normalize_missing: bool = True
    strict_schema: bool = False
    sort_fields: bool = False


def encode(records: Sequence[dict[str, Any]], options: LJSONOptions | None = None) -> dict[str, Any]:
    opts = options or LJSONOptions()
    if not records:
        return {"_version": opts.version, "_fields": {} if opts.numeric_keys else [], "data": []}

    fields = _collect_fields(records, opts)
    if opts.numeric_keys:
        field_map = {str(index): name for index, name in enumerate(fields, start=1)}
        data = [_encode_numeric_record(record, fields, opts) for record in records]
        return {"_version": opts.version, "_fields": field_map, "data": data}

    data = [_encode_positional_record(record, fields, opts) for record in records]
    return {"_version": opts.version, "_fields": fields, "data": data}


def decode(payload: dict[str, Any]) -> list[dict[str, Any]]:
    fields_obj = payload.get("_fields")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("LJSON payload missing list 'data'.")

    if isinstance(fields_obj, list):
        fields = [str(item) for item in fields_obj]
        return [_decode_positional_record(fields, row) for row in data]

    if isinstance(fields_obj, dict):
        ordered = [fields_obj[str(index)] for index in range(1, len(fields_obj) + 1)]
        return [_decode_numeric_record(fields_obj, ordered, row) for row in data]

    raise ValueError("LJSON payload missing valid '_fields'.")


def encode_json_bytes(
    records: Sequence[dict[str, Any]],
    *,
    options: LJSONOptions | None = None,
    gzip_enabled: bool = False,
    indent: int | None = None,
) -> bytes:
    payload = encode(records, options=options)
    raw = dumps_ascii(payload, indent=indent, compact=indent is None).encode("utf-8")
    return gzip.compress(raw) if gzip_enabled else raw


def decode_json_bytes(raw: bytes, *, gzipped: bool = False) -> list[dict[str, Any]]:
    data = gzip.decompress(raw) if gzipped else raw
    return decode(loads_text(data.decode("utf-8")))


def dump_file(
    path: str | Path,
    records: Sequence[dict[str, Any]],
    *,
    options: LJSONOptions | None = None,
    gzip_enabled: bool = False,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if gzip_enabled:
        target.write_bytes(encode_json_bytes(records, options=options, gzip_enabled=True, indent=None))
    else:
        write_text_utf8(target, encode_json_bytes(records, options=options, gzip_enabled=False, indent=2).decode("utf-8"))


def load_file(path: str | Path, *, gzipped: bool | None = None) -> list[dict[str, Any]]:
    source = Path(path)
    use_gzip = gzipped if gzipped is not None else source.suffix == ".gz"
    if use_gzip:
        return decode_json_bytes(source.read_bytes(), gzipped=True)
    return decode(loads_text(read_text_utf8(source)))


def stream_encode(
    records: Iterable[dict[str, Any]],
    *,
    chunk_size: int = 100,
    options: LJSONOptions | None = None,
) -> Iterator[dict[str, Any]]:
    opts = options or LJSONOptions()
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")

    iterator = iter(records)
    buffer: list[dict[str, Any]] = []
    fields: list[str] | None = None
    chunk_index = 0

    for record in iterator:
        buffer.append(record)
        if len(buffer) == chunk_size:
            if fields is None:
                fields = _collect_fields(buffer, opts)
            chunk_index += 1
            yield _encode_chunk(buffer, fields, chunk_index, opts)
            buffer = []

    if buffer:
        if fields is None:
            fields = _collect_fields(buffer, opts)
        chunk_index += 1
        yield _encode_chunk(buffer, fields, chunk_index, opts)


def stream_decode(chunks: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for chunk in chunks:
        for item in decode(chunk):
            yield item


def benchmark_sizes(
    records: Sequence[dict[str, Any]],
    *,
    numeric_keys: bool = False,
    gzip_enabled: bool = False,
) -> dict[str, Any]:
    options = LJSONOptions(numeric_keys=numeric_keys)
    json_raw = dumps_ascii(list(records), compact=True).encode("utf-8")
    ljson_raw = encode_json_bytes(records, options=options, gzip_enabled=False)
    if gzip_enabled:
        json_size = len(gzip.compress(json_raw))
        ljson_size = len(gzip.compress(ljson_raw))
    else:
        json_size = len(json_raw)
        ljson_size = len(ljson_raw)
    reduction = 0.0 if json_size == 0 else ((json_size - ljson_size) / json_size) * 100.0
    return {
        "json_size": json_size,
        "ljson_size": ljson_size,
        "reduction_percent": round(reduction, 2),
        "numeric_keys": numeric_keys,
        "gzip": gzip_enabled,
        "record_count": len(records),
    }


def _collect_fields(records: Sequence[dict[str, Any]], options: LJSONOptions) -> list[str]:
    if not all(isinstance(record, dict) for record in records):
        raise TypeError("LJSON encode expects a sequence of dict objects.")

    first = records[0]
    fields = list(first.keys())
    seen = set(fields)

    for record in records[1:]:
        if options.strict_schema and list(record.keys()) != fields:
            raise ValueError("Record schema mismatch in strict mode.")
        for key in record.keys():
            if key not in seen:
                seen.add(key)
                fields.append(key)

    if options.sort_fields:
        fields.sort()
    return fields


def _encode_positional_record(record: dict[str, Any], fields: Sequence[str], options: LJSONOptions) -> list[Any]:
    row = []
    for field in fields:
        if field in record:
            row.append(record[field])
        elif options.normalize_missing:
            row.append(MISSING)
        else:
            raise ValueError(f"Missing field '{field}' in record.")
    return row


def _encode_numeric_record(record: dict[str, Any], fields: Sequence[str], options: LJSONOptions) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for index, field in enumerate(fields, start=1):
        if field in record:
            row[str(index)] = record[field]
        elif options.normalize_missing:
            row[str(index)] = MISSING
        else:
            raise ValueError(f"Missing field '{field}' in record.")
    return row


def _decode_positional_record(fields: Sequence[str], row: Any) -> dict[str, Any]:
    if not isinstance(row, list):
        raise ValueError("Positional LJSON rows must be arrays.")
    if len(row) > len(fields):
        raise ValueError("Positional row longer than schema.")
    return {field: row[index] if index < len(row) else MISSING for index, field in enumerate(fields)}


def _decode_numeric_record(field_map: dict[str, Any], ordered_fields: Sequence[str], row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("Numeric-key LJSON rows must be objects.")
    decoded: dict[str, Any] = {}
    for index, field in enumerate(ordered_fields, start=1):
        decoded[str(field)] = row.get(str(index), MISSING)
    if len(field_map) != len(ordered_fields):
        raise ValueError("Numeric field map inconsistent.")
    return decoded


def _encode_chunk(
    records: Sequence[dict[str, Any]],
    fields: Sequence[str],
    chunk_index: int,
    options: LJSONOptions,
) -> dict[str, Any]:
    payload = encode(
        list(records),
        options=LJSONOptions(
            version=options.version,
            numeric_keys=options.numeric_keys,
            normalize_missing=options.normalize_missing,
            strict_schema=options.strict_schema,
            sort_fields=options.sort_fields,
        ),
    )
    payload["_chunk"] = chunk_index
    payload["_chunk_size"] = len(records)
    payload["_stream"] = True
    payload["_schema_fields"] = list(fields) if isinstance(payload["_fields"], list) else dict(payload["_fields"])
    return payload
