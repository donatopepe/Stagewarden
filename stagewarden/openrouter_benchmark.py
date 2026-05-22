from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .handoff import HandoffManager, format_run_model
from .provider_registry import model_token_env
from .textcodec import loads_text, read_text_utf8


DEFAULT_OPENROUTER_BENCHMARK_BASELINE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "openrouter_benchmark_baseline.json"
)
DEFAULT_OPENROUTER_BENCHMARK_HISTORY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "openrouter_benchmark_history.jsonl"
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


def openrouter_benchmark_history_path() -> Path:
    override = os.environ.get("STAGEWARDEN_OPENROUTER_BENCHMARK_HISTORY")
    if override:
        return Path(override)
    return DEFAULT_OPENROUTER_BENCHMARK_HISTORY_PATH


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
    history_path: str | Path | None = None,
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
        regression_tolerance = float(suite.get("regression_tolerance", 0.0) or 0.0)
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
            "regression_tolerance": regression_tolerance,
            "accuracy": suite_accuracy,
            "passed": suite_passed,
            "cases": case_reports,
        }

    overall_accuracy = 0.0 if total_cases == 0 else round(correct_cases / total_cases, 3)
    overall_passed = passed_suites == len(report_suites) and total_cases > 0
    report = {
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
        "suites": report_suites,
        "overall": {
            "total_cases": total_cases,
            "passed_suites": passed_suites,
            "suite_count": len(report_suites),
            "accuracy": overall_accuracy,
            "passed": overall_passed,
            "regressed": False,
        },
    }
    history_report = _build_openrouter_benchmark_history_report(
        baseline=baseline,
        current_report=report,
        history_path=history_path,
    )
    if history_report is not None:
        report["history"] = history_report
        for regression in history_report["regressions"]:
            suite_id = str(regression["suite_id"])
            suite_report = report_suites.get(suite_id)
            if suite_report is None:
                continue
            suite_report["passed"] = False
            suite_report["regressed"] = True
            suite_report["previous_accuracy"] = regression["previous_accuracy"]
            suite_report["delta_accuracy"] = regression["delta_accuracy"]
            suite_report["regression_tolerance"] = regression["tolerance"]
        report["overall"]["regressed"] = bool(history_report["overall"]["regressed"])
        report["overall"]["passed"] = report["overall"]["passed"] and not report["overall"]["regressed"]
    for suite_id, suite_report in report_suites.items():
        report[suite_id] = suite_report
    return report


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


def _build_openrouter_benchmark_history_report(
    *,
    baseline: dict[str, Any],
    current_report: dict[str, Any],
    history_path: str | Path | None,
) -> dict[str, Any] | None:
    if history_path is None:
        return None

    path = Path(history_path)
    previous = _load_openrouter_benchmark_history_snapshot(path)
    current_snapshot = _compact_openrouter_benchmark_snapshot(current_report)
    history_report = {
        "enabled": True,
        "path": str(path),
        "previous": previous,
        "current": current_snapshot,
        "regressions": [],
        "appended": False,
    }
    overall_regressed = False
    if previous is not None:
        history_report["regressions"] = _compare_openrouter_benchmark_snapshots(previous, current_snapshot)
        overall_regressed = _overall_regressed(
            previous,
            current_snapshot,
            float(baseline.get("regression_tolerance", 0.0) or 0.0),
        )
        for regression in history_report["regressions"]:
            suite_id = str(regression["suite_id"])
            suite_snapshot = current_snapshot.get("suites", {}).get(suite_id)
            if not isinstance(suite_snapshot, dict):
                continue
            suite_snapshot["passed"] = False
            suite_snapshot["regressed"] = True
            suite_snapshot["previous_accuracy"] = regression["previous_accuracy"]
            suite_snapshot["delta_accuracy"] = regression["delta_accuracy"]
            suite_snapshot["regression_tolerance"] = regression["tolerance"]
        current_snapshot["overall"]["regressed"] = overall_regressed
        current_snapshot["overall"]["passed"] = current_snapshot["overall"]["passed"] and not overall_regressed
        history_report["overall"] = {
            "previous_accuracy": previous.get("overall", {}).get("accuracy"),
            "current_accuracy": current_snapshot["overall"]["accuracy"],
            "delta_accuracy": round(
                current_snapshot["overall"]["accuracy"] - float(previous.get("overall", {}).get("accuracy", 0.0)),
                3,
            ),
            "tolerance": float(baseline.get("regression_tolerance", 0.0) or 0.0),
            "regressed": bool(history_report["regressions"]) or overall_regressed,
        }
    else:
        history_report["overall"] = {
            "previous_accuracy": None,
            "current_accuracy": current_snapshot["overall"]["accuracy"],
            "delta_accuracy": None,
            "tolerance": float(baseline.get("regression_tolerance", 0.0) or 0.0),
            "regressed": False,
        }

    _append_openrouter_benchmark_history_snapshot(path, current_snapshot)
    history_report["appended"] = True
    return history_report


