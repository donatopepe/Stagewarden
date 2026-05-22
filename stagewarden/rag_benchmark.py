from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8

from .rag import DesignRag


@dataclass(frozen=True)
class RagBenchmarkCase:
    query: str
    expected_title: str


def _seed_rag() -> DesignRag:
    rag = DesignRag()
    rag.add(
        phase="design",
        tags=["api", "contract"],
        title="API boundary contract",
        content="Define REST contract boundaries for external integrations.",
    )
    rag.add(
        phase="design",
        tags=["storage", "database"],
        title="Storage persistence policy",
        content="Persist transactional state in relational storage with migrations.",
    )
    rag.add(
        phase="delivery",
        tags=["testing", "validation"],
        title="Validation test matrix",
        content="Run focused and full-suite validation gates before merge.",
    )
    rag.add(
        phase="design",
        tags=["security", "auth"],
        title="Authentication and authorization boundary",
        content="Use explicit authn/authz checks for privileged operations.",
    )
    return rag


def _cases() -> list[RagBenchmarkCase]:
    return [
        RagBenchmarkCase(query="rest api contract", expected_title="API boundary contract"),
        RagBenchmarkCase(query="database persistence", expected_title="Storage persistence policy"),
        RagBenchmarkCase(query="full suite validation", expected_title="Validation test matrix"),
        RagBenchmarkCase(query="auth security checks", expected_title="Authentication and authorization boundary"),
    ]


def _mode_metrics(rag: DesignRag, mode: str, *, k_values: tuple[int, ...] = (1, 3)) -> dict[str, Any]:
    cases = _cases()
    hits_by_k = {k: 0 for k in k_values}
    case_results: list[dict[str, Any]] = []
    for case in cases:
        entries = rag.search(case.query, mode=mode, limit=max(k_values))
        titles = [entry.title for entry in entries]
        case_payload = {
            "query": case.query,
            "expected_title": case.expected_title,
            "results": titles,
        }
        for k in k_values:
            matched = case.expected_title in titles[:k]
            case_payload[f"hit@{k}"] = matched
            if matched:
                hits_by_k[k] += 1
        case_results.append(case_payload)
    total = len(cases)
    recall = {f"recall@{k}": (hits_by_k[k] / total if total else 0.0) for k in k_values}
    return {
        "mode": mode,
        "cases": case_results,
        "metrics": recall,
    }


def run_rag_benchmark() -> dict[str, Any]:
    rag = _seed_rag()
    modes = ["lexical", "vector", "hybrid"]
    return {
        "command": "rag benchmark",
        "version": 1,
        "case_count": len(_cases()),
        "modes": [_mode_metrics(rag, mode) for mode in modes],
    }


def _mode_metrics_map(report: dict[str, Any]) -> dict[str, dict[str, float]]:
    mapping: dict[str, dict[str, float]] = {}
    modes = report.get("modes", [])
    if not isinstance(modes, list):
        return mapping
    for item in modes:
        if not isinstance(item, dict):
            continue
        mode = str(item.get("mode", ""))
        metrics = item.get("metrics", {}) if isinstance(item.get("metrics"), dict) else {}
        mapping[mode] = {
            "recall@1": float(metrics.get("recall@1", 0.0)),
            "recall@3": float(metrics.get("recall@3", 0.0)),
        }
    return mapping


def compare_rag_benchmark_reports(baseline: dict[str, Any], current: dict[str, Any], *, threshold: float = 0.05) -> dict[str, Any]:
    baseline_map = _mode_metrics_map(baseline)
    current_map = _mode_metrics_map(current)
    regressions: list[dict[str, Any]] = []
    for mode, baseline_metrics in baseline_map.items():
        current_metrics = current_map.get(mode, {})
        for metric_name, baseline_value in baseline_metrics.items():
            current_value = float(current_metrics.get(metric_name, 0.0))
            delta = current_value - baseline_value
            if delta < -abs(threshold):
                regressions.append(
                    {
                        "mode": mode,
                        "metric": metric_name,
                        "baseline": baseline_value,
                        "current": current_value,
                        "delta": delta,
                    }
                )
    return {
        "threshold": float(threshold),
        "regressions": regressions,
        "passed": not regressions,
    }


