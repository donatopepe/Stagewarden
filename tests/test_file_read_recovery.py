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
                resumed.checkpoint_file_chunk(session["session_id"], start=6, content=content[6:12], content_hash=digest)
                resumed.checkpoint_file_chunk(session["session_id"], start=12, content=content[12:], content_hash=digest)
                resumed.complete_file_read(session["session_id"], content_hash=digest)
                final = resumed.file_read_status(session["session_id"])
                self.assertEqual(final["status"], "complete")
                self.assertEqual(resumed.read_file_content(session["session_id"]), content)

    def test_file_read_checkpoint_rejects_oversized_chunk_and_total_overrun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "knowledge.sqlite"
            with NodeKnowledgeStore(path) as store:
                store.begin_file_read(
                    tree_id="tree",
                    node_id="node",
                    path="source.txt",
                    purpose="read",
                    chunk_size=5,
                    total_chars=10,
                    content_hash="sha256:test",
                    session_id="session",
                )
                # 1. Exact chunk accepted.
                state = store.checkpoint_file_chunk("session", start=0, content="abcde", content_hash="sha256:test")
                self.assertEqual(state["next_offset"], 5)
                # 2. Final chunk may reach, but not exceed, total_chars.
                state = store.checkpoint_file_chunk("session", start=5, content="12345", content_hash="sha256:test")
                self.assertEqual(state["next_offset"], 10)

                store.begin_file_read(
                    tree_id="tree",
                    node_id="node",
                    path="oversized.txt",
                    purpose="read",
                    chunk_size=5,
                    total_chars=10,
                    content_hash="sha256:test",
                    session_id="oversized",
                )
                # 3. Oversized chunk cannot corrupt persisted offset.
                with self.assertRaises(ValueError):
                    store.checkpoint_file_chunk("oversized", start=0, content="abcdef", content_hash="sha256:test")
                self.assertEqual(store.file_read_status("oversized")["next_offset"], 0)

    def test_file_read_session_identity_rejects_conflicting_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "knowledge.sqlite"
            with NodeKnowledgeStore(path) as store:
                store.begin_file_read(
                    tree_id="tree",
                    node_id="node-a",
                    path="source.txt",
                    purpose="read source",
                    chunk_size=5,
                    total_chars=10,
                    content_hash="sha256:old",
                    session_id="session-1",
                )
                store.checkpoint_file_chunk("session-1", start=0, content="abcde", content_hash="sha256:old")

                # 1. Exact identity resumes persisted offset.
                resumed = store.begin_file_read(
                    tree_id="tree",
                    node_id="node-a",
                    path="source.txt",
                    purpose="read source",
                    chunk_size=5,
                    total_chars=10,
                    content_hash="sha256:old",
                    session_id="session-1",
                )
                self.assertEqual(resumed["next_offset"], 5)

                # 2. Changed source identity cannot reuse checkpoint.
                with self.assertRaises(ValueError):
                    store.begin_file_read(
                        tree_id="tree",
                        node_id="node-a",
                        path="source.txt",
                        purpose="read source",
                        chunk_size=5,
                        total_chars=10,
                        content_hash="sha256:new",
                        session_id="session-1",
                    )

                # 3. Changed node/path/metadata cannot reuse checkpoint.
                with self.assertRaises(ValueError):
                    store.begin_file_read(
                        tree_id="tree",
                        node_id="node-b",
                        path="other.txt",
                        purpose="other read",
                        chunk_size=9,
                        total_chars=99,
                        content_hash="sha256:old",
                        session_id="session-1",
                    )

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