def _load_openrouter_benchmark_history_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = read_text_utf8(path).splitlines()
    for line in reversed(text):
        line = line.strip()
        if not line:
            continue
        try:
            payload = loads_text(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _append_openrouter_benchmark_history_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(snapshot, sort_keys=False))
        stream.write("\n")


def _compact_openrouter_benchmark_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    suites = report.get("suites", {})
    compact_suites: dict[str, dict[str, Any]] = {}
    if isinstance(suites, dict):
        for suite_id, suite_report in suites.items():
            if not isinstance(suite_report, dict):
                continue
            compact_suites[str(suite_id)] = {
                "suite_id": str(suite_report.get("suite_id", suite_id)),
                "accuracy": float(suite_report.get("accuracy", 0.0) or 0.0),
                "threshold_accuracy": float(suite_report.get("threshold_accuracy", 0.0) or 0.0),
                "regression_tolerance": float(suite_report.get("regression_tolerance", 0.0) or 0.0),
                "passed": bool(suite_report.get("passed", False)),
            }
    overall = report.get("overall", {})
    return {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "command": str(report.get("command", "openrouter benchmark")),
        "baseline": {
            "path": str(report.get("baseline", {}).get("path", "")),
            "version": str(report.get("baseline", {}).get("version", "1")),
            "provider": str(report.get("baseline", {}).get("provider", "openrouter")),
            "model": str(report.get("baseline", {}).get("model", "")),
            "account": str(report.get("baseline", {}).get("account", "")),
        },
        "overall": {
            "accuracy": float(overall.get("accuracy", 0.0) or 0.0),
            "suite_count": int(overall.get("suite_count", 0) or 0),
            "total_cases": int(overall.get("total_cases", 0) or 0),
            "passed": bool(overall.get("passed", False)),
        },
        "suites": compact_suites,
    }


def _compare_openrouter_benchmark_snapshots(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    regressions: list[dict[str, Any]] = []
    previous_suites = previous.get("suites", {})
    current_suites = current.get("suites", {})
    if isinstance(previous_suites, dict) and isinstance(current_suites, dict):
        for suite_id, current_suite in current_suites.items():
            if not isinstance(current_suite, dict):
                continue
            previous_suite = previous_suites.get(suite_id)
            if not isinstance(previous_suite, dict):
                continue
            current_accuracy = float(current_suite.get("accuracy", 0.0) or 0.0)
            previous_accuracy = float(previous_suite.get("accuracy", 0.0) or 0.0)
            tolerance = float(current_suite.get("regression_tolerance", 0.0) or 0.0)
            if current_accuracy + tolerance < previous_accuracy:
                regressions.append(
                    {
                        "suite_id": str(suite_id),
                        "previous_accuracy": previous_accuracy,
                        "current_accuracy": current_accuracy,
                        "delta_accuracy": round(current_accuracy - previous_accuracy, 3),
                        "tolerance": tolerance,
                    }
                )
    return regressions


def _overall_regressed(previous: dict[str, Any], current: dict[str, Any], tolerance: float) -> bool:
    previous_overall = float(previous.get("overall", {}).get("accuracy", 0.0) or 0.0)
    current_overall = float(current.get("overall", {}).get("accuracy", 0.0) or 0.0)
    return current_overall + tolerance < previous_overall
