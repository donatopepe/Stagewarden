# Provider model catalog

One JSON file per provider. `index.json` is manifest. Generated from `data/ai_models_catalog.json` by:

```bash
./scripts/generate_provider_model_tree.py
```

No credentials in files.

Runtime loader validates `index.json`, each provider file, provider IDs, filenames, and record counts. Valid tree takes precedence; malformed/missing tree falls back to `data/ai_models_catalog.json`. Override path with `STAGEWARDEN_PROVIDER_MODELS_PATH`.