def save_rag_benchmark_snapshot(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_utf8(path, dumps_ascii(report, indent=2))


def load_rag_benchmark_snapshot(path: Path) -> dict[str, Any]:
    payload = loads_text(read_text_utf8(path))
    if not isinstance(payload, dict):
        raise ValueError("Invalid RAG benchmark snapshot payload.")
    return payload


def load_rag_benchmark_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "entries": []}
    payload = loads_text(read_text_utf8(path))
    if not isinstance(payload, dict):
        raise ValueError("Invalid RAG benchmark history payload.")
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("Invalid RAG benchmark history entries payload.")
    return {
        "version": int(payload.get("version", 1)),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
    }


def append_rag_benchmark_history(path: Path, report: dict[str, Any], *, max_entries: int = 50) -> dict[str, Any]:
    history = load_rag_benchmark_history(path)
    entries = list(history.get("entries", []))
    entries.append(report)
    if max_entries > 0 and len(entries) > max_entries:
        entries = entries[-max_entries:]
    payload = {"version": 1, "entries": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_utf8(path, dumps_ascii(payload, indent=2))
    return payload


def summarize_rag_benchmark_trend(history: dict[str, Any]) -> dict[str, Any]:
    entries = history.get("entries", []) if isinstance(history, dict) else []
    if not isinstance(entries, list) or not entries:
        return {"samples": 0, "modes": [], "improving": 0, "regressing": 0, "stable": 0}

    mode_names: set[str] = set()
    mapped_entries: list[dict[str, dict[str, float]]] = []
    for report in entries:
        if not isinstance(report, dict):
            continue
        mode_map = _mode_metrics_map(report)
        mapped_entries.append(mode_map)
        mode_names.update(mode_map.keys())

    modes_payload: list[dict[str, Any]] = []
    improving = 0
    regressing = 0
    stable = 0
    for mode in sorted(mode_names):
        recall1_series: list[float] = []
        recall3_series: list[float] = []
        for mode_map in mapped_entries:
            metrics = mode_map.get(mode, {})
            if "recall@1" in metrics:
                recall1_series.append(float(metrics["recall@1"]))
            if "recall@3" in metrics:
                recall3_series.append(float(metrics["recall@3"]))
        if not recall1_series and not recall3_series:
            continue

        first = recall3_series[0] if recall3_series else 0.0
        last = recall3_series[-1] if recall3_series else 0.0
        delta = last - first
        if delta > 1e-9:
            improving += 1
            trend = "improving"
        elif delta < -1e-9:
            regressing += 1
            trend = "regressing"
        else:
            stable += 1
            trend = "stable"

        modes_payload.append(
            {
                "mode": mode,
                "samples": max(len(recall1_series), len(recall3_series)),
                "trend": trend,
                "recall@1": {
                    "first": recall1_series[0] if recall1_series else 0.0,
                    "last": recall1_series[-1] if recall1_series else 0.0,
                    "min": min(recall1_series) if recall1_series else 0.0,
                    "max": max(recall1_series) if recall1_series else 0.0,
                    "delta": (recall1_series[-1] - recall1_series[0]) if len(recall1_series) >= 2 else 0.0,
                },
                "recall@3": {
                    "first": recall3_series[0] if recall3_series else 0.0,
                    "last": recall3_series[-1] if recall3_series else 0.0,
                    "min": min(recall3_series) if recall3_series else 0.0,
                    "max": max(recall3_series) if recall3_series else 0.0,
                    "delta": (recall3_series[-1] - recall3_series[0]) if len(recall3_series) >= 2 else 0.0,
                },
            }
        )

    return {
        "samples": len(entries),
        "modes": modes_payload,
        "improving": improving,
        "regressing": regressing,
        "stable": stable,
    }
