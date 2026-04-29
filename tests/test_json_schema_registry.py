from __future__ import annotations

import unittest

from stagewarden.json_schema_registry import JSON_SCHEMA_REGISTRY, JSON_SCHEMA_VERSION, json_schema, json_schema_commands


class JsonSchemaRegistryTests(unittest.TestCase):
    def test_json_schema_registry_covers_operational_views(self) -> None:
        expected = {
            "status",
            "statusline",
            "commands",
            "slash",
            "slash choose",
            "baseline",
            "battery",
            "shell backend",
            "auth status",
            "project brief",
            "project design",
            "project tree propose",
            "project tree approve",
            "overview",
            "health",
            "preflight",
            "report",
            "handoff",
            "boundary",
            "board",
            "doctor",
            "models",
            "model limits",
            "catalog status",
            "catalog search",
            "goal",
            "goal set",
            "goal status",
            "goal clear",
            "help",
            "accounts",
            "permissions",
            "sources status",
            "sources update",
            "update status",
            "update check",
            "update apply",
            "extensions",
            "file inspect",
            "file stat",
            "file copy",
            "file move",
            "file delete",
            "file chmod",
            "file chown",
            "git status",
            "git log",
            "git history",
            "git show",
            "sessions",
            "risks",
            "issues",
            "quality",
            "exception",
            "lessons",
            "todo",
            "transcript",
            "resume --show",
            "resume context",
            "models usage",
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
