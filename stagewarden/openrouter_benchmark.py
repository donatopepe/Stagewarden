from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .handoff import HandoffManager, format_run_model
from .provider_registry import model_token_env
from .textcodec import loads_text, read_text_utf8


DEFAULT_OPENROUTER_BENCHMARK_BASELINE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "openrouter_benchmark_baseline.json"
)


@dataclass(frozen=True, slots=True)
class OpenRouterBenchmarkCase:
    suite_id: str
    case_id: str
    prompt: str
    expected_answer: str
    kind: str
    source: str


def openrouter_benchmark_baseline_path() -> Path:
    override = os.environ.get("STAGEWARDEN_OPENROUTER_BENCHMARK_BASELINE")
    if override:
        return Path(override)
    return DEFAULT_OPENROUTER_BENCHMARK_BASELINE_PATH


def load_openrouter_benchmark_baseline(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path is not None else openrouter_benchmark_baseline_path()
    payload = loads_text(read_text_utf8(source))
    if not isinstance(payload, dict):
        raise ValueError("OpenRouter benchmark baseline must be a JSON object.")
    suites = payload.get("suites", [])
    if not isinstance(suites, list) or not suites:
        raise ValueError("OpenRouter benchmark baseline requires a non-empty 'suites' list.")
    return payload


def render_openrouter_benchmark_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=False)


def run_openrouter_benchmark(
    *,
    timeout_seconds: int | None = None,
    baseline_path: str | Path | None = None,
) -> dict[str, Any]:
    baseline = load_openrouter_benchmark_baseline(baseline_path)
    model = str(baseline.get("model", "cheap")).strip() or "cheap"
    account = str(baseline.get("account", "live")).strip() or "live"
    baseline_timeout = int(baseline.get("timeout_seconds", 30) or 30)
    timeout = timeout_seconds if timeout_seconds is not None else baseline_timeout
    openrouter_env = _resolve_openrouter_env_name(model)
    manager = HandoffManager(timeout_seconds=timeout)
    manager.account_env_by_target = {f"{model}:{account}": openrouter_env}
    suites = baseline.get("suites", [])
    if not isinstance(suites, list):
        raise ValueError("OpenRouter benchmark baseline suites must be a list.")

    report_suites: dict[str, dict[str, Any]] = {}
    total_cases = 0
    correct_cases = 0
    passed_suites = 0

    for suite in suites:
        if not isinstance(suite, dict):
            continue
        suite_id = str(suite.get("id", "")).strip()
        if not suite_id:
            continue
        cases = _load_suite_cases(suite_id, suite)
        threshold = float(suite.get("min_accuracy", 1.0) or 1.0)
        case_reports: list[dict[str, Any]] = []
        suite_correct = 0
        suite_failed = False
        for case in cases:
            total_cases += 1
            result = manager.execute(format_run_model(model, case.prompt, account=account))
            case_report: dict[str, Any] = {
                "case_id": case.case_id,
                "suite_id": case.suite_id,
                "source": case.source,
                "expected_answer": case.expected_answer,
                "kind": case.kind,
                "ok": result.ok,
                "error": result.error,
                "routed_model": "",
                "content": "",
                "answer": "",
                "correct": False,
                "usage": {},
            }
            if result.ok:
                try:
                    payload = json.loads(result.output)
                except json.JSONDecodeError as exc:
                    case_report["error"] = f"invalid JSON output: {exc}"
                    suite_failed = True
                else:
                    content = str(payload.get("content") or payload.get("reasoning") or "").strip()
                    answer = _extract_answer(case.kind, content)
                    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
                    case_report.update(
                        {
                            "routed_model": str(payload.get("routed_model", "")),
                            "content": content,
                            "answer": answer,
                            "usage": dict(usage),
                        }
                    )
                    case_report["correct"] = answer == case.expected_answer
                    suite_correct += 1 if case_report["correct"] else 0
                    correct_cases += 1 if case_report["correct"] else 0
            else:
                suite_failed = True
            if not case_report["correct"]:
                suite_failed = True
            case_reports.append(case_report)

        suite_accuracy = 0.0 if not case_reports else round(suite_correct / len(case_reports), 3)
        suite_passed = (suite_accuracy >= threshold) and not suite_failed
        passed_suites += 1 if suite_passed else 0
        report_suites[suite_id] = {
            "suite_id": suite_id,
            "label": str(suite.get("label", suite_id)),
            "description": str(suite.get("description", "")),
            "threshold_accuracy": threshold,
            "accuracy": suite_accuracy,
            "passed": suite_passed,
            "cases": case_reports,
        }

    overall_accuracy = 0.0 if total_cases == 0 else round(correct_cases / total_cases, 3)
    overall_passed = passed_suites == len(report_suites) and total_cases > 0
    return {
        "command": "openrouter benchmark",
        "baseline": {
            "path": str(baseline_path or openrouter_benchmark_baseline_path()),
            "version": str(baseline.get("_version", "1")),
            "provider": str(baseline.get("provider", "openrouter")),
            "model": model,
            "account": account,
            "timeout_seconds": baseline_timeout,
            "openrouter_env": openrouter_env,
        },
        "simple": report_suites.get("simple", {}),
        "complex": report_suites.get("complex", {}),
        "overall": {
            "total_cases": total_cases,
            "passed_suites": passed_suites,
            "suite_count": len(report_suites),
            "accuracy": overall_accuracy,
            "passed": overall_passed,
        },
    }


def _load_suite_cases(suite_id: str, suite: dict[str, Any]) -> list[OpenRouterBenchmarkCase]:
    cases_obj = suite.get("cases", [])
    if not isinstance(cases_obj, list) or not cases_obj:
        raise ValueError(f"OpenRouter benchmark suite '{suite_id}' must contain cases.")
    cases: list[OpenRouterBenchmarkCase] = []
    for case in cases_obj:
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("id", "")).strip()
        prompt = str(case.get("prompt", "")).strip()
        expected = str(case.get("expected_answer", "")).strip().upper()
        kind = str(case.get("kind", "")).strip().lower()
        source = str(case.get("source", "")).strip()
        if not case_id or not prompt or not expected or kind not in {"choice", "number"}:
            continue
        cases.append(
            OpenRouterBenchmarkCase(
                suite_id=suite_id,
                case_id=case_id,
                prompt=prompt,
                expected_answer=expected,
                kind=kind,
                source=source,
            )
        )
    if not cases:
        raise ValueError(f"OpenRouter benchmark suite '{suite_id}' has no valid cases.")
    return cases


def _extract_answer(kind: str, text: str) -> str:
    if kind == "choice":
        matches = re.findall(r"\b([ABCD])\b", text.upper())
        if not matches:
            return ""
        return matches[-1]
    matches = re.findall(r"-?\d[\d,]*", text)
    if not matches:
        return ""
    return matches[-1].replace(",", "")


def _resolve_openrouter_env_name(model: str) -> str:
    candidate = model_token_env().get(model) or "OPENROUTER_API_KEY"
    if os.environ.get(candidate):
        return candidate
    if candidate != "OPENROUTER_API_KEY" and os.environ.get("OPENROUTER_API_KEY"):
        return "OPENROUTER_API_KEY"
    raise RuntimeError("OpenRouter API key is required for this benchmark.")
