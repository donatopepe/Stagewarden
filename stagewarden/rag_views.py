from __future__ import annotations

import shlex
from typing import Any

from .config import AgentConfig
from pathlib import Path

from .rag_benchmark import (
    append_rag_benchmark_history,
    compare_rag_benchmark_reports,
    load_rag_benchmark_history,
    load_rag_benchmark_snapshot,
    run_rag_benchmark,
    save_rag_benchmark_snapshot,
    summarize_rag_benchmark_latest,
    summarize_rag_benchmark_trend,
)
from .rag import DesignRag, RagEntry, resolve_min_score_policy_details


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


def _rag_entry_report(entry: RagEntry, *, score: float | None = None, diagnostics: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "phase": entry.phase,
        "tags": list(entry.tags),
        "title": entry.title,
        "content": entry.content,
        "metadata": dict(entry.metadata),
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "score": score,
        "diagnostics": diagnostics,
    }


def rag_command_report(task: str, config: AgentConfig) -> dict[str, Any]:
    task = task.removesuffix(" --json").strip()
    mutating = task.startswith("rag add ") or task.startswith("rag update ") or task.startswith("rag remove ") or task.startswith("rag compact") or task == "rag rebuild-vectors"
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
    if task == "rag benchmark":
        report = run_rag_benchmark()
        report["ok"] = True
        return report
    if task.startswith("rag benchmark "):
        fields = _parse_key_value_fields(parts[2:])
        report = run_rag_benchmark()
        baseline_path = str(fields.get("baseline", "")).strip()
        write_path = str(fields.get("write", "")).strip()
        history_path = str(fields.get("history", "")).strip()
        latest_only = str(fields.get("latest", "")).strip().lower() in {"1", "true", "yes", "on"}
        max_entries = 50
        threshold = 0.05
        if fields.get("threshold") is not None:
            try:
                threshold = max(0.0, float(str(fields.get("threshold"))))
            except ValueError:
                return {"command": task, "ok": False, "error": _rag_usage()}
        if fields.get("max_entries") is not None:
            try:
                max_entries = max(1, int(str(fields.get("max_entries"))))
            except ValueError:
                return {"command": task, "ok": False, "error": _rag_usage()}
        if write_path:
            save_rag_benchmark_snapshot(Path(write_path), report)
            report["saved_to"] = write_path
        if baseline_path:
            try:
                baseline = load_rag_benchmark_snapshot(Path(baseline_path))
            except (OSError, ValueError, TypeError) as exc:
                return {"command": task, "ok": False, "error": f"Unable to load baseline snapshot: {exc}"}
            report["comparison"] = compare_rag_benchmark_reports(baseline, report, threshold=threshold)
        if history_path:
            try:
                history_payload = append_rag_benchmark_history(Path(history_path), report, max_entries=max_entries)
            except (OSError, ValueError, TypeError) as exc:
                return {"command": task, "ok": False, "error": f"Unable to append benchmark history: {exc}"}
            report["history"] = {
                "path": history_path,
                "samples": len(history_payload.get("entries", [])),
                "max_entries": max_entries,
            }
            report["trend"] = summarize_rag_benchmark_trend(history_payload)
            if latest_only:
                report["latest"] = summarize_rag_benchmark_latest(history_payload)
        elif str(fields.get("trend", "")).strip():
            trend_path = str(fields.get("trend", "")).strip()
            try:
                history_payload = load_rag_benchmark_history(Path(trend_path))
            except (OSError, ValueError, TypeError) as exc:
                return {"command": task, "ok": False, "error": f"Unable to load benchmark trend history: {exc}"}
            report["trend"] = summarize_rag_benchmark_trend(history_payload)
            if latest_only:
                report["latest"] = summarize_rag_benchmark_latest(history_payload)
        report["ok"] = True
        return report
    if task.startswith("rag search "):
        query_parts: list[str] = []
        phase = None
        role = None
        tags: list[str] | None = None
        limit = 10
        mode = "hybrid"
        min_score: float | None = None
        for token in parts[2:]:
            if token.startswith("phase="):
                phase = token.split("=", 1)[1]
                continue
            if token.startswith("role="):
                role = token.split("=", 1)[1]
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
            if token.startswith("min_score="):
                try:
                    min_score = max(0.0, float(token.split("=", 1)[1]))
                except ValueError:
                    return {"command": task, "ok": False, "error": _rag_usage()}
                continue
            query_parts.append(token)
        query = " ".join(query_parts).strip()
        if not query:
            return {"command": task, "ok": False, "error": _rag_usage()}
        policy = resolve_min_score_policy_details(phase=phase, role=role, mode=mode, override=min_score)
        effective_min_score = float(policy.get("min_score", 0.0))
        policy_source = str(policy.get("policy_source", "default"))
        diagnostic_results = rag.search_diagnostics(query, phase=phase, role=role, tags=tags, limit=limit, mode=mode, min_score=min_score)
        return {
            "command": task,
            "ok": True,
            "query": query,
            "mode": mode,
            "role": role,
            "min_score": effective_min_score,
            "policy_source": policy_source,
            "entries": [
                _rag_entry_report(
                    item["entry"],
                    score=float(item.get("score", 0.0)),
                    diagnostics={
                        "mode": item.get("mode"),
                        "lexical_score": float(item.get("lexical_score", 0.0)),
                        "vector_score": float(item.get("vector_score", 0.0)),
                    },
                )
                for item in diagnostic_results
            ],
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
    if task.startswith("rag compact"):
        compact_mode = "strict"
        for token in parts[2:]:
            if token.startswith("mode="):
                compact_mode = token.split("=", 1)[1]
        if compact_mode not in {"strict", "balanced", "aggressive"}:
            return {"command": task, "ok": False, "error": _rag_usage()}
        removed = rag.compact(mode=compact_mode)
        rag.save(config.rag_path)
        return {"command": task, "ok": True, "mode": compact_mode, "removed": removed, "entries": [_rag_entry_report(entry) for entry in rag.get_all(limit=100)]}
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
    if str(report.get("command", "")) == "rag benchmark":
        modes = report.get("modes", [])
        if not isinstance(modes, list):
            return "RAG benchmark completed."
        lines = ["RAG benchmark:"]
        for item in modes:
            if not isinstance(item, dict):
                continue
            metrics = item.get("metrics", {}) if isinstance(item.get("metrics"), dict) else {}
            lines.append(
                f"- {item.get('mode')}: recall@1={float(metrics.get('recall@1', 0.0)):.3f}, recall@3={float(metrics.get('recall@3', 0.0)):.3f}"
            )
        comparison = report.get("comparison") if isinstance(report.get("comparison"), dict) else None
        if comparison is not None:
            lines.append(f"Comparison passed: {bool(comparison.get('passed'))}")
            regressions = comparison.get("regressions", []) if isinstance(comparison.get("regressions"), list) else []
            for item in regressions:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"- regression {item.get('mode')} {item.get('metric')}: baseline={float(item.get('baseline', 0.0)):.3f}, current={float(item.get('current', 0.0)):.3f}, delta={float(item.get('delta', 0.0)):.3f}"
                )
        history = report.get("history") if isinstance(report.get("history"), dict) else None
        if history is not None:
            lines.append(f"History samples: {int(history.get('samples', 0))}")
        trend = report.get("trend") if isinstance(report.get("trend"), dict) else None
        if trend is not None:
            first_recorded_at = trend.get("first_recorded_at")
            last_recorded_at = trend.get("last_recorded_at")
            lines.append(
                f"Trend: samples={int(trend.get('samples', 0))}, improving={int(trend.get('improving', 0))}, regressing={int(trend.get('regressing', 0))}, stable={int(trend.get('stable', 0))}"
            )
            if isinstance(first_recorded_at, str) and isinstance(last_recorded_at, str):
                lines.append(f"Trend window: first={first_recorded_at}, last={last_recorded_at}")
            mode_trends = trend.get("modes", []) if isinstance(trend.get("modes"), list) else []
            for item in mode_trends:
                if not isinstance(item, dict):
                    continue
                recall1 = item.get("recall@1", {}) if isinstance(item.get("recall@1"), dict) else {}
                recall3 = item.get("recall@3", {}) if isinstance(item.get("recall@3"), dict) else {}
                lines.append(
                    f"- trend {item.get('mode')}: type={item.get('trend')}, recall@1={float(recall1.get('first', 0.0)):.3f}->{float(recall1.get('last', 0.0)):.3f} (delta={float(recall1.get('delta', 0.0)):.3f}), recall@3={float(recall3.get('first', 0.0)):.3f}->{float(recall3.get('last', 0.0)):.3f} (delta={float(recall3.get('delta', 0.0)):.3f})"
                )
        latest = report.get("latest") if isinstance(report.get("latest"), dict) else None
        if latest is not None:
            lines.append(f"Latest snapshot samples={int(latest.get('samples', 0))}")
            deltas = latest.get("deltas", []) if isinstance(latest.get("deltas"), list) else []
            for item in deltas:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"- latest delta {item.get('mode')} {item.get('metric')}: prev={float(item.get('previous', 0.0)):.3f}, latest={float(item.get('latest', 0.0)):.3f}, delta={float(item.get('delta', 0.0)):.3f}"
                )
        return "\n".join(lines)
    entries = report.get("entries", [])
    if str(report.get("command", "")).startswith("rag search "):
        mode = str(report.get("mode", "hybrid"))
        min_score = float(report.get("min_score", 0.0)) if isinstance(report.get("min_score"), (int, float)) else 0.0
        policy_source = str(report.get("policy_source", "default"))
        lines = [f"RAG search: mode={mode}, min_score={min_score:.3f}, policy_source={policy_source}"]
        if not isinstance(entries, list) or not entries:
            lines.append("No design knowledge entries found.")
            return "\n".join(lines)
        lines.append("Design knowledge entries:")
        for item in entries:
            if not isinstance(item, dict):
                continue
            tags = ", ".join(str(tag) for tag in item.get("tags", []))
            score = item.get("score")
            score_text = f", score={float(score):.3f}" if isinstance(score, (int, float)) else ""
            lines.append(f"- [{item.get('entry_id')}] [{item.get('phase')}] {item.get('title')} (tags: {tags}{score_text})")
            content = str(item.get("content", ""))
            if content:
                lines.append(f"  {content[:500]}")
        return "\n".join(lines)
    if not isinstance(entries, list) or not entries:
        return "No design knowledge entries found."
    lines = ["Design knowledge entries:"]
    for item in entries:
        if not isinstance(item, dict):
            continue
        tags = ", ".join(str(tag) for tag in item.get("tags", []))
        score = item.get("score")
        score_text = f", score={float(score):.3f}" if isinstance(score, (int, float)) else ""
        lines.append(f"- [{item.get('entry_id')}] [{item.get('phase')}] {item.get('title')} (tags: {tags}{score_text})")
        content = str(item.get("content", ""))
        if content:
            lines.append(f"  {content[:500]}")
    return "\n".join(lines)


def _rag_usage() -> str:
    return "Usage: rag | rag list | rag search <query> [phase=<phase>] [role=<role>] [tags=a,b] [limit=N] [mode=lexical|vector|hybrid] [min_score=0.0] | rag add phase=<phase> title='<title>' content='<content>' [tags=a,b] | rag update <entry_id> field=value [...] | rag remove <entry_id> | rag compact [mode=strict|balanced|aggressive] | rag rebuild-vectors | rag benchmark [baseline=<path>] [threshold=0.05] [write=<path>] [history=<path>] [trend=<path>] [max_entries=<N>] [latest=true]"


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
