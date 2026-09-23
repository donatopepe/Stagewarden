# LJSON utility

LJSON is a compact JSON representation for arrays of homogeneous objects. It is a storage/transport utility, not a work orchestration model.

## v3 role

LJSON may serialize event streams, evidence indexes, benchmark fixtures, and export/import bundles when schema stability makes it useful. It must not replace the node/event/knowledge contracts, and it must not hide provenance or redactability.

Every LJSON artifact used by Stagewarden must retain:

- schema/version;
- tree/node/work/event identifiers when applicable;
- timestamps and source;
- sensitivity/redaction state;
- enough metadata for replay or rejection.

## Supported API

- `encode(records, options=None)`
- `decode(payload)`
- `encode_json_bytes(records, gzip_enabled=False)`
- `decode_json_bytes(raw, gzipped=False)`
- `dump_file(path, records, ...)`
- `load_file(path, ...)`
- `stream_encode(records, chunk_size=100)`
- `stream_decode(chunks)`
- `benchmark_sizes(records, numeric_keys=False, gzip_enabled=False)`

## Properties and limits

- `decode(encode(x)) == x` for supported record arrays;
- missing fields normalize to `null`;
- field order is preserved;
- complexity is linear in record count;
- nested JSON values remain values;
- compression helps stable, repeated schemas;
- LJSON reduces key redundancy, not semantic content;
- streaming chunks are valid chunks, not one implicit transaction.

## Legacy CLI

```bash
stagewarden --ljson-encode records.json
stagewarden --ljson-decode records.ljson
stagewarden --ljson-benchmark records.json
```

These commands belong to the legacy runtime. The canonical v3 plan is [`TODO.md`](TODO.md).
