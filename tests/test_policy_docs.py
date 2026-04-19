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


if __name__ == "__main__":
    unittest.main()
