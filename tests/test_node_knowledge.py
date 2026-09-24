from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewarden.node_knowledge import NodeKnowledgeStore


class NodeKnowledgeStoreTests(unittest.TestCase):
    def test_retrieval_scope_matrix_keeps_node_context_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with NodeKnowledgeStore(Path(tmp) / "knowledge.sqlite") as store:
                store.record_context(
                    tree_id="tree",
                    node_id="ancestor",
                    parent_node_id=None,
                    purpose="ancestor",
                    status="completed",
                    content="ancestorexclusivepayload",
                )
                store.record_context(
                    tree_id="tree",
                    node_id="child",
                    parent_node_id="ancestor",
                    purpose="child",
                    status="completed",
                    content="childexclusivepayload",
                )
                direct = store.search("ancestorexclusivepayload", node_id="ancestor")
                child = store.search("ancestorexclusivepayload", node_id="child")
                self.assertTrue(direct)
                self.assertEqual(child, [])

    def test_code_retrieval_scope_matrix_keeps_node_symbols_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ancestor_root = root / "ancestor"
            child_root = root / "child"
            ancestor_root.mkdir()
            child_root.mkdir()
            (ancestor_root / "ancestor.py").write_text("def ancestorexclusive():\n    return 1\n", encoding="utf-8")
            (child_root / "child.py").write_text("def childexclusive():\n    return 2\n", encoding="utf-8")
            with NodeKnowledgeStore(root / "knowledge.sqlite") as store:
                store.index_python(ancestor_root, node_id="ancestor", tree_id="tree")
                store.index_python(child_root, node_id="child", tree_id="tree")
                self.assertTrue(store.code_search("ancestorexclusive", node_id="ancestor"))
                self.assertEqual(store.code_search("ancestorexclusive", node_id="child"), [])

    def test_same_root_indexing_rejects_cross_node_ownership_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "src"
            root.mkdir()
            source = root / "shared.py"
            source.write_text("def ancestor_only():\n    return 1\n", encoding="utf-8")
            with NodeKnowledgeStore(Path(tmp) / "knowledge.sqlite") as store:
                first = store.index_python(root, node_id="ancestor", tree_id="tree")
                self.assertTrue(store.code_search("ancestor_only", node_id="ancestor"))

                with self.assertRaises(ValueError):
                    store.index_python(root, node_id="child", tree_id="tree")
                self.assertEqual(store.code_search("ancestor_only", node_id="child"), [])

                second = store.index_python(root, node_id="ancestor", tree_id="tree")
                self.assertEqual(second["fresh"], 1)
                self.assertEqual(second["changed"], 0)
                self.assertEqual(second["stale_removed"], 0)
                self.assertEqual(first["schema_version"], second["schema_version"])
                self.assertTrue(store.code_search("ancestor_only", node_id="ancestor"))

    def test_node_execution_capsule_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "knowledge.sqlite"
            capsule = {
                "node_id": "build.compiler",
                "parent_node_id": "build",
                "purpose": "Compile compiler module",
                "status": "running",
                "cycle_id": 2,
                "cycle_phase": "verify",
                "context_revision": 3,
                "last_checkpoint": "event-7",
                "cycle_budget": {"max_cycles": 5},
                "pending_action": "run focused tests",
            }
            with NodeKnowledgeStore(path) as store:
                entry_id = store.save_node_execution_capsule(
                    tree_id="tree-1",
                    node_id="build.compiler",
                    parent_node_id="build",
                    purpose="Compile compiler module",
                    capsule=capsule,
                )
                loaded = store.load_node_execution_capsule("tree-1", "build.compiler")
                self.assertEqual(loaded["entry_id"], entry_id)
                self.assertEqual(loaded["capsule"]["cycle_id"], 2)
                self.assertEqual(loaded["capsule"]["pending_action"], "run focused tests")

            with NodeKnowledgeStore(path) as reopened:
                loaded = reopened.load_node_execution_capsule("tree-1", "build.compiler")
                self.assertEqual(loaded["capsule"]["last_checkpoint"], "event-7")

    def test_records_node_scoped_context_and_retrieves_with_citation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = NodeKnowledgeStore(Path(tmp) / "knowledge.sqlite")
            try:
                entry_id = store.record_context(
                    tree_id="tree-1",
                    node_id="build.compiler",
                    parent_node_id="build",
                    purpose="Compile compiler module",
                    status="running",
                    content="pytest tests/test_compiler.py is required",
                )
                results = store.search("compiler pytest", node_id="build.compiler")
                self.assertEqual(results[0]["entry_id"], entry_id)
                self.assertEqual(results[0]["node_id"], "build.compiler")
                self.assertEqual(results[0]["namespace"], "context")
                self.assertEqual(results[0]["source"]["node_id"], "build.compiler")
                self.assertEqual(store.search("compiler", node_id="other"), [])
            finally:
                store.close()

    def test_indexes_python_files_classes_functions_and_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.py"
            source.write_text(
                "class Compiler:\n    def compile(self, value):\n        return helper(value)\n\ndef helper(value):\n    return value\n",
                encoding="utf-8",
            )
            store = NodeKnowledgeStore(root / "knowledge.sqlite")
            try:
                report = store.index_python(root, node_id="build.compiler")
                self.assertEqual(report["files"], 1)
                self.assertGreaterEqual(report["symbols"], 3)
                symbols = store.code_search("compile", node_id="build.compiler")
                self.assertTrue(symbols)
                self.assertEqual(symbols[0]["path"], "sample.py")
                self.assertGreater(symbols[0]["line_start"], 0)
                self.assertEqual(symbols[0]["node_id"], "build.compiler")
            finally:
                store.close()

    def test_node_knowledge_acceptance_matrix_covers_isolation_citation_index_compaction_and_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.py"
            source.write_text("class Fresh:\n    pass\n", encoding="utf-8")
            store = NodeKnowledgeStore(root / "knowledge.sqlite")
            try:
                entry_id = store.record_context(tree_id="tree", node_id="node-a", parent_node_id=None, purpose="index source", status="running", content="Fresh evidence")
                self.assertEqual(store.search("Fresh", node_id="node-b"), [])
                result = store.search("Fresh", node_id="node-a")
                self.assertEqual(result[0]["entry_id"], entry_id)
                self.assertEqual(result[0]["source"]["node_id"], "node-a")
                indexed = store.index_python(root, node_id="node-a", tree_id="tree")
                self.assertGreaterEqual(indexed["symbols"], 1)
                symbol = store.code_search("Fresh", node_id="node-a")[0]
                self.assertEqual(symbol["line_start"], 1)
                compacted = store.compact_context(purpose="index source", sections=[("next", "run tests"), ("history", "x" * 100)], max_chars=40)
                self.assertIn("Purpose: index source", compacted)
                source.write_text("class Fresh:\n    pass\n\nclass New:\n    pass\n", encoding="utf-8")
                refreshed = store.index_python(root, node_id="node-a", tree_id="tree")
                self.assertGreaterEqual(refreshed["symbols"], indexed["symbols"])
                self.assertTrue(store.code_search("New", node_id="node-a"))
            finally:
                store.close()

    def test_code_index_relations_and_freshness_matrix_has_six_fixed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.py"
            source.write_text(
                "from helper import run\n"
                "\n"
                "VALUE = 1\n"
                "\n"
                "def build(value):\n"
                "    result = run(value)\n"
                "    return result\n",
                encoding="utf-8",
            )
            store = NodeKnowledgeStore(root / "knowledge.sqlite")
            try:
                first = store.index_python(root, node_id="node-a", tree_id="tree")
                # 1. module symbol
                module_symbols = store.code_search("sample", node_id="node-a")
                self.assertTrue(module_symbols)
                self.assertEqual(module_symbols[0]["symbol_kind"], "module")
                # 2. import relation
                self.assertTrue(store.code_relations("helper.run", node_id="node-a", relation_kind="import"))
                # 3. local call relation
                self.assertTrue(store.code_relations("run", node_id="node-a", relation_kind="call"))
                # 4. source read/write relations
                self.assertTrue(store.code_relations("VALUE", node_id="node-a", relation_kind="write"))
                self.assertTrue(store.code_relations("run", node_id="node-a", relation_kind="read"))
                # 5. unchanged reindex is fresh and does not duplicate symbols
                second = store.index_python(root, node_id="node-a", tree_id="tree")
                self.assertEqual(second["fresh"], 1)
                self.assertEqual(second["changed"], 0)
                self.assertEqual(second["stale_removed"], 0)
                # 6. changed reindex increments version and removes stale symbol
                source.write_text("def changed(value):\n    return value\n", encoding="utf-8")
                third = store.index_python(root, node_id="node-a", tree_id="tree")
                self.assertEqual(third["changed"], 1)
                self.assertTrue(store.code_search("changed", node_id="node-a"))
                self.assertEqual(store.code_search("build", node_id="node-a"), [])
                version = store.connection.execute(
                    "SELECT version, freshness FROM code_files WHERE node_id = ? AND path = ?",
                    ("node-a", "sample.py"),
                ).fetchone()
                self.assertEqual((version["version"], version["freshness"]), (2, "fresh"))
                self.assertEqual(first["schema_version"], 2)
            finally:
                store.close()

    def test_compacts_context_deterministically_and_preserves_purpose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = NodeKnowledgeStore(Path(tmp) / "knowledge.sqlite")
            try:
                compacted = store.compact_context(
                    purpose="Validate API contract",
                    sections=[
                        ("task", "A" * 1000),
                        ("evidence", "B" * 1000),
                        ("next", "run tests"),
                    ],
                    max_chars=180,
                )
                self.assertLessEqual(len(compacted), 180)
                self.assertIn("Validate API contract", compacted)
                self.assertIn("run tests", compacted)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
