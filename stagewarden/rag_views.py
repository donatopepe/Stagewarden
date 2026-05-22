from __future__ import annotations

import shlex
from typing import Any

from .config import AgentConfig
from .rag import DesignRag, RagEntry


def _load_design_rag(config: AgentConfig) -> DesignRag:
    try:
        return DesignRag.load(config.rag_path)
    except (OSError, ValueError, TypeError):
        return DesignRag()


def _try_load_design_rag(config: AgentConfig) -> tuple[DesignRag | None, str]:
    try:
        return DesignRag.load(config.rag_path), ""
    except (OSError, ValueError, TypeError) as exc:
        return None, f"Unable to load design knowledge store: {exc}"


def _rag_entry_report(entry: RagEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "phase": entry.phase,
        "tags": list(entry.tags),
        "title": entry.title,
        "content": entry.content,
        "metadata": dict(entry.metadata),
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def rag_command_report(task: str, config: AgentConfig) -> dict[str, Any]:
    task = task.removesuffix(" --json").strip()
    mutating = task.startswith("rag add ") or task.startswith("rag update ") or task.startswith("rag remove ") or task == "rag compact" or task == "rag rebuild-vectors"
    loaded, load_error = _try_load_design_rag(config)
    if loaded is None:
        if mutating:
            return {"command": task, "ok": False, "error": load_error}
        rag = DesignRag()
    else:
        rag = loaded
    try:
        parts = shlex.split(task)
    except ValueError as exc:
        return {"command": task, "ok": False, "error": f"{_rag_usage()} ({exc})"}
    if task == "rag" or task == "rag list":
        return {
            "command": task,
            "ok": True,
            "vector_entries": len(rag.vector_index),
            "entries": [_rag_entry_report(entry) for entry in rag.get_all(limit=100)],
        }
    if task.startswith("rag search "):
        query_parts: list[str] = []
        phase = None
        tags: list[str] | None = None
        limit = 10
        mode = "hybrid"
        for token in parts[2:]:
            if token.startswith("phase="):
                phase = token.split("=", 1)[1]
                continue
            if token.startswith("tags=") or token.startswith("tag="):
                tags = [item.strip() for item in token.split("=", 1)[1].split(",") if item.strip()]
                continue
            if token.startswith("limit="):
                try:
                    limit = max(1, int(token.split("=", 1)[1]))
                except ValueError:
                    return {"command": task, "ok": False, "error": _rag_usage()}
                continue
            if token.startswith("mode="):
                mode = token.split("=", 1)[1]
                if mode not in {"lexical", "vector", "hybrid"}:
                    return {"command": task, "ok": False, "error": _rag_usage()}
                continue
            query_parts.append(token)
        query = " ".join(query_parts).strip()
        if not query:
            return {"command": task, "ok": False, "error": _rag_usage()}
        return {
            "command": task,
            "ok": True,
            "query": query,
            "mode": mode,
            "entries": [_rag_entry_report(entry) for entry in rag.search(query, phase=phase, tags=tags, limit=limit, mode=mode)],
        }
    if task.startswith("rag add "):
        fields = _parse_key_value_fields(parts[2:])
        if fields:
            phase = str(fields.get("phase", ""))
            title = str(fields.get("title", ""))
            content = str(fields.get("content", ""))
            tags = _parse_tags(str(fields.get("tags", fields.get("tag", phase))))
        elif len(parts) >= 5:
            _, _, phase, title, *content_parts = parts
            content = " ".join(content_parts)
            tags = [phase]
            if " tags=" in content:
                content, raw_tags = content.rsplit(" tags=", 1)
                tags = _parse_tags(raw_tags) or tags
        else:
            return {"command": task, "ok": False, "error": _rag_usage()}
        if not phase or not title or not content:
            return {"command": task, "ok": False, "error": _rag_usage()}
        entry = rag.add(phase=phase, tags=tags, title=title, content=content, metadata={"source": "cli"})
        rag.save(config.rag_path)
        return {"command": task, "ok": True, "entry": _rag_entry_report(entry)}
    if task.startswith("rag update "):
        if len(parts) < 4:
            return {"command": task, "ok": False, "error": _rag_usage()}
        entry_id = parts[2]
        updates = _parse_update_fields(parts[3:])
        if not updates:
            return {"command": task, "ok": False, "error": _rag_usage()}
        entry = rag.update(entry_id, **updates)
        if entry is None:
            return {"command": task, "ok": False, "error": f"Design knowledge entry not found: {entry_id}"}
        rag.save(config.rag_path)
        return {"command": task, "ok": True, "entry": _rag_entry_report(entry)}
    if task.startswith("rag remove "):
        raw = task.split(maxsplit=2)
        if len(raw) != 3:
            return {"command": task, "ok": False, "error": _rag_usage()}
        removed = rag.remove(raw[2])
        if removed:
            rag.save(config.rag_path)
        return {"command": task, "ok": removed, "removed": removed, "entry_id": raw[2], "error": "" if removed else f"Design knowledge entry not found: {raw[2]}"}
    if task == "rag compact":
        removed = rag.compact()
        rag.save(config.rag_path)
        return {"command": task, "ok": True, "removed": removed, "entries": [_rag_entry_report(entry) for entry in rag.get_all(limit=100)]}
    if task == "rag rebuild-vectors":
        indexed = rag.rebuild_vector_index()
        rag.save(config.rag_path)
        return {"command": task, "ok": True, "vector_entries": indexed, "entries": [_rag_entry_report(entry) for entry in rag.get_all(limit=100)]}
    return {"command": task, "ok": False, "error": _rag_usage()}


def render_rag_report(report: dict[str, Any]) -> str:
    if not report.get("ok", True):
        return str(report.get("error", _rag_usage()))
    if "entry" in report:
        entry = report["entry"] if isinstance(report["entry"], dict) else {}
        verb = "Updated" if str(report.get("command", "")).startswith("rag update") else "Added"
        return f"{verb} design knowledge entry {entry.get('entry_id')}: [{entry.get('phase')}] {entry.get('title')}"
    if "removed" in report and str(report.get("command", "")).startswith("rag remove"):
        return f"Removed design knowledge entry {report.get('entry_id')}."
    if "removed" in report and str(report.get("command", "")) == "rag compact":
        return f"Compacted design knowledge entries: removed={report.get('removed', 0)}"
    if str(report.get("command", "")) == "rag rebuild-vectors":
        return f"Rebuilt RAG vector index: entries={report.get('vector_entries', 0)}"
    entries = report.get("entries", [])
    if not isinstance(entries, list) or not entries:
        return "No design knowledge entries found."
    lines = ["Design knowledge entries:"]
    for item in entries:
        if not isinstance(item, dict):
            continue
        tags = ", ".join(str(tag) for tag in item.get("tags", []))
        lines.append(f"- [{item.get('entry_id')}] [{item.get('phase')}] {item.get('title')} (tags: {tags})")
        content = str(item.get("content", ""))
        if content:
            lines.append(f"  {content[:500]}")
    return "\n".join(lines)


def _rag_usage() -> str:
    return "Usage: rag | rag list | rag search <query> [phase=<phase>] [tags=a,b] [limit=N] [mode=lexical|vector|hybrid] | rag add phase=<phase> title='<title>' content='<content>' [tags=a,b] | rag update <entry_id> field=value [...] | rag remove <entry_id> | rag compact | rag rebuild-vectors"


def _parse_update_fields(tokens: list[str]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    fields = _parse_key_value_fields(tokens)
    for key, value in fields.items():
        if key == "phase":
            updates["phase"] = value
        elif key == "title":
            updates["title"] = value
        elif key == "content":
            updates["content"] = value
        elif key in {"tags", "tag"}:
            updates["tags"] = _parse_tags(value)
    return updates


def _parse_key_value_fields(tokens: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key:
            fields[key] = value
    return fields


def _parse_tags(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]
