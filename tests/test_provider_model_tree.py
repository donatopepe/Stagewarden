from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_provider_model_tree.py"


class ProviderModelTreeTests(unittest.TestCase):
    def test_checked_in_tree_is_valid_and_conserves_catalog_records(self) -> None:
        source = json.loads((ROOT / "data" / "ai_models_catalog.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / "models/providers/index.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["model_count"], len(source["models"]))
        self.assertEqual({item["id"] for item in manifest["providers"]}, {"chatgpt", "cheap", "claude", "local", "openai"})
        rows = []
        for provider in manifest["providers"]:
            path = ROOT / "models/providers" / provider["file"]
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["provider"], provider["id"])
            self.assertEqual(len(payload["models"]), provider["model_count"])
            rows.extend(payload["models"])
        self.assertEqual(len(rows), len(source["models"]))
        self.assertEqual(sorted((item["provider"], item["model_id"]) for item in rows), sorted((item["provider"], item["model_id"]) for item in source["models"]))

    def test_generator_rebuilds_tree_in_temp_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "models/providers"
            completed = subprocess.run(
                [sys.executable, str(GENERATOR), "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertTrue(report["ok"])
            self.assertEqual(report["model_count"], 238)
            self.assertEqual(len(list(output.glob("*.json"))), 6)

    def test_tree_contains_no_secret_fields(self) -> None:
        forbidden = {"api_key", "apikey", "token", "password", "secret", "private_key", "credentials"}
        for path in (ROOT / "models/providers").glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            serialized = json.dumps(payload).lower()
            self.assertTrue(forbidden.isdisjoint(serialized.split('"')), path)


if __name__ == "__main__":
    unittest.main()
