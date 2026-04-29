from __future__ import annotations

import unittest

from stagewarden.json_schema_registry import JSON_SCHEMA_REGISTRY, JSON_SCHEMA_VERSION, json_schema, json_schema_commands


class JsonSchemaRegistryTests(unittest.TestCase):
    def test_json_schema_registry_covers_operational_views(self) -> None:
        expected = {
            "status",
            "statusline",
            "overview",
            "health",
            "preflight",
            "report",
            "handoff",
            "boundary",
            "board",
        }
        self.assertEqual(set(json_schema_commands()), expected)
        self.assertEqual(set(JSON_SCHEMA_REGISTRY), expected)

    def test_json_schema_registry_uses_shared_version(self) -> None:
        for command in json_schema_commands():
            payload = json_schema(command)
            self.assertEqual(payload["name"], JSON_SCHEMA_REGISTRY[command])
            self.assertEqual(payload["version"], JSON_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
