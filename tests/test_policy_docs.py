from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PolicyDocsTests(unittest.TestCase):
    def test_policy_artifacts_exist(self) -> None:
        self.assertTrue((ROOT / "AGENT_MANIFESTO.md").exists())
        self.assertTrue((ROOT / "AGENT_POLICY.md").exists())
        self.assertTrue((ROOT / "AGENT_POLICY.json").exists())
        self.assertTrue((ROOT / "AGENTS.md").exists())
        self.assertTrue((ROOT / "AGENT_HANDOFF.md").exists())

    def test_machine_readable_policy_has_required_fields(self) -> None:
        payload = json.loads((ROOT / "AGENT_POLICY.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["_format"], "stagewarden_agent_policy")
        self.assertEqual(payload["author"], "Donato Pepe")
        self.assertEqual(payload["framework"], "adaptive_prince2")
        self.assertIn("principles", payload)
        principle_ids = {item["id"] for item in payload["principles"]}
        self.assertIn("adaptive_governance", principle_ids)
        self.assertIn("wet_run_required", principle_ids)
        self.assertIn("traceability", principle_ids)

    def test_study_material_mentions_kilocode(self) -> None:
        source_refs = (ROOT / "docs" / "source_references.md").read_text(encoding="utf-8")
        status_research = (ROOT / "docs" / "status_research.md").read_text(encoding="utf-8")
        policy = (ROOT / "AGENT_POLICY.json").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        handoff = (ROOT / "AGENT_HANDOFF.md").read_text(encoding="utf-8")
        example_settings = (ROOT / "examples" / "stagewarden_settings.example.json").read_text(encoding="utf-8")

        self.assertIn("external_sources/kilocode", source_refs)
        self.assertIn("kilocode_provider_coverage.md", source_refs)
        self.assertIn("KiloCode", status_research)
        self.assertIn("runtime-supported", status_research)
        self.assertIn("codex_claude_kilocode_minimum_baseline", policy)
        self.assertIn("Mandatory startup protocol", agents)
        self.assertIn("Mandatory handoff protocol", agents)
        self.assertIn("Current objective", handoff)
        self.assertIn("Current state", handoff)
        self.assertIn("STAGEWARDEN_ARTIFICIAL_ANALYSIS_API_KEY", example_settings)
        self.assertIn("catalog refresh --aa", example_settings)

    def test_kilocode_provider_coverage_artifacts_exist_and_match_snapshot(self) -> None:
        coverage_json = ROOT / "data" / "kilocode_provider_coverage.json"
        coverage_md = ROOT / "docs" / "kilocode_provider_coverage.md"
        self.assertTrue(coverage_json.exists())
        self.assertTrue(coverage_md.exists())

        payload = json.loads(coverage_json.read_text(encoding="utf-8"))
        self.assertEqual(payload["snapshot_provider_count"], 115)
        self.assertEqual(payload["supported_model_count"], 119)
        self.assertEqual(payload["core_provider_count"], 5)
        self.assertEqual(payload["snapshot_runtime_provider_count"], 114)
        self.assertEqual(len(payload["providers"]), 119)
        self.assertEqual(len(payload["core_providers"]), 5)
        self.assertEqual(len(payload["snapshot_providers"]), 114)
        provider_ids = [item["provider_id"] for item in payload["providers"]]
        self.assertEqual(len(provider_ids), len(set(provider_ids)))
        self.assertIn("openai", provider_ids)
        self.assertIn("kilo", provider_ids)
        self.assertIn("github-copilot", provider_ids)


if __name__ == "__main__":
    unittest.main()
