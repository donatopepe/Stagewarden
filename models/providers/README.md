# Provider model metadata

`providers/` contains provider metadata and model records. `index.json` is a manifest; each provider file is a generated snapshot.

These files are not secrets, authorization, or user selection. They may be stale and must expose source/freshness when consumed by runtime.

The v3 provider contract requires:

- exact provider and model ID;
- explicit alias/route resolution;
- context window, input limit and output limit when known;
- measurement/source/timestamp/staleness;
- capability and parameter metadata;
- no credentials.

Runtime must fail closed or request a user decision when metadata is missing or contradictory. See [`../../docs/specs/stagewarden-v3.md`](../../docs/specs/stagewarden-v3.md).

Legacy regeneration:

```bash
python3 scripts/generate_provider_model_tree.py
```
