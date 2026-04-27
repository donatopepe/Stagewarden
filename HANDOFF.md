# Stagewarden Handoff Summary

## Resolved Issues & Current State

- **Test Suite Stability:** The `TypeError: dataclass() got an unexpected keyword argument 'slots'` preventing `unittest` execution has been resolved. The test suite now runs successfully.
- **Test Environment Improvements:** Enhanced `tests/conftest.py` and `bootstrap_tests.sh` for robust test setup, including correct `PYTHONPATH` export, verbose output, and disabling output capturing during test runs.
- **AI Model Catalog Bootstrap:** Added `stagewarden/model_catalog.py`, `scripts/build_ai_models_catalog.py`, and `data/ai_models_catalog.json` to normalize provider data into a shared catalog snapshot using live OpenRouter/Ollama inputs and Artificial Analysis rank metadata.
- **AI Model Catalog Integration:** `model list`, guided model selection, and `models --json` now read from the shared catalog snapshot so selection surfaces show price/rank metadata from the same source of truth.
- **AI Model Catalog Refresh Workflow:** Added `catalog status` and `catalog refresh` so the snapshot can be inspected and regenerated on demand, with an env override for the catalog path in tests or alternate environments.
- **AI Model Catalog Enrichment:** Added catalog aliases and `catalog search` so the snapshot can be queried by model id, name, aliases, or features instead of only by direct provider-model lookup.

## Ongoing Work: AI Model Catalog

- **Objective:** To create and maintain a comprehensive catalog of available AI models for Stagewarden, including their characteristics and token costs, to serve as the PRINCE2 business case.
- **Data Sources:** Information is being gathered from Ollama (local models), OpenRouter API, and Artificial Analysis.
- **Data Structure:** A detailed JSON structure has been defined for the catalog. Key fields include `provider`, `model_name`, `model_id`, `context_window`, `cost_per_input_token_usd`, `cost_per_output_token_usd`, `blended_price_usd_per_1m_tokens` (with 'local' or 'N/A' for local models), `intelligence_rank`, `speed_rank`, `latency_rank`, `openness`, and `features`.
- **Next Steps (Implementation):** The builder, selection integration, refresh workflow, and search enrichment now exist. Next, decide whether to automate periodic refreshes or widen the query/facet filters.

## PRINCE2 Alignment

- **Business Case:** Token pricing is central to the decision-making process and economic justification for model selection.
- **Product Focus:** The AI model catalog is treated as a key deliverable product.

# Operational Notes

- `~/.codex/config.toml` is used for study purposes only and is not directly leveraged by Stagewarden for model selection.

## Runtime Handoff State (.stagewarden_handoff.json) (To be updated after commit)

- **Git Head Baseline:** (will be updated after commit)
- **Plan Status:** Current task (AI Model Catalog Population) is in progress.
- **Current Step:** Considering periodic refresh automation or additional query facets. Alias/search enrichment is now complete.
- **Updated At:** 2026-04-27T16:03:12Z
