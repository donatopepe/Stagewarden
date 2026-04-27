# External IO Help Audit

File generated from wet-run validation of `/help external_io` commands.
Base: stagewarden commands registered under `external_io` handler.

## Command List

| Command | Description | JSON |
|---------|-------------|------|
| `web search` | Run governed web search with result evidence. | Yes |
| `download` | Download HTTP/HTTPS file inside workspace with checksum evidence. | Yes |
| `checksum` | Compute SHA-256 for a workspace file. | Yes |
| `compress` | Gzip-compress one workspace file. | Yes |
| `archive verify` | Verify a gzip archive and report checksum evidence. | Yes |

## Verified Examples

### `checksum`

Input:
```
stagewarden> checksum test_checksum.txt
```

JSON output (verified):
```json
{
  "ok": true,
  "command": "checksum",
  "message": "SHA-256 computed for test_checksum.txt.",
  "path": "test_checksum.txt",
  "url": null,
  "bytes_written": 26,
  "sha256": "23e164f596833156dc6a2918009c8020d713abbc1520d6a828400545ac99382e",
  "content_type": "text/plain",
  "duration_ms": 24,
  "items": [],
  "error": null
}
```

### `compress`

Input:
```
stagewarden> compress test_checksum.txt
```

JSON output (verified):
```json
{
  "ok": true,
  "command": "compress",
  "message": "Compressed test_checksum.txt to test_checksum.txt.gz.",
  "path": "test_checksum.txt.gz",
  "url": null,
  "bytes_written": 64,
  "sha256": "4a85bd3c74f3acfa9df7e890ee4932cfe2385357dbd4ef7cc4111e9159d5f8f8",
  "content_type": "application/gzip",
  "duration_ms": 1,
  "items": [],
  "error": null
}
```

### `archive verify`

Input:
```
stagewarden> archive verify test_checksum.txt.gz
```

JSON output (verified):
```json
{
  "ok": true,
  "command": "archive verify",
  "message": "Archive verified; compressed=64 bytes uncompressed=26 bytes.",
  "path": "test_checksum.txt.gz",
  "url": null,
  "bytes_written": 64,
  "sha256": "4a85bd3c74f3acfa9df7e890ee4932cfe2385357dbd4ef7cc4111e9159d5f8f8",
  "content_type": "application/gzip",
  "duration_ms": 0,
  "items": [],
  "error": null
}
```

## Unverified Examples (Sandbox / Network)

### `web search`

Input:
```
stagewarden> web search Stagewarden coding agent
```

Note: wet-run returned `"error": "urlopen error [Errno 8] nodename nor servname provided, or not known"` due to sandbox network restrictions. Expected behavior confirmed via unit tests.

Expected JSON shape:
```json
{
  "ok": true,
  "command": "web search",
  "message": "Found N results",
  "items": [ ... ],
  "error": null
}
```

### `download`

Input:
```
stagewarden> download https://example.com/file.txt artifacts/file.txt --max-bytes 1048576
```

Note: cannot verify in sandbox. Expected JSON shape:
```json
{
  "ok": true,
  "command": "download",
  "message": "Downloaded ...",
  "path": "artifacts/file.txt",
  "sha256": "...",
  "error": null
}
```

## Validation Evidence

- `checksum` wet-run: passed (path inside workspace required)
- `compress` wet-run: passed
- `archive verify` wet-run: passed
- `web search` wet-run: blocked by sandbox network
- `download` wet-run: blocked by sandbox network

## Aliases

Help topic aliases for `external_io`: `io`, `network`, `download`.

## Related Files

- `stagewarden/commands.py` — `HelpTopic("external_io", ...)`
- `stagewarden/tools/external_io.py` — implementation
- `stagewarden/main.py` — `_handle_external_io_command`, `_external_io_execute`
