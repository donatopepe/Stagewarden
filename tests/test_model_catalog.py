from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stagewarden.model_catalog import build_ai_models_catalog, write_ai_models_catalog
from stagewarden.provider_registry import ProviderModelSpec


class ModelCatalogTests(unittest.TestCase):
    def test_build_ai_models_catalog_normalizes_source_data(self) -> None:
        openrouter_models = {
            "openai/gpt-5.4": {
                "id": "openai/gpt-5.4",
                "name": "OpenAI: GPT-5.4",
                "context_length": 1_050_000,
                "pricing": {"prompt": "0.0000025", "completion": "0.000015"},
                "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
                "supported_parameters": ["reasoning", "tools", "structured_outputs"],
            },
            "anthropic/claude-sonnet-4.6": {
                "id": "anthropic/claude-sonnet-4.6",
                "name": "Anthropic: Claude Sonnet 4.6",
                "context_length": 1_000_000,
                "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                "supported_parameters": ["reasoning", "tools"],
            },
        }

        def provider_specs(provider: str) -> tuple[ProviderModelSpec, ...]:
            if provider == "local":
                return (
                    ProviderModelSpec("provider-default", "Provider default", (), None, source="workspace/provider setting"),
                    ProviderModelSpec("qwen2.5-coder:7b", "Qwen2.5 Coder", ("low", "medium"), "medium", context_window_hint="size=7.6B; validate tool support before agentic use", source="dynamic Ollama discovery"),
                )
            if provider == "cheap":
                return (
                    ProviderModelSpec("provider-default", "Provider default", ("low", "medium"), "medium", source="OpenRouter provider setting"),
                    ProviderModelSpec("openai/gpt-5.4", "GPT-5.4", ("low", "medium", "high"), "medium", source="OpenRouter profile"),
                )
            if provider == "openai":
                return (
                    ProviderModelSpec("provider-default", "Provider default", ("low", "medium", "high"), "medium", source="OpenAI models docs"),
                    ProviderModelSpec("gpt-5.4", "GPT-5.4", ("low", "medium", "high"), "medium", source="OpenAI models docs"),
                )
            if provider == "chatgpt":
                return (ProviderModelSpec("provider-default", "Provider default", ("low", "medium", "high"), "medium", source="OpenAI Codex/OpenAI models docs"),)
            if provider == "claude":
                return (
                    ProviderModelSpec("provider-default", "Provider default", ("low", "medium", "high"), "medium", source="Claude Code model configuration docs"),
                    ProviderModelSpec("claude-sonnet-4.6", "Claude Sonnet 4.6", ("low", "medium", "high"), "medium", source="Claude Code model configuration docs"),
                )
            return ()

        with patch("stagewarden.model_catalog.provider_model_specs", side_effect=provider_specs):
            catalog = build_ai_models_catalog(openrouter_models=openrouter_models)

        models = {(entry["provider"], entry["model_id"]): entry for entry in catalog["models"]}

        gpt54 = models[("openai", "gpt-5.4")]
        self.assertEqual(gpt54["model_name"], "GPT-5.4")
        self.assertEqual(gpt54["context_window"], 1_050_000)
        self.assertEqual(gpt54["cost_per_input_token_usd"], 0.0000025)
        self.assertEqual(gpt54["cost_per_output_token_usd"], 0.000015)
        self.assertEqual(gpt54["blended_price_usd_per_1m_tokens"], 5.63)
        self.assertEqual(gpt54["intelligence_rank"], 2)
        self.assertIn("text", gpt54["features"])
        self.assertIn("tool_use", gpt54["features"])

        claude = models[("claude", "claude-sonnet-4.6")]
        self.assertEqual(claude["blended_price_usd_per_1m_tokens"], 6.0)
        self.assertEqual(claude["intelligence_rank"], 2)
        self.assertEqual(claude["speed_rank"], 38)

        local = models[("local", "qwen2.5-coder:7b")]
        self.assertEqual(local["blended_price_usd_per_1m_tokens"], "local")
        self.assertEqual(local["openness"], "self_hosted")
        self.assertIn("coding", local["features"])

        self.assertEqual(catalog["source_urls"]["openrouter_models"], "https://openrouter.ai/api/v1/models")

    def test_write_ai_models_catalog_emits_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "catalog.json"
            payload = {"models": [{"provider": "local", "model_id": "provider-default"}]}
            with patch("stagewarden.model_catalog.build_ai_models_catalog", return_value=payload):
                catalog = write_ai_models_catalog(output)

            self.assertEqual(catalog, payload)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written["models"][0]["provider"], "local")


if __name__ == "__main__":
    unittest.main()
