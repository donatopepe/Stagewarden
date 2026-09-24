from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

INDEX_SCHEMA_VERSION = 2


def _node_end(node: ast.AST) -> int:
    return int(getattr(node, "end_lineno", getattr(node, "lineno", 1)))


def _relative_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")



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
            CREATE TABLE IF NOT EXISTS code_index_roots (
                root_path TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                tree_id TEXT NOT NULL,
                claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
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
            CREATE TABLE IF NOT EXISTS code_files (
                node_id TEXT NOT NULL,
                path TEXT NOT NULL,
                language TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                version INTEGER NOT NULL,
                freshness TEXT NOT NULL,
                line_count INTEGER NOT NULL,
                indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (node_id, path)
            );
            CREATE TABLE IF NOT EXISTS code_relations (
                relation_id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_qualified_name TEXT NOT NULL,
                target_path TEXT,
                target_qualified_name TEXT NOT NULL,
                relation_kind TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                source_json TEXT NOT NULL,
                UNIQUE(node_id, source_path, source_qualified_name, target_path, target_qualified_name, relation_kind, line_start)
            );
            CREATE INDEX IF NOT EXISTS idx_code_relations_node ON code_relations(node_id, relation_kind);
            CREATE INDEX IF NOT EXISTS idx_code_relations_target ON code_relations(node_id, target_qualified_name);
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
        existing = self.connection.execute(
            "SELECT tree_id, node_id, path, purpose, chunk_size, total_chars, content_hash FROM file_reads WHERE session_id = ?",
            (identifier,),
        ).fetchone()
        requested = (tree_id, node_id, path, purpose, max(1, int(chunk_size)), max(0, int(total_chars)), content_hash)
        if existing is not None:
            stored = tuple(existing[key] for key in ("tree_id", "node_id", "path", "purpose", "chunk_size", "total_chars", "content_hash"))
            if stored != requested:
                raise ValueError(f"File read session identity conflict: {identifier}")
        else:
            self.connection.execute(
                """INSERT INTO file_reads
                (session_id, tree_id, node_id, path, purpose, chunk_size, total_chars, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (identifier, *requested),
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
        files = symbols = relations = fresh = changed = 0
        root = root.resolve()
        owner = self.connection.execute(
            "SELECT node_id, tree_id FROM code_index_roots WHERE root_path = ?",
            (str(root),),
        ).fetchone()
        if owner is not None and (str(owner["node_id"]) != node_id or str(owner["tree_id"]) != tree_id):
            raise ValueError(
                f"Code index root already owned by node {owner['node_id']} in tree {owner['tree_id']}: {root}"
            )
        self.connection.execute(
            "INSERT OR IGNORE INTO code_index_roots (root_path, node_id, tree_id) VALUES (?, ?, ?)",
            (str(root), node_id, tree_id),
        )
        self.connection.commit()
        seen_paths: set[str] = set()
        parsed_files: dict[str, tuple[str, ast.Module, list[str]]] = {}
        for path in sorted(root.rglob("*.py")):
            if any(part in {".git", ".stagewarden", "venv", "venv_pytest", "__pycache__"} for part in path.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(path))
            except (OSError, SyntaxError, UnicodeError):
                continue
            relative = _relative_path(path, root)
            file_hash = self._hash(content)
            seen_paths.add(relative)
            parsed_files[relative] = (file_hash, tree, content.splitlines())
            prior = self.connection.execute(
                "SELECT content_hash, version FROM code_files WHERE node_id = ? AND path = ?",
                (node_id, relative),
            ).fetchone()
            if prior is not None and str(prior["content_hash"]) == file_hash:
                fresh += 1
            elif prior is not None:
                changed += 1
            files += 1

        stale_rows = self.connection.execute(
            "SELECT path FROM code_files WHERE node_id = ?",
            (node_id,),
        ).fetchall()
        stale_paths = {str(row["path"]) for row in stale_rows} - seen_paths
        for relative in stale_paths:
            self.connection.execute("DELETE FROM code_symbols WHERE node_id = ? AND path = ?", (node_id, relative))
            self.connection.execute("DELETE FROM code_relations WHERE node_id = ? AND source_path = ?", (node_id, relative))
            self.connection.execute("DELETE FROM code_files WHERE node_id = ? AND path = ?", (node_id, relative))

        for relative, (file_hash, tree, lines) in parsed_files.items():
            prior = self.connection.execute(
                "SELECT content_hash, version FROM code_files WHERE node_id = ? AND path = ?",
                (node_id, relative),
            ).fetchone()
            version = (
                int(prior["version"])
                if prior is not None and str(prior["content_hash"]) == file_hash
                else int(prior["version"]) + 1 if prior is not None else 1
            )
            self.connection.execute(
                """
                INSERT INTO code_files (node_id, path, language, content_hash, version, freshness, line_count)
                VALUES (?, ?, 'python', ?, ?, 'fresh', ?)
                ON CONFLICT(node_id, path) DO UPDATE SET
                    content_hash=excluded.content_hash, version=excluded.version,
                    freshness='fresh', line_count=excluded.line_count, indexed_at=CURRENT_TIMESTAMP
                """,
                (node_id, relative, file_hash, version, len(lines)),
            )
            self.connection.execute("DELETE FROM code_symbols WHERE node_id = ? AND path = ?", (node_id, relative))
            self.connection.execute("DELETE FROM code_relations WHERE node_id = ? AND source_path = ?", (node_id, relative))
            parents: dict[ast.AST, ast.AST] = {}
            for container in ast.walk(tree):
                for child in ast.iter_child_nodes(container):
                    parents[child] = container
            definitions: dict[str, str] = {}
            for item in ast.walk(tree):
                if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    parent = parents.get(item)
                    qualified = f"{parent.name}.{item.name}" if isinstance(parent, ast.ClassDef) else item.name
                    definitions[item.name] = qualified
                    self._insert_code_symbol(node_id, relative, file_hash, item, qualified, "class" if isinstance(item, ast.ClassDef) else "function")
                    symbols += 1
            module_name = relative[:-3].replace("/", ".") if relative.endswith(".py") else relative.replace("/", ".")
            self._insert_code_symbol(node_id, relative, file_hash, tree, module_name, "module")
            symbols += 1
            for item in ast.walk(tree):
                if isinstance(item, ast.Import):
                    for alias in item.names:
                        relations += self._insert_code_relation(node_id, relative, file_hash, "module", alias.name, None, alias.name, "import", item)
                elif isinstance(item, ast.ImportFrom):
                    imported = item.module or ""
                    for alias in item.names:
                        target = f"{imported}.{alias.name}" if imported else alias.name
                        relations += self._insert_code_relation(node_id, relative, file_hash, "module", relative, None, target, "import", item)
                elif isinstance(item, ast.Call):
                    target = item.func.id if isinstance(item.func, ast.Name) else item.func.attr if isinstance(item.func, ast.Attribute) else ""
                    if target:
                        owner = self._enclosing_qualified_name(item, parents, definitions)
                        relations += self._insert_code_relation(node_id, relative, file_hash, owner, relative, None, definitions.get(target, target), "call", item)
                elif isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load):
                    owner = self._enclosing_qualified_name(item, parents, definitions)
                    relations += self._insert_code_relation(node_id, relative, file_hash, owner, relative, None, definitions.get(item.id, item.id), "read", item)
            for item in ast.walk(tree):
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            owner = self._enclosing_qualified_name(item, parents, definitions)
                            relations += self._insert_code_relation(node_id, relative, file_hash, owner, relative, None, target.id, "write", item)
        self.connection.commit()
        return {"files": files, "symbols": symbols, "relations": relations, "fresh": fresh, "changed": changed, "stale_removed": len(stale_paths), "schema_version": INDEX_SCHEMA_VERSION}

    def _insert_code_symbol(self, node_id: str, path: str, content_hash: str, node: ast.AST, qualified: str, kind: str) -> None:
        line_start = int(getattr(node, "lineno", 1))
        line_end = _node_end(node)
        entry_id = f"code-{self._hash(f'{node_id}:{path}:{qualified}:{line_start}:{kind}')[-16:]}"
        source = {"type": "file", "path": path, "line_start": line_start, "line_end": line_end, "content_hash": content_hash, "freshness": "fresh", "index_schema_version": INDEX_SCHEMA_VERSION}
        name = str(getattr(node, "name", qualified.rsplit(".", 1)[-1]))
        self.connection.execute(
            """
            INSERT OR REPLACE INTO code_symbols
            (entry_id, node_id, path, language, symbol_kind, name, qualified_name,
             line_start, line_end, content_hash, source_json)
            VALUES (?, ?, ?, 'python', ?, ?, ?, ?, ?, ?, ?)
            """,
            (entry_id, node_id, path, kind, name, qualified, line_start, line_end, content_hash, json.dumps(source, sort_keys=True)),
        )

    def _enclosing_qualified_name(self, node: ast.AST, parents: dict[ast.AST, ast.AST], definitions: dict[str, str]) -> str:
        current = parents.get(node)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return definitions.get(current.name, current.name)
            current = parents.get(current)
        return "module"

    def _insert_code_relation(self, node_id: str, source_path: str, content_hash: str, owner: str, target_path: str | None, _unused: str | None, target: str, kind: str, node: ast.AST) -> int:
        line_start = int(getattr(node, "lineno", 1))
        line_end = _node_end(node)
        relation_id = f"relation-{self._hash(f'{node_id}:{source_path}:{owner}:{target_path}:{target}:{kind}:{line_start}')[-16:]}"
        source = {"type": "relation", "path": source_path, "line_start": line_start, "line_end": line_end, "content_hash": content_hash, "freshness": "fresh", "index_schema_version": INDEX_SCHEMA_VERSION}
        self.connection.execute(
            """
            INSERT OR REPLACE INTO code_relations
            (relation_id, node_id, source_path, source_qualified_name, target_path,
             target_qualified_name, relation_kind, line_start, line_end, content_hash, source_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (relation_id, node_id, source_path, owner, target_path, target, kind, line_start, line_end, content_hash, json.dumps(source, sort_keys=True)),
        )
        return 1

    def code_relations(self, query: str = "", *, node_id: str | None = None, relation_kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if node_id:
            clauses.append("node_id = ?")
            params.append(node_id)
        if relation_kind:
            clauses.append("relation_kind = ?")
            params.append(relation_kind)
        if query:
            clauses.append("(lower(source_qualified_name) LIKE ? OR lower(target_qualified_name) LIKE ? OR lower(source_path) LIKE ?)")
            needle = f"%{query.lower()}%"
            params.extend((needle, needle, needle))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(
            f"SELECT * FROM code_relations {where} ORDER BY source_path, line_start, relation_id LIMIT ?",
            (*params, max(1, int(limit))),
        ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["source"] = json.loads(item.pop("source_json"))
            results.append(item)
        return results

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
