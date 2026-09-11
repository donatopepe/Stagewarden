# Model catalog tree

`providers/` contains one JSON file per configured provider plus `index.json` manifest.

- `providers/index.json`: provider list and total model count.
- `providers/<provider>.json`: provider metadata and model records.
- `scripts/generate_provider_model_tree.py`: regenerate tree from `data/ai_models_catalog.json`.

Current tree is generated from legacy catalog and preserves 238 records. Runtime provider precedence is intentionally still open; legacy catalog remains fallback until integration is implemented and tested.

No credentials belong in these files.
