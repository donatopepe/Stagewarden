from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
