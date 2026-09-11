from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stagewarden.model_catalog import load_ai_models_catalog, load_provider_tree_catalog
from stagewarden.provider_registry import provider_model_spec, provider_model_specs


class ProviderRuntimeTreeTests(unittest.TestCase):
    def _tree(self, root: Path, *, model_id: str = "test-model") -> Path:
        providers = root / "providers"
        providers.mkdir()
        provider_payload = {
            "_format": "stagewarden_provider_models",
            "_version": 1,
            "provider": "openai",
            "source": "test",
            "generated_at": "test",
            "models": [{
                "provider": "openai",
                "model_name": "Test model",
                "model_id": model_id,
                "context_window": 1000,
                "features": ["reasoning"],
                "aliases": [],
                "cost_per_input_token_usd": None,
                "cost_per_output_token_usd": None,
                "blended_price_usd_per_1m_tokens": None,
                "intelligence_rank": None,
                "speed_rank": None,
                "latency_rank": None,
                "openness": "proprietary",
                "pricing_source": "test",
                "source": "test",
            }],
        }
        (providers / "openai.json").write_text(json.dumps(provider_payload), encoding="utf-8")
        manifest = {
            "_format": "stagewarden_provider_model_manifest",
            "_version": 1,
            "source": "test",
            "generated_at": "test",
            "provider_directory": "providers",
            "providers": [{"id": "openai", "file": "openai.json", "model_count": 1}],
            "model_count": 1,
        }
        (providers / "index.json").write_text(json.dumps(manifest), encoding="utf-8")
        return providers

    def test_valid_tree_overrides_legacy_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree = self._tree(root)
            with patch.dict(os.environ, {"STAGEWARDEN_PROVIDER_MODELS_PATH": str(tree)}):
                catalog = load_ai_models_catalog()
                self.assertEqual(catalog["models"][0]["model_id"], "test-model")
                self.assertEqual(provider_model_spec("openai", "test-model").id, "test-model")

    def test_malformed_tree_falls_back_to_legacy_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree = self._tree(root)
            (tree / "openai.json").write_text("not json", encoding="utf-8")
            with patch.dict(os.environ, {"STAGEWARDEN_PROVIDER_MODELS_PATH": str(tree)}):
                self.assertEqual(load_provider_tree_catalog(), {})
                legacy = load_ai_models_catalog()
                self.assertGreater(len(legacy.get("models", [])), 1)

    def test_missing_tree_falls_back_and_keeps_registry_usable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"STAGEWARDEN_PROVIDER_MODELS_PATH": str(Path(tmp) / "missing")}):
                self.assertEqual(load_provider_tree_catalog(), {})
                self.assertTrue(provider_model_specs("openai"))


if __name__ == "__main__":
    unittest.main()
