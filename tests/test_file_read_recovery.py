from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from stagewarden.node_knowledge import NodeKnowledgeStore


class FileReadRecoveryTests(unittest.TestCase):
    def test_file_read_checkpoint_survives_reopen_and_reconstructs_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "knowledge.sqlite"
            content = "alpha\nbeta\ngamma\n"
            digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
            with NodeKnowledgeStore(path) as store:
                session = store.begin_file_read(
                    tree_id="tree-1",
                    node_id="node-1",
                    path="large.txt",
                    purpose="read complete source",
                    chunk_size=6,
                    total_chars=len(content),
                    content_hash=digest,
                )
                store.checkpoint_file_chunk(session["session_id"], start=0, content=content[:6], content_hash=digest)
                self.assertEqual(store.file_read_status(session["session_id"])["next_offset"], 6)

            with NodeKnowledgeStore(path) as resumed:
                status = resumed.file_read_status(session["session_id"])
                self.assertEqual(status["next_offset"], 6)
                resumed.checkpoint_file_chunk(session["session_id"], start=6, content=content[6:], content_hash=digest)
                resumed.complete_file_read(session["session_id"], content_hash=digest)
                final = resumed.file_read_status(session["session_id"])
                self.assertEqual(final["status"], "complete")
                self.assertEqual(resumed.read_file_content(session["session_id"]), content)

    def test_pause_resume_checkpoint_safety_matrix_file_checkpoint_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "knowledge.sqlite"
            content = "alpha\nbeta\n"
            digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
            with NodeKnowledgeStore(path) as store:
                session = store.begin_file_read(tree_id="tree", node_id="node", path="source.txt", purpose="resume", chunk_size=6, total_chars=len(content), content_hash=digest)
                store.checkpoint_file_chunk(session["session_id"], start=0, content=content[:6], content_hash=digest)
            with NodeKnowledgeStore(path) as resumed:
                self.assertEqual(resumed.file_read_status(session["session_id"])["next_offset"], 6)
                resumed.checkpoint_file_chunk(session["session_id"], start=6, content=content[6:], content_hash=digest)
                resumed.complete_file_read(session["session_id"], content_hash=digest)
                self.assertEqual(resumed.read_file_content(session["session_id"]), content)

    def test_checkpoint_rejects_wrong_offset_or_changed_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "knowledge.sqlite"
            digest = "sha256:" + hashlib.sha256(b"abc").hexdigest()
            with NodeKnowledgeStore(path) as store:
                session = store.begin_file_read(
                    tree_id="tree-1", node_id="node-1", path="x", purpose="read", chunk_size=3,
                    total_chars=3, content_hash=digest,
                )
                store.checkpoint_file_chunk(session["session_id"], start=0, content="abc", content_hash=digest)
                with self.assertRaises(ValueError):
                    store.checkpoint_file_chunk(session["session_id"], start=1, content="x", content_hash=digest)
                with self.assertRaises(ValueError):
                    store.checkpoint_file_chunk(session["session_id"], start=3, content="x", content_hash="sha256:changed")


if __name__ == "__main__":
    unittest.main()
