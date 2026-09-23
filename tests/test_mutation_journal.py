from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewarden.mutation_journal import MutationJournal


class MutationJournalTests(unittest.TestCase):
    def test_key_is_stable_and_completed_entry_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = MutationJournal(Path(tmp) / "mutations.jsonl")
            action = {"path": "x.txt", "content": "hello"}
            first = journal.key("write_file", action)
            self.assertEqual(first, journal.key("write_file", dict(action)))
            self.assertIsNone(journal.get(first))
            journal.append(key=first, action_type="write_file", path="x.txt", status="completed", message="ok")
            self.assertEqual(journal.get(first)["status"], "completed")

    def test_in_flight_entry_is_visible_and_not_replayed_as_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = MutationJournal(Path(tmp) / "mutations.jsonl")
            key = journal.key("write_file", {"path": "x.txt", "content": "hello"})
            journal.append(key=key, action_type="write_file", path="x.txt", status="in_flight", message="started")
            self.assertEqual(journal.get(key)["status"], "in_flight")
            self.assertEqual(journal.list(status="in_flight")[0]["key"], key)

    def test_list_filters_status_and_preserves_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = MutationJournal(Path(tmp) / "mutations.jsonl")
            journal.append(key="1", action_type="write_file", path="a", status="failed", message="no")
            journal.append(key="2", action_type="write_file", path="b", status="completed", message="yes")
            journal.append(key="3", action_type="apply_patch", path="c", status="completed", message="yes2")
            self.assertEqual([item["key"] for item in journal.list(status="completed")], ["2", "3"])
            self.assertEqual(len(journal.list(limit=2)), 2)


if __name__ == "__main__":
    unittest.main()
