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

    def test_readers_survive_an_undecodable_journal_file(self) -> None:
        """Both readers decoded the whole file unguarded, so invalid UTF-8 bytes
        raised UnicodeDecodeError out of get() and list() -- which the CLI
        `mutations` task calls directly, crashing the command."""
        bodies = {
            "binary garbage": b"\xff\xfe\x00\x01\x80\x81 not utf-8",
            "null bytes": b"\x00\x00\x00\n",
            "not json": b"this is not json\n",
            "truncated": b'{"key": "k", ',
        }
        for label, body in bodies.items():
            with self.subTest(journal=label):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "mutations.jsonl"
                    path.write_bytes(body)
                    journal = MutationJournal(path)
                    self.assertEqual(journal.list(), [])
                    self.assertIsNone(journal.get("mutation:missing"))

    def test_readers_keep_valid_entries_alongside_undecodable_ones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mutations.jsonl"
            journal = MutationJournal(path)
            journal.append(key="mutation:one", action_type="write_file",
                           path="a.txt", status="completed", message="ok")
            with path.open("ab") as handle:
                handle.write(b"\xff\xfe not utf-8\n")
            journal.append(key="mutation:two", action_type="write_file",
                           path="b.txt", status="failed", message="nope")
            items = journal.list()
            self.assertEqual([item["key"] for item in items],
                             ["mutation:one", "mutation:two"])
            self.assertEqual(journal.get("mutation:two")["path"], "b.txt")

    def test_empty_and_missing_journals_still_return_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "mutations.jsonl"
            empty.write_bytes(b"")
            self.assertEqual(MutationJournal(empty).list(), [])
            missing = Path(tmp) / "absent.jsonl"
            self.assertEqual(MutationJournal(missing).list(), [])
            self.assertIsNone(MutationJournal(missing).get("k"))

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
