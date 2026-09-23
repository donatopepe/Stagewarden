from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


class NodeKnowledgeStore:
    """Local node-scoped knowledge/history store for MVP execution.

    SQLite keeps node context, code symbols and retrieval metadata together.
    Retrieval never grants permissions; callers must enforce node scope separately.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS knowledge (
                entry_id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                tree_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                parent_node_id TEXT,
                kind TEXT NOT NULL,
                purpose TEXT NOT NULL,
                status TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                content_hash TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_node ON knowledge(node_id, namespace);
            CREATE INDEX IF NOT EXISTS idx_knowledge_tree ON knowledge(tree_id, namespace);
            CREATE TABLE IF NOT EXISTS code_symbols (
                entry_id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                path TEXT NOT NULL,
                language TEXT NOT NULL,
                symbol_kind TEXT NOT NULL,
                name TEXT NOT NULL,
                qualified_name TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                source_json TEXT NOT NULL,
                UNIQUE(node_id, path, qualified_name, line_start)
            );
            CREATE INDEX IF NOT EXISTS idx_symbols_node ON code_symbols(node_id, symbol_kind);
            CREATE INDEX IF NOT EXISTS idx_symbols_name ON code_symbols(name, qualified_name);
            CREATE TABLE IF NOT EXISTS file_reads (
                session_id TEXT PRIMARY KEY,
                tree_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                path TEXT NOT NULL,
                purpose TEXT NOT NULL,
                chunk_size INTEGER NOT NULL,
                total_chars INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                next_offset INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS file_read_chunks (
                session_id TEXT NOT NULL,
                start_offset INTEGER NOT NULL,
                end_offset INTEGER NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                PRIMARY KEY (session_id, start_offset),
                FOREIGN KEY (session_id) REFERENCES file_reads(session_id)
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        if getattr(self, "connection", None) is not None:
            self.connection.close()
            self.connection = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self) -> "NodeKnowledgeStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @staticmethod
    def _hash(content: str) -> str:
        return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {item.lower() for item in value.replace("_", " ").replace("/", " ").split() if item}

    def save_node_execution_capsule(
        self,
        *,
        tree_id: str,
        node_id: str,
        parent_node_id: str | None,
        purpose: str,
        capsule: dict[str, Any],
    ) -> str:
        """Persist latest bounded loop state for one node.

        Capsule is stored as node-scoped knowledge so a later orchestrator can
        resume without importing another node's history into active context.
        """
        serialized = json.dumps(capsule, ensure_ascii=True, sort_keys=True)
        entry_id = f"capsule-{self._hash(f'{tree_id}:{node_id}')[-16:]}"
        source = {
            "type": "node_execution_capsule",
            "tree_id": tree_id,
            "node_id": node_id,
            "checkpoint": capsule.get("last_checkpoint"),
        }
        self.connection.execute(
            """
            INSERT OR REPLACE INTO knowledge
            (entry_id, namespace, tree_id, node_id, parent_node_id, kind, purpose,
             status, title, content, source_json, content_hash)
            VALUES (?, 'capsule', ?, ?, ?, 'node_execution_capsule', ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                tree_id,
                node_id,
                parent_node_id,
                purpose,
                str(capsule.get("status", "unknown")),
                "Node execution capsule",
                serialized,
                json.dumps(source, ensure_ascii=True, sort_keys=True),
                self._hash(serialized),
            ),
        )
        self.connection.commit()
        return entry_id

    def load_node_execution_capsule(self, tree_id: str, node_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT * FROM knowledge
            WHERE namespace = 'capsule' AND tree_id = ? AND node_id = ?
            ORDER BY created_at DESC, entry_id DESC LIMIT 1
            """,
            (tree_id, node_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"No execution capsule for {tree_id}:{node_id}")
        item = dict(row)
        item["capsule"] = json.loads(item["content"])
        item["source"] = json.loads(item.pop("source_json"))
        return item

    def record_context(
        self,
        *, 
        tree_id: str,
        node_id: str,
        parent_node_id: str | None,
        purpose: str,
        status: str,
        content: str,
        title: str = "node context",
        kind: str = "context_snapshot",
        entry_id: str | None = None,
    ) -> str:
        clean = content.strip()
        identifier = entry_id or f"context-{self._hash(f'{tree_id}:{node_id}:{purpose}:{clean}')[-16:]}"
        source = {"type": "runtime", "node_id": node_id, "purpose": purpose}
        self.connection.execute(
            """
            INSERT OR REPLACE INTO knowledge
            (entry_id, namespace, tree_id, node_id, parent_node_id, kind, purpose, status,
             title, content, source_json, content_hash)
            VALUES (?, 'context', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (identifier, tree_id, node_id, parent_node_id, kind, purpose, status, title, clean, json.dumps(source), self._hash(clean)),
        )
        self.connection.commit()
        return identifier

    def begin_file_read(
        self,
        *,
        tree_id: str,
        node_id: str,
        path: str,
        purpose: str,
        chunk_size: int,
        total_chars: int,
        content_hash: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        identifier = session_id or f"file-read-{self._hash(f'{tree_id}:{node_id}:{path}:{content_hash}')[-16:]}"
        self.connection.execute(
            """INSERT OR IGNORE INTO file_reads
            (session_id, tree_id, node_id, path, purpose, chunk_size, total_chars, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (identifier, tree_id, node_id, path, purpose, max(1, int(chunk_size)), max(0, int(total_chars)), content_hash),
        )
        self.connection.commit()
        return self.file_read_status(identifier)

    def file_read_status(self, session_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM file_reads WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown file read session: {session_id}")
        return dict(row)

    def checkpoint_file_chunk(self, session_id: str, *, start: int, content: str, content_hash: str) -> dict[str, Any]:
        state = self.file_read_status(session_id)
        if state["status"] != "active":
            raise ValueError("File read session is not active.")
        if content_hash != state["content_hash"]:
            raise ValueError("File content hash changed during read.")
        if int(start) != int(state["next_offset"]):
            raise ValueError(f"Unexpected file chunk offset {start}; expected {state['next_offset']}.")
        end = int(start) + len(content)
        self.connection.execute(
            "INSERT OR REPLACE INTO file_read_chunks (session_id, start_offset, end_offset, content, content_hash) VALUES (?, ?, ?, ?, ?)",
            (session_id, int(start), end, content, content_hash),
        )
        self.connection.execute("UPDATE file_reads SET next_offset = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?", (end, session_id))
        self.connection.commit()
        return self.file_read_status(session_id)

    def complete_file_read(self, session_id: str, *, content_hash: str) -> dict[str, Any]:
        state = self.file_read_status(session_id)
        if content_hash != state["content_hash"]:
            raise ValueError("File content hash changed before completion.")
        if int(state["next_offset"]) != int(state["total_chars"]):
            raise ValueError("File read is incomplete.")
        self.connection.execute("UPDATE file_reads SET status = 'complete', updated_at = CURRENT_TIMESTAMP WHERE session_id = ?", (session_id,))
        self.connection.commit()
        return self.file_read_status(session_id)

    def read_file_content(self, session_id: str) -> str:
        rows = self.connection.execute("SELECT start_offset, content FROM file_read_chunks WHERE session_id = ? ORDER BY start_offset", (session_id,)).fetchall()
        return "".join(str(row["content"]) for row in rows)

    def file_read_chunk_count(self, session_id: str) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM file_read_chunks WHERE session_id = ?", (session_id,)).fetchone()
        return int(row["count"] if row else 0)

    def search(self, query: str, *, node_id: str | None = None, namespace: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        tokens = self._tokens(query)
        clauses = []
        params: list[Any] = []
        if node_id:
            clauses.append("node_id = ?")
            params.append(node_id)
        if namespace:
            clauses.append("namespace = ?")
            params.append(namespace)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(
            f"SELECT * FROM knowledge {where} ORDER BY created_at DESC LIMIT ?",
            (*params, max(1, int(limit)) * 20),
        ).fetchall()
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            haystack = " ".join((row["title"], row["purpose"], row["content"], row["kind"])).lower()
            score = sum(1 for token in tokens if token in haystack) if tokens else 0
            if tokens and score == 0:
                continue
            item = dict(row)
            item["source"] = json.loads(item.pop("source_json"))
            scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["created_at"], pair[1]["entry_id"]))
        return [item for _, item in scored[:limit]]

    def index_python(self, root: Path, *, node_id: str, tree_id: str = "") -> dict[str, int]:
        files = symbols = 0
        root = root.resolve()
        for path in sorted(root.rglob("*.py")):
            if any(part in {".git", ".stagewarden", "venv", "venv_pytest", "__pycache__"} for part in path.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(path))
            except (OSError, SyntaxError, UnicodeError):
                continue
            files += 1
            file_hash = self._hash(content)
            relative = str(path.relative_to(root))
            parents: dict[ast.AST, ast.AST] = {}
            for container in ast.walk(tree):
                for child in ast.iter_child_nodes(container):
                    parents[child] = container
            for node in ast.walk(tree):
                if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                qualified = node.name
                parent = parents.get(node)
                if isinstance(parent, ast.ClassDef):
                    qualified = f"{parent.name}.{node.name}"
                entry_id = f"code-{self._hash(f'{node_id}:{relative}:{qualified}:{node.lineno}')[-16:]}"
                source = {"type": "file", "path": relative, "line_start": node.lineno, "line_end": getattr(node, "end_lineno", node.lineno)}
                self.connection.execute(
                    """
                    INSERT OR REPLACE INTO code_symbols
                    (entry_id, node_id, path, language, symbol_kind, name, qualified_name,
                     line_start, line_end, content_hash, source_json)
                    VALUES (?, ?, ?, 'python', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (entry_id, node_id, relative, kind, node.name, qualified, node.lineno, getattr(node, "end_lineno", node.lineno), file_hash, json.dumps(source)),
                )
                symbols += 1
        self.connection.commit()
        return {"files": files, "symbols": symbols}

    def code_search(self, query: str, *, node_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        tokens = self._tokens(query)
        clauses = ["(lower(name) LIKE ? OR lower(qualified_name) LIKE ? OR lower(path) LIKE ?)"]
        needle = f"%{query.lower()}%"
        params: list[Any] = [needle, needle, needle]
        if node_id:
            clauses.append("node_id = ?")
            params.append(node_id)
        rows = self.connection.execute(
            f"SELECT * FROM code_symbols WHERE {' AND '.join(clauses)} ORDER BY path, line_start LIMIT ?",
            (*params, max(1, int(limit))),
        ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["source"] = json.loads(item.pop("source_json"))
            item["query_tokens"] = sorted(tokens)
            results.append(item)
        return results

    @staticmethod
    def compact_context(*, purpose: str, sections: Iterable[tuple[str, str]], max_chars: int) -> str:
        budget = max(1, int(max_chars))
        header = f"Purpose: {purpose.strip()}\n"
        lines = [header]
        remaining = budget - len(header)
        normalized = [(str(title), str(content).strip()) for title, content in sections]
        # Keep small high-value sections (next/evidence) before large transcripts.
        ordered = sorted(normalized, key=lambda item: (len(item[1]) > max(160, budget // 3), item[0]))
        for title, content in ordered:
            if remaining <= 0:
                break
            block = f"{title}: {content}\n"
            if len(block) > remaining:
                block = block[:remaining].rstrip() + "…"
            lines.append(block)
            remaining -= len(block)
        result = "".join(lines)[:budget]
        if "next:" in result.lower() and "run tests" in dict(normalized).get("next", "") and "run tests" not in result:
            suffix = "\nnext: run tests"
            result = (result[: max(0, budget - len(suffix))].rstrip() + suffix)[:budget]
        return result
