from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from .agent import Agent
from .config import AgentConfig
from .executor import Executor
from .memory import MemoryStore
from .modelprefs import ModelPreferences
from .planner import PlanStep
from .prince2 import Prince2AgentPolicy
from .project_handoff import ProjectHandoff
from .role_tree import build_prince2_role_flow, build_prince2_role_matrix, build_prince2_role_tree, check_prince2_role_tree
from .router import ModelRouter
from .textcodec import loads_text, read_text_utf8


DEFAULT_PRINCE2_BENCHMARK_BASELINE_PATH = Path(__file__).resolve().parents[1] / "data" / "prince2_benchmark_baseline.json"


@dataclass(frozen=True, slots=True)
class Prince2BenchmarkCase:
    suite_id: str
    case_id: str
    kind: str
    prompt: str
    source: str


class Prince2BenchmarkHandoff:
    def __init__(self, outputs: list[dict[str, Any]]) -> None:
        self.outputs = list(outputs)
        self.calls: list[str] = []
        self.model_variant_by_model: dict[str, str] = {}
        self.account_env_by_target: dict[str, str] = {}
        self.model_params_by_model: dict[str, dict[str, str]] = {}

    def execute(self, command: str):  # noqa: ANN001
        self.calls.append(command)
        if self.outputs:
            payload = self.outputs.pop(0)
        else:
            payload = {
                "ok": True,
                "model": "local",
                "backend": "local/mock",
                "prompt": command,
                "command": "RUN_MODEL: local benchmark",
                "output": json.dumps(
                    {
                        "summary": "default accept",
                        "action": {"type": "complete", "message": "validation completed exit_code=0"},
                    }
                ),
                "error": "",
            }
        return SimpleNamespace(**payload)


@contextmanager
def _temp_run_model_env(stub_path: Path):
    original = os.environ.get("RUN_MODEL_BIN")
    os.environ["RUN_MODEL_BIN"] = str(stub_path)
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("RUN_MODEL_BIN", None)
        else:
            os.environ["RUN_MODEL_BIN"] = original


def prince2_benchmark_baseline_path() -> Path:
    override = os.environ.get("STAGEWARDEN_PRINCE2_BENCHMARK_BASELINE")
    if override:
        return Path(override)
    return DEFAULT_PRINCE2_BENCHMARK_BASELINE_PATH


def load_prince2_benchmark_baseline(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path is not None else prince2_benchmark_baseline_path()
    payload = loads_text(read_text_utf8(source))
    if not isinstance(payload, dict):
        raise ValueError("PRINCE2 benchmark baseline must be a JSON object.")
    suites = payload.get("suites", [])
    if not isinstance(suites, list) or not suites:
        raise ValueError("PRINCE2 benchmark baseline requires a non-empty 'suites' list.")
    return payload


def render_prince2_benchmark_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=False)


def run_prince2_benchmark(*, baseline_path: str | Path | None = None) -> dict[str, Any]:
    baseline = load_prince2_benchmark_baseline(baseline_path)
    suites = baseline.get("suites", [])
    if not isinstance(suites, list):
        raise ValueError("PRINCE2 benchmark baseline suites must be a list.")

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
        for case in cases:
            total_cases += 1
            case_report = _run_prince2_benchmark_case(case)
            case_report["suite_id"] = case.suite_id
            case_report["case_id"] = case.case_id
            case_report["kind"] = case.kind
            case_report["prompt"] = case.prompt
            case_report["source"] = case.source
            case_report["passed"] = bool(case_report.get("passed"))
            case_report["node_runtime"] = _case_node_runtime_snapshot(case_report.pop("node_runtime_source", None), case=case)
            if case_report["passed"]:
                suite_correct += 1
                correct_cases += 1
            case_reports.append(case_report)

        suite_accuracy = 0.0 if not case_reports else round(suite_correct / len(case_reports), 3)
        suite_passed = suite_accuracy >= threshold and all(bool(case_report.get("passed")) for case_report in case_reports)
        passed_suites += 1 if suite_passed else 0
        report_suites[suite_id] = {
            "suite_id": suite_id,
            "label": str(suite.get("label", suite_id)),
            "description": str(suite.get("description", "")),
            "threshold_accuracy": threshold,
            "regression_tolerance": regression_tolerance,
            "accuracy": suite_accuracy,
            "passed": suite_passed,
            "case_count": len(case_reports),
            "cases": case_reports,
        }

    overall_accuracy = 0.0 if total_cases == 0 else round(correct_cases / total_cases, 3)
    overall_passed = passed_suites == len(report_suites) and total_cases > 0
    report = {
        "command": "prince2 benchmark",
        "baseline": {
            "path": str(baseline_path or prince2_benchmark_baseline_path()),
            "version": str(baseline.get("_version", "1")),
            "provider": str(baseline.get("provider", "stagewarden")),
        },
        "suites": report_suites,
        "overall": {
            "total_cases": total_cases,
            "passed_suites": passed_suites,
            "suite_count": len(report_suites),
            "accuracy": overall_accuracy,
            "passed": overall_passed,
        },
    }
    for suite_id, suite_report in report_suites.items():
        report[suite_id] = suite_report
    return report


def _load_suite_cases(suite_id: str, suite: dict[str, Any]) -> list[Prince2BenchmarkCase]:
    cases_obj = suite.get("cases", [])
    if not isinstance(cases_obj, list) or not cases_obj:
        raise ValueError(f"PRINCE2 benchmark suite '{suite_id}' must contain cases.")
    cases: list[Prince2BenchmarkCase] = []
    for case in cases_obj:
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("id", "")).strip()
        kind = str(case.get("kind", "")).strip().lower()
        prompt = str(case.get("prompt", "")).strip()
        source = str(case.get("source", "")).strip()
        if not case_id or not kind or not prompt or kind not in _CASE_RUNNERS:
            continue
        cases.append(
            Prince2BenchmarkCase(
                suite_id=suite_id,
                case_id=case_id,
                kind=kind,
                prompt=prompt,
                source=source,
            )
        )
    if not cases:
        raise ValueError(f"PRINCE2 benchmark suite '{suite_id}' has no valid cases.")
    return cases


def _run_prince2_benchmark_case(case: Prince2BenchmarkCase) -> dict[str, Any]:
    runner = _CASE_RUNNERS.get(case.kind)
    if runner is None:
        return {
            "passed": False,
            "summary": f"Unsupported case kind: {case.kind}",
            "observed": {},
            "expected": {},
        }
    return runner(case)


def _suite_transition_plan(suite_id: str) -> list[dict[str, Any]]:
    plans: dict[str, list[dict[str, Any]]] = {
        "governance": [
            {
                "source_node": "board.executive",
                "target_node": "management.project_manager",
                "edge_id": "authorize.project",
                "payload_scope": [
                    "business_justification",
                    "approved_tolerances",
                    "stage_objectives",
                    "reporting_controls",
                ],
                "summary": "authorize project baseline and delegated tolerances",
            },
            {
                "source_node": "management.project_manager",
                "target_node": "delivery.team_manager",
                "edge_id": "issue.work_package",
                "payload_scope": [
                    "assigned_work_package",
                    "product_descriptions",
                    "quality_criteria",
                    "delivery_tolerances",
                ],
                "summary": "issue controlled work package",
            },
        ],
        "assurance": [
            {
                "source_node": "board.executive",
                "target_node": "management.project_manager",
                "edge_id": "authorize.project",
                "payload_scope": [
                    "business_justification",
                    "approved_tolerances",
                    "stage_objectives",
                    "reporting_controls",
                ],
                "summary": "authorize project baseline and delegated tolerances",
            },
            {
                "source_node": "management.project_manager",
                "target_node": "assurance.project_assurance",
                "edge_id": "assure.quality_risk",
                "payload_scope": [
                    "quality_evidence",
                    "risk_controls",
                    "issue_controls",
                    "lessons",
                    "closure_evidence",
                ],
                "summary": "send assurance evidence",
            },
            {
                "source_node": "management.project_manager",
                "target_node": "support.project_support",
                "edge_id": "record.project_evidence",
                "payload_scope": [
                    "approved_baseline_delta",
                    "register_entry",
                    "git_evidence",
                    "decision_record",
                ],
                "summary": "record project evidence",
            },
        ],
        "recovery": [
            {
                "source_node": "board.executive",
                "target_node": "management.project_manager",
                "edge_id": "authorize.project",
                "payload_scope": [
                    "business_justification",
                    "approved_tolerances",
                    "stage_objectives",
                    "reporting_controls",
                ],
                "summary": "authorize recovery baseline and delegated tolerances",
            },
            {
                "source_node": "management.project_manager",
                "target_node": "authority.change_authority",
                "edge_id": "escalate.stage_exception",
                "payload_scope": [
                    "exception_report",
                    "impact_assessment",
                    "options",
                    "risks",
                    "issues",
                    "rebaseline_need",
                ],
                "summary": "escalate stage exception for recovery",
            },
        ],
    }
    return plans.get(suite_id, plans["governance"])


def _build_case_runtime_handoff(case: Prince2BenchmarkCase) -> ProjectHandoff:
    task = case.prompt
    project_handoff = ProjectHandoff(task=task)
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = AgentConfig(workspace_root=Path(tmp_dir))
        prefs = ModelPreferences.default()
        prefs.enabled_models = ["local", "openai"]
        prefs.preferred_model = "openai"
        prefs.set_prince2_role_assignment(
            "project_assurance",
            mode="manual",
            provider="openai",
            provider_model="gpt-5.4-mini",
            params={"reasoning_effort": "medium"},
            source="prince2_benchmark",
        )
        prefs.save(config.model_prefs_path)
        project_handoff.sync_prince2_role_tree_baseline(
            {
                "version": "1",
                "approved_at": "2026-05-08T00:00:00Z",
                "source": "prince2_benchmark",
                "status": "approved",
                "tree": build_prince2_role_tree(prefs),
                "flow": build_prince2_role_flow(),
                "check": check_prince2_role_tree(prefs),
                "matrix": build_prince2_role_matrix(prefs),
            }
        )
        for transition in _suite_transition_plan(case.suite_id):
            project_handoff.send_prince2_node_message(
                source_node=transition["source_node"],
                target_node=transition["target_node"],
                edge_id=transition["edge_id"],
                payload_scope=list(transition["payload_scope"]),
                evidence_refs=["prince2_benchmark"],
                summary=transition["summary"],
            )
    return project_handoff


def _case_orchestration_node_ids(case: Prince2BenchmarkCase) -> list[str]:
    node_ids: list[str] = []
    seen: set[str] = set()
    for transition in _suite_transition_plan(case.suite_id):
        for key in ("source_node", "target_node"):
            node_id = str(transition.get(key, "")).strip()
            if node_id and node_id not in seen:
                seen.add(node_id)
                node_ids.append(node_id)
    return node_ids


def _parse_utc_timestamp(value: str) -> datetime | None:
    clean_value = str(value).strip()
    if not clean_value:
        return None
    try:
        parsed = datetime.fromisoformat(clean_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_ms(now: datetime, then: str) -> int | None:
    parsed = _parse_utc_timestamp(then)
    if parsed is None:
        return None
    delta = now - parsed
    return max(0, int(delta.total_seconds() * 1000))


def _summarize_case_node_runtime(
    nodes: list[dict[str, Any]],
    *,
    status: str,
    materialized_at: str,
    baseline_source: str,
    snapshot_at: str,
) -> dict[str, Any]:
    now = _parse_utc_timestamp(snapshot_at) or datetime.now(timezone.utc)
    counts = {
        "command": "roles runtime",
        "status": status,
        "nodes": len(nodes),
        "ready": 0,
        "waiting": 0,
        "running": 0,
        "blocked": 0,
        "escalated": 0,
        "idle": 0,
        "completed": 0,
        "message_queues": 0,
        "wait_triggers": 0,
        "providers": {},
        "provider_models": {},
        "role_types": [],
        "tokens": {
            "business_case_input": 0,
            "business_case_output": 0,
            "business_case_total": 0,
            "thread_total": 0,
        },
        "cost_usd": {
            "business_case_input": 0.0,
            "business_case_output": 0.0,
            "business_case_total": 0.0,
        },
        "timing": {
            "snapshot_at": snapshot_at,
            "materialized_at": materialized_at,
            "elapsed_since_materialization_ms": _age_ms(now, materialized_at),
            "max_age_since_last_transition_ms": None,
        },
    }
    role_types: list[str] = []
    max_age_since_last_transition_ms: int | None = None
    for node in nodes:
        state = str(node.get("state", "")).strip().lower()
        if state in counts:
            counts[state] += 1
        wait_status = str(node.get("wait_status", "none")).strip().lower()
        if wait_status not in {"", "none"}:
            counts["waiting"] += 0 if state == "waiting" else 1
        counts["message_queues"] += int(node.get("inbox_count", 0) or 0) + int(node.get("outbox_count", 0) or 0)
        counts["wait_triggers"] += len(node.get("wake_triggers", [])) if isinstance(node.get("wake_triggers"), list) else 0
        role_type = str(node.get("role_type", "")).strip()
        if role_type and role_type not in role_types:
            role_types.append(role_type)
        assignment = node.get("assignment", {}) if isinstance(node.get("assignment"), dict) else {}
        provider = str(assignment.get("provider", "none") or "none")
        provider_model = str(assignment.get("provider_model", "none") or "none")
        counts["providers"][provider] = int(counts["providers"].get(provider, 0)) + 1
        provider_variant = f"{provider}:{provider_model}"
        counts["provider_models"][provider_variant] = int(counts["provider_models"].get(provider_variant, 0)) + 1
        input_tokens = int(node.get("business_case_input_token_count", 0) or 0)
        output_tokens = int(node.get("business_case_output_token_count", 0) or 0)
        thread_tokens = int(node.get("thread_token_count", 0) or 0)
        counts["tokens"]["business_case_input"] += input_tokens
        counts["tokens"]["business_case_output"] += output_tokens
        counts["tokens"]["business_case_total"] += input_tokens + output_tokens
        counts["tokens"]["thread_total"] += thread_tokens
        counts["cost_usd"]["business_case_input"] += float(node.get("business_case_input_cost_usd", 0.0) or 0.0)
        counts["cost_usd"]["business_case_output"] += float(node.get("business_case_output_cost_usd", 0.0) or 0.0)
        counts["cost_usd"]["business_case_total"] += float(node.get("business_case_cost_usd", 0.0) or 0.0)
        age_ms = _age_ms(now, str(node.get("last_transition_at", "")))
        if age_ms is not None:
            max_age_since_last_transition_ms = age_ms if max_age_since_last_transition_ms is None else max(max_age_since_last_transition_ms, age_ms)
    counts["role_types"] = role_types
    counts["materialized_at"] = materialized_at
    counts["baseline_source"] = baseline_source
    counts["timing"]["max_age_since_last_transition_ms"] = max_age_since_last_transition_ms
    return counts


def _case_node_runtime_snapshot(source: object, *, case: Prince2BenchmarkCase) -> dict[str, Any]:
    if isinstance(source, ProjectHandoff):
        runtime_report = source.prince2_node_runtime_report()
    elif isinstance(source, dict) and source:
        runtime_report = {
            "status": str(source.get("status", "missing")),
            "summary": source.get("summary", {}),
            "runtime": dict(source.get("runtime", {})),
        }
    else:
        return {
            "status": "missing",
            "summary": {},
            "runtime": {},
            "nodes": [],
            "transitions": [],
            "orchestration": {"node_ids": _case_orchestration_node_ids(case), "mode": "suite_transition_plan"},
            "detail": "PRINCE2 node runtime: missing\n- action: approve a role-tree baseline first.",
        }
    runtime = runtime_report.get("runtime", {}) if isinstance(runtime_report, dict) else {}
    full_nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)] if isinstance(runtime, dict) else []
    selected_node_ids = _case_orchestration_node_ids(case)
    selected_nodes = [node for node in full_nodes if str(node.get("node_id", "")).strip() in selected_node_ids]
    transitions = _collect_node_transitions(selected_nodes)
    materialized_at = str(runtime.get("materialized_at", runtime_report.get("summary", {}).get("materialized_at", "")))
    baseline_source = str(runtime.get("baseline_source", runtime_report.get("summary", {}).get("baseline_source", "unknown")))
    snapshot_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary = _summarize_case_node_runtime(
        selected_nodes,
        status=str(runtime_report.get("status", "missing")),
        materialized_at=materialized_at,
        baseline_source=baseline_source,
        snapshot_at=snapshot_at,
    )
    filtered_runtime = dict(runtime) if isinstance(runtime, dict) else {}
    filtered_runtime["nodes"] = selected_nodes
    return {
        "status": str(runtime_report.get("status", "missing")),
        "summary": summary,
        "runtime": filtered_runtime,
        "nodes": selected_nodes,
        "transitions": transitions,
        "orchestration": {
            "mode": "suite_transition_plan",
            "node_ids": selected_node_ids,
            "node_count": len(selected_nodes),
            "role_types": [str(node.get("role_type", "")) for node in selected_nodes],
        },
        "detail": _render_case_node_runtime_detail({"status": runtime_report.get("status", "missing"), "summary": summary, "runtime": filtered_runtime, "snapshot_at": snapshot_at}, nodes=selected_nodes, transitions=transitions),
    }


def _render_case_node_runtime_detail(
    runtime_report: dict[str, Any],
    *,
    nodes: list[dict[str, Any]] | None = None,
    transitions: list[dict[str, Any]] | None = None,
) -> str:
    runtime = runtime_report.get("runtime", {}) if isinstance(runtime_report, dict) else {}
    nodes = list(nodes or [node for node in runtime.get("nodes", []) if isinstance(node, dict)])
    transitions = list(transitions or _collect_node_transitions(nodes))
    summary = runtime_report.get("summary", {}) if isinstance(runtime_report, dict) else {}
    snapshot_at = str(runtime_report.get("snapshot_at", datetime.now(timezone.utc).isoformat(timespec="seconds")))
    lines = [
        "PRINCE2 node runtime:",
        f"- status: {runtime_report.get('status', 'missing')}",
        f"- nodes: {summary.get('nodes', len(nodes))}",
        (
            f"- ready: {summary.get('ready', 0)} waiting={summary.get('waiting', 0)} "
            f"running={summary.get('running', 0)} blocked={summary.get('blocked', 0)}"
        ),
        f"- materialized_at: {runtime.get('materialized_at', 'unknown')}",
        f"- baseline_source: {runtime.get('baseline_source', 'unknown')}",
        f"- snapshot_at: {snapshot_at}",
        (
            f"- wait_triggers: {summary.get('wait_triggers', 0)} "
            f"message_queues={summary.get('message_queues', 0)}"
        ),
    ]
    if not nodes:
        lines.append("- nodes: none")
    else:
        lines.append("- nodes detail:")
        for index, node in enumerate(nodes, start=1):
            assignment = node.get("assignment", {}) if isinstance(node.get("assignment"), dict) else {}
            context_rule = node.get("context_rule", {}) if isinstance(node.get("context_rule"), dict) else {}
            antagonist_profile = node.get("antagonist_profile", {}) if isinstance(node.get("antagonist_profile"), dict) else {}
            age_since_last_transition_ms = _age_ms(_parse_utc_timestamp(snapshot_at) or datetime.now(timezone.utc), str(node.get("last_transition_at", "")))
            age_since_materialization_ms = _age_ms(_parse_utc_timestamp(snapshot_at) or datetime.now(timezone.utc), str(runtime.get("materialized_at", "")))
            lines.append(
                f"  [{index}] {node.get('node_id', 'unknown')} role={node.get('role_type', 'unknown')} "
                f"label={node.get('label', 'unknown')} parent={node.get('parent_id') or 'none'} "
                f"level={node.get('level', 'unknown')}"
            )
            lines.append(
                f"      state={node.get('state', 'unknown')} wait={node.get('wait_status', 'none')} "
                f"wait_reason={node.get('wait_reason') or 'none'} wake_triggers="
                f"{', '.join(str(item) for item in node.get('wake_triggers', []) if str(item).strip()) or 'none'}"
            )
            lines.append(
                f"      owner={node.get('accountable_owner', 'user')} "
                f"provider={assignment.get('provider', 'none') or 'none'} "
                f"provider_model={assignment.get('provider_model', 'none') or 'none'} "
                f"account={assignment.get('account') or 'none'} "
                f"params={json.dumps(assignment.get('params', {}), sort_keys=True) if isinstance(assignment.get('params'), dict) else '{}'} "
                f"spawn_source={node.get('spawn_source', 'none') or 'none'} "
                f"spawn_reason={node.get('spawn_reason', 'none') or 'none'}"
            )
            lines.append(
                f"      inbox={node.get('inbox_count', 0)} outbox={node.get('outbox_count', 0)} "
                f"child_count={node.get('child_count', 0)} last_transition_at={node.get('last_transition_at', 'unknown')} "
                f"age_since_last_transition_ms={age_since_last_transition_ms if age_since_last_transition_ms is not None else 'unknown'} "
                f"age_since_materialization_ms={age_since_materialization_ms if age_since_materialization_ms is not None else 'unknown'}"
            )
            lines.append(
                f"      tokens total={node.get('thread_token_count', 0)} "
                f"business_case={node.get('business_case_token_count', 0)} "
                f"input={node.get('business_case_input_token_count', 0)} "
                f"output={node.get('business_case_output_token_count', 0)} "
                f"cost_usd={node.get('business_case_cost_usd', 0)}"
            )
            if context_rule:
                include = ", ".join(str(item) for item in context_rule.get("include", []) if str(item).strip()) or "none"
                exclude = ", ".join(str(item) for item in context_rule.get("exclude", []) if str(item).strip()) or "none"
                lines.append(f"      context include={include} exclude={exclude}")
            if antagonist_profile:
                lines.append(
                    f"      antagonist={antagonist_profile.get('antagonist_name', 'unknown')} "
                    f"pressure={antagonist_profile.get('decision_kpis', {}).get('antagonist_pressure_percent', 0)}"
                )
            inbox = [dict(item) for item in node.get("inbox", []) if isinstance(item, dict)]
            outbox = [dict(item) for item in node.get("outbox", []) if isinstance(item, dict)]
            if inbox:
                lines.append("      inbox messages:")
                for message in inbox:
                    lines.append(
                        f"        - {message.get('message_id', 'unknown')} {message.get('source_node', 'unknown')} "
                        f"-> {message.get('target_node', 'unknown')} edge={message.get('edge_id', 'unknown')} "
                        f"status={message.get('status', 'unknown')} summary={message.get('summary', 'unknown')}"
                    )
            if outbox:
                lines.append("      outbox messages:")
                for message in outbox:
                    lines.append(
                        f"        - {message.get('message_id', 'unknown')} {message.get('source_node', 'unknown')} "
                        f"-> {message.get('target_node', 'unknown')} edge={message.get('edge_id', 'unknown')} "
                        f"status={message.get('status', 'unknown')} summary={message.get('summary', 'unknown')}"
                    )
    if not transitions:
        lines.append("- transitions: none")
    else:
        lines.append("- transitions:")
        for index, transition in enumerate(transitions, start=1):
            payload_scope = ", ".join(transition.get("payload_scope", [])) or "none"
            evidence_refs = ", ".join(transition.get("evidence_refs", [])) or "none"
            lines.append(
                f"  [{index}] {transition.get('message_id', 'unknown')} {transition.get('source_node', 'unknown')} "
                f"-> {transition.get('target_node', 'unknown')} edge={transition.get('edge_id', 'unknown')} "
                f"direction={transition.get('direction', 'unknown')} status={transition.get('status', 'unknown')}"
            )
            lines.append(
                f"      flow_type={transition.get('flow_type', 'unknown')} "
                f"payload_scope={payload_scope} evidence_refs={evidence_refs}"
            )
            lines.append(
                f"      validation_condition={transition.get('validation_condition', 'none')} "
                f"decision_authority={transition.get('decision_authority', 'none')} "
                f"summary={transition.get('summary', 'none')}"
            )
    if isinstance(summary.get("providers"), dict) and summary["providers"]:
        lines.append(
            "- provider_usage: "
            + ", ".join(f"{key}={summary['providers'][key]}" for key in sorted(summary["providers"]))
        )
    if isinstance(summary.get("provider_models"), dict) and summary["provider_models"]:
        lines.append(
            "- provider_model_usage: "
            + ", ".join(f"{key}={summary['provider_models'][key]}" for key in sorted(summary["provider_models"]))
        )
    if isinstance(summary.get("tokens"), dict):
        tokens = summary["tokens"]
        lines.append(
            "- token_totals: "
            f"business_case_input={tokens.get('business_case_input', 0)} "
            f"business_case_output={tokens.get('business_case_output', 0)} "
            f"business_case_total={tokens.get('business_case_total', 0)} "
            f"thread_total={tokens.get('thread_total', 0)}"
        )
    if isinstance(summary.get("cost_usd"), dict):
        costs = summary["cost_usd"]
        lines.append(
            "- cost_totals_usd: "
            f"business_case_input={costs.get('business_case_input', 0.0)} "
            f"business_case_output={costs.get('business_case_output', 0.0)} "
            f"business_case_total={costs.get('business_case_total', 0.0)}"
        )
    if isinstance(summary.get("role_types"), list) and summary["role_types"]:
        lines.append("- role_types: " + ", ".join(str(item) for item in summary["role_types"]))
    timing = summary.get("timing") if isinstance(summary.get("timing"), dict) else {}
    if timing:
        lines.append(
            "- timing: "
            f"snapshot_at={timing.get('snapshot_at', 'unknown')} "
            f"materialized_at={timing.get('materialized_at', 'unknown')} "
            f"elapsed_since_materialization_ms={timing.get('elapsed_since_materialization_ms', 'unknown')} "
            f"max_age_since_last_transition_ms={timing.get('max_age_since_last_transition_ms', 'unknown')}"
        )
    return "\n".join(lines)


def _collect_node_transitions(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in nodes:
        for direction in ("outbox", "inbox"):
            for message in node.get(direction, []):
                if not isinstance(message, dict):
                    continue
                message_id = str(message.get("message_id", "")).strip()
                if not message_id or message_id in seen:
                    continue
                seen.add(message_id)
                transitions.append(
                    {
                        "message_id": message_id,
                        "timestamp": str(message.get("timestamp", "")),
                        "direction": direction,
                        "source_node": str(message.get("source_node", "")),
                        "target_node": str(message.get("target_node", "")),
                        "edge_id": str(message.get("edge_id", "")),
                        "flow_type": str(message.get("flow_type", "")),
                        "payload_scope": [str(item) for item in message.get("payload_scope", []) if str(item).strip()],
                        "evidence_refs": [str(item) for item in message.get("evidence_refs", []) if str(item).strip()],
                        "validation_condition": str(message.get("validation_condition", "")),
                        "decision_authority": str(message.get("decision_authority", "")),
                        "summary": str(message.get("summary", "")),
                        "status": str(message.get("status", "")),
                    }
                )
    return transitions


def _policy_case_checklist_structure(case: Prince2BenchmarkCase) -> dict[str, Any]:
    checklist = Prince2AgentPolicy().build_checklist(case.prompt)
    runtime = _build_case_runtime_handoff(case)
    passed = bool(checklist.stage_plan) and bool(checklist.quality_criteria) and "risk" in checklist.tolerances
    return {
        "passed": passed,
        "summary": "checklist includes the governance fields",
        "observed": {
            "stage_plan_count": len(checklist.stage_plan),
            "quality_criteria_count": len(checklist.quality_criteria),
            "tolerances": sorted(checklist.tolerances),
            "prompt_excerpt": case.prompt[:240],
        },
            "expected": {
                "stage_plan": "non-empty",
                "quality_criteria": "non-empty",
                "tolerances": "includes risk",
            },
        "node_runtime_source": runtime,
    }


def _policy_case_vague_rejection(case: Prince2BenchmarkCase) -> dict[str, Any]:
    policy = Prince2AgentPolicy()
    checklist = policy.build_checklist(case.prompt)
    assessment = policy.assess_task(case.prompt, checklist)
    runtime = _build_case_runtime_handoff(case)
    passed = (not assessment.allowed) and bool(assessment.reasons)
    return {
        "passed": passed,
        "summary": "vague tasks are rejected by governance",
        "observed": {
            "allowed": assessment.allowed,
            "reasons": list(assessment.reasons),
            "prompt_excerpt": case.prompt[:240],
        },
            "expected": {
                "allowed": False,
                "reasons": "non-empty",
            },
        "node_runtime_source": runtime,
    }


def _policy_case_escalation_trigger(case: Prince2BenchmarkCase) -> dict[str, Any]:
    policy = Prince2AgentPolicy()
    checklist = policy.build_checklist(case.prompt)
    checklist.tolerance_profile = {
        **checklist.tolerance_profile,
        "margin_percent": 10.0,
        "pressure_percent": 40.0,
    }
    assessment = policy.assess_task(case.prompt, checklist)
    runtime = _build_case_runtime_handoff(case)
    passed = assessment.allowed and assessment.escalation_required and bool(assessment.escalation_notes)
    return {
        "passed": passed,
        "summary": "tolerance pressure triggers escalation",
        "observed": {
            "allowed": assessment.allowed,
            "escalation_required": assessment.escalation_required,
            "notes": list(assessment.escalation_notes),
            "prompt_excerpt": case.prompt[:240],
        },
            "expected": {
                "allowed": True,
                "escalation_required": True,
                "escalation_notes": "non-empty",
            },
        "node_runtime_source": runtime,
    }


def _build_executor_harness(
    *,
    root: Path,
    task: str,
    step: PlanStep,
    outputs: list[dict[str, Any]],
) -> tuple[Executor, Prince2BenchmarkHandoff]:
    config = AgentConfig(workspace_root=root)
    prefs = ModelPreferences.default()
    prefs.enabled_models = ["local", "openai"]
    prefs.preferred_model = "openai"
    prefs.set_prince2_role_assignment(
        "project_assurance",
        mode="manual",
        provider="openai",
        provider_model="gpt-5.4-mini",
        params={"reasoning_effort": "medium"},
        source="prince2_benchmark",
    )
    prefs.save(config.model_prefs_path)
    project_handoff = ProjectHandoff(task=task)
    project_handoff.sync_prince2_role_tree_baseline(
        {
            "version": "1",
            "approved_at": "2026-05-08T00:00:00Z",
            "source": "prince2_benchmark",
            "status": "approved",
            "tree": build_prince2_role_tree(prefs),
            "flow": build_prince2_role_flow(),
            "check": check_prince2_role_tree(prefs),
            "matrix": build_prince2_role_matrix(prefs),
        }
    )
    memory = MemoryStore()
    router = ModelRouter()
    router.configure(enabled_models=["local", "openai"])
    handoff = Prince2BenchmarkHandoff(outputs)
    executor = Executor(config=config, router=router, handoff=handoff, memory=memory, project_handoff=project_handoff)
    return executor, handoff


def _primary_output(*, message: str = "validation completed exit_code=0") -> dict[str, Any]:
    return {
        "ok": True,
        "model": "openai",
        "backend": "openai/mock",
        "prompt": "primary",
        "command": "run_model openai primary",
        "output": json.dumps(
            {
                "summary": "complete the task",
                "validation": "done",
                "confidence": 0.94,
                "action": {
                    "type": "complete",
                    "message": message,
                },
            }
        ),
        "error": "",
    }


def _critic_output(
    *,
    verdict: str | None,
    contradictions: list[str] | None = None,
    missing_evidence: list[str] | None = None,
    counter_argument: str = "No contradiction found.",
    must_escalate: bool = False,
    confidence: float = 0.9,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contradictions": contradictions or [],
        "missing_evidence": missing_evidence or [],
        "counter_argument": counter_argument,
        "must_escalate": must_escalate,
        "confidence": confidence,
    }
    if verdict is not None:
        payload["verdict"] = verdict
    return {
        "ok": True,
        "model": "openai",
        "backend": "openai/mock",
        "prompt": "critic",
        "command": "run_model openai critic",
        "output": json.dumps(payload),
        "error": "",
    }


def _executor_case_accept(case: Prince2BenchmarkCase) -> dict[str, Any]:
    step = PlanStep(
        id="step-validate",
        title="Validate evidence",
        instruction=case.prompt,
        validation="The target files or behavior exist and are internally consistent.",
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        executor, handoff = _build_executor_harness(
            root=Path(tmp_dir),
            task=case.prompt,
            step=step,
            outputs=[
                _primary_output(),
                _critic_output(
                    verdict="accept",
                    contradictions=[],
                    missing_evidence=[],
                    counter_argument="No issue detected.",
                    must_escalate=False,
                    confidence=0.9,
                ),
            ],
        )
        outcome = executor.execute_step(task=case.prompt, step=step, plan=[step], iteration=1, last_observation="none")
    review_prompt = handoff.calls[1] if len(handoff.calls) > 1 else ""
    runtime_source = getattr(executor, "project_handoff", None)
    passed = (
        outcome.ok
        and len(handoff.calls) == 2
        and "You are the devil's advocate / Project Assurance critic." in review_prompt
        and "Required keys: verdict, contradictions, missing_evidence, counter_argument, must_escalate, confidence." in review_prompt
    )
    return {
        "passed": passed,
        "summary": "critic accepts a valid wet-run response",
        "observed": {
            "ok": outcome.ok,
            "error_type": outcome.error_type,
            "calls": len(handoff.calls),
        },
        "expected": {
            "ok": True,
            "error_type": None,
            "devil_advocate_review": True,
        },
        "node_runtime_source": runtime_source,
    }


def _executor_case_block(case: Prince2BenchmarkCase) -> dict[str, Any]:
    step = PlanStep(
        id="step-validate",
        title="Validate evidence",
        instruction=case.prompt,
        validation="The target files or behavior exist and are internally consistent.",
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        executor, _handoff = _build_executor_harness(
            root=Path(tmp_dir),
            task=case.prompt,
            step=step,
            outputs=[
                _primary_output(),
                _critic_output(
                    verdict="block",
                    contradictions=["No wet-run evidence for the completion claim."],
                    missing_evidence=["Real command output"],
                    counter_argument="The response assumes success without proof.",
                    must_escalate=True,
                    confidence=0.97,
                ),
            ],
        )
        outcome = executor.execute_step(task=case.prompt, step=step, plan=[step], iteration=1, last_observation="none")
    runtime_source = getattr(executor, "project_handoff", None)
    passed = (not outcome.ok) and outcome.error_type == "critic_rejection"
    return {
        "passed": passed,
        "summary": "critic blocks an unsafe completion",
        "observed": {
            "ok": outcome.ok,
            "error_type": outcome.error_type,
            "observation": outcome.observation,
        },
        "expected": {
            "ok": False,
            "error_type": "critic_rejection",
        },
        "node_runtime_source": runtime_source,
    }


def _executor_case_invalid_critic(case: Prince2BenchmarkCase) -> dict[str, Any]:
    step = PlanStep(
        id="step-validate",
        title="Validate evidence",
        instruction=case.prompt,
        validation="The target files or behavior exist and are internally consistent.",
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        executor, _handoff = _build_executor_harness(
            root=Path(tmp_dir),
            task=case.prompt,
            step=step,
            outputs=[
                _primary_output(),
                _critic_output(
                    verdict=None,
                    contradictions=[],
                    missing_evidence=["Real command output"],
                    counter_argument="The response assumes success without proof.",
                    must_escalate=True,
                    confidence=0.97,
                ),
            ],
        )
        outcome = executor.execute_step(task=case.prompt, step=step, plan=[step], iteration=1, last_observation="none")
    runtime_source = getattr(executor, "project_handoff", None)
    passed = (not outcome.ok) and outcome.error_type == "critic_invalid_output"
    return {
        "passed": passed,
        "summary": "invalid critic output blocks the step",
        "observed": {
            "ok": outcome.ok,
            "error_type": outcome.error_type,
            "observation": outcome.observation,
        },
        "expected": {
            "ok": False,
            "error_type": "critic_invalid_output",
        },
        "node_runtime_source": runtime_source,
    }


def _executor_case_wet_run_required(case: Prince2BenchmarkCase) -> dict[str, Any]:
    step = PlanStep(
        id="step-validate",
        title="Validate evidence",
        instruction=case.prompt,
        validation="The target files or behavior exist and are internally consistent.",
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        executor, _handoff = _build_executor_harness(
            root=Path(tmp_dir),
            task=case.prompt,
            step=step,
            outputs=[
                {
                    "ok": True,
                    "model": "openai",
                    "backend": "openai/mock",
                    "prompt": "primary",
                    "command": "run_model openai primary",
                    "output": json.dumps(
                {
                    "summary": "complete the task",
                    "validation": "done",
                    "confidence": 0.94,
                    "action": {
                        "type": "complete",
                        "message": "task acknowledged",
                    },
                }
            ),
            "error": "",
        },
                _critic_output(
                    verdict="accept",
                    contradictions=[],
                    missing_evidence=[],
                    counter_argument="No issue detected.",
                    must_escalate=False,
                    confidence=0.9,
                ),
            ],
        )
        outcome = executor.execute_step(task=case.prompt, step=step, plan=[step], iteration=1, last_observation="none")
    runtime_source = getattr(executor, "project_handoff", None)
    passed = (not outcome.ok) and outcome.error_type == "wet_run_required"
    return {
        "passed": passed,
        "summary": "dry completion is rejected without wet-run evidence",
        "observed": {
            "ok": outcome.ok,
            "error_type": outcome.error_type,
            "observation": outcome.observation,
        },
        "expected": {
            "ok": False,
            "error_type": "wet_run_required",
        },
        "node_runtime_source": runtime_source,
    }


def _executor_case_prompt_packet(case: Prince2BenchmarkCase) -> dict[str, Any]:
    step = PlanStep(
        id="step-implement",
        title="Implement feature",
        instruction=case.prompt,
        validation="The target files or behavior exist and a real wet-run verifies the change.",
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        executor, handoff = _build_executor_harness(
            root=Path(tmp_dir),
            task=case.prompt,
            step=step,
            outputs=[
                _primary_output(),
                _critic_output(
                    verdict="accept",
                    contradictions=[],
                    missing_evidence=[],
                    counter_argument="No contradiction found.",
                    must_escalate=False,
                    confidence=0.9,
                ),
            ],
        )
        outcome = executor.execute_step(task=case.prompt, step=step, plan=[step], iteration=1, last_observation="none")
    prompt = handoff.calls[0] if handoff.calls else ""
    runtime_source = getattr(executor, "project_handoff", None)
    passed = (
        outcome.ok
        and "prince2_active_role" in prompt
        and "PRINCE2 node AI context packet" in prompt
        and "active_flow_rule: context moves only through approved PRINCE2 flow edges" in prompt
        and "core_agent_capabilities: shell=true files=true git=true wet_run_required=true" in prompt
    )
    return {
        "passed": passed,
        "summary": "executor prompt includes PRINCE2 role and flow context",
        "observed": {
            "ok": outcome.ok,
            "prompt_excerpt": prompt[:1200],
        },
        "expected": {
            "ok": True,
            "contains": [
                "prince2_active_role",
                "prince2_node_context_packet",
                "active_flow_rule: context moves only through approved PRINCE2 flow edges",
                "core_agent_capabilities: shell=true files=true git=true wet_run_required=true",
            ],
        },
        "node_runtime_source": runtime_source,
    }


def _write_agent_success_stub(root: Path) -> Path:
    path = root / "run_model_success_stub.py"
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import json",
                "import re",
                "import sys",
                "",
                "def extract(prompt: str, field: str) -> str:",
                '    match = re.search(rf"^{re.escape(field)}=(.+)$", prompt, re.MULTILINE)',
                "    return match.group(1).strip() if match else ''",
                "",
                "def main() -> int:",
                "    if len(sys.argv) < 3:",
                '        print(json.dumps({"error": "usage: stub <model> <prompt>"}))',
                "        return 1",
                "    prompt = sys.argv[2]",
                "    prompt_lower = prompt.lower()",
                "    instruction = extract(prompt, 'instruction').lower()",
                "    if 'required keys: verdict' in prompt_lower or 'allowed verdict values: accept, revise, block' in prompt_lower or \"you are the devil's advocate / project assurance critic\" in prompt_lower:",
                '        print(json.dumps({"summary": "devil advocate review", "verdict": "accept", "contradictions": [], "missing_evidence": [], "counter_argument": "No issue detected.", "must_escalate": False, "confidence": 0.9}))',
                "        return 0",
                "    if instruction.startswith('analyze') or instruction.startswith('inspect'):",
                '        action = {"type": "complete", "message": "analysis validated exit_code=0"}',
                "    else:",
                '        action = {"type": "complete", "message": "validation completed exit_code=0"}',
                '    print(json.dumps({"summary": "stub response", "action": action}))',
                "    return 0",
                "",
                "if __name__ == '__main__':",
                "    raise SystemExit(main())",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _recovery_handoff_payload(task: str) -> ProjectHandoff:
    return ProjectHandoff(
        task=task,
        status="exception",
        current_step_id="step-2",
        current_step_title="2. Implement a fix",
        current_step_status="failed",
        latest_observation="tests failed after patch",
        plan_status="step-1:completed,step-2:failed,step-3:planned",
        risk_register=[
            {"risk": "regression remains after failed patch", "status": "open"},
        ],
        issue_register=[
            {"step_id": "step-2", "severity": "high", "summary": "tests still failing", "status": "open"},
        ],
        exception_plan=["review failing test output", "prepare corrective patch"],
    )


def _agent_case_recovery_gate(case: Prince2BenchmarkCase) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        stub = _write_agent_success_stub(root)
        handoff = _recovery_handoff_payload(case.prompt)
        case_runtime = _build_case_runtime_handoff(case)
        handoff.sync_prince2_role_tree_baseline(dict(case_runtime.prince2_role_tree_baseline))
        handoff.prince2_node_runtime = json.loads(json.dumps(case_runtime.prince2_node_runtime))
        handoff.save(root / ".stagewarden_handoff.json")
        with _temp_run_model_env(stub):
            agent = Agent(AgentConfig(workspace_root=root, max_steps=10, verbose=False))
            result = agent.run(case.prompt)
        saved = ProjectHandoff.load(root / ".stagewarden_handoff.json")
    passed = (
        result.ok
        and saved.exception_plan == []
        and all(item.get("status") == "closed" for item in saved.issue_register)
        and all(item.get("status") == "closed" for item in saved.risk_register)
        and "recovery-step-1:completed" in saved.plan_status
        and "recovery-step-2:completed" in saved.plan_status
    )
    return {
        "passed": passed,
        "summary": "recovery lane clears exception controls and closes the gate",
        "observed": {
            "ok": result.ok,
            "exception_plan": list(saved.exception_plan),
            "plan_status": saved.plan_status,
            "message": result.message,
        },
        "expected": {
            "ok": True,
            "exception_plan": [],
            "closed_issues": True,
            "closed_risks": True,
            "recovery_steps": "completed",
        },
        "node_runtime_source": saved,
    }


def _executor_case_recovery_prompt_packet(case: Prince2BenchmarkCase) -> dict[str, Any]:
    step = PlanStep(
        id="recovery-step-1",
        title="Stabilize recovery lane",
        instruction=case.prompt,
        validation="Recovery evidence exists and the exception plan can be cleared.",
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        executor, handoff = _build_executor_harness(
            root=Path(tmp_dir),
            task=case.prompt,
            step=step,
            outputs=[
                _primary_output(message="recovery completed exit_code=0"),
                _critic_output(
                    verdict="accept",
                    contradictions=[],
                    missing_evidence=[],
                    counter_argument="No issue detected.",
                    must_escalate=False,
                    confidence=0.9,
                ),
            ],
        )
        outcome = executor.execute_step(task=case.prompt, step=step, plan=[step], iteration=1, last_observation="exception plan active")
    prompt = handoff.calls[0] if handoff.calls else ""
    runtime_source = getattr(executor, "project_handoff", None)
    passed = (
        outcome.ok
        and "recovery_state:" in prompt
        and "PRINCE2 node AI context packet" in prompt
        and "active_flow_rule: context moves only through approved PRINCE2 flow edges" in prompt
        and "core_agent_capabilities: shell=true files=true git=true wet_run_required=true" in prompt
    )
    return {
        "passed": passed,
        "summary": "recovery prompt packet includes recovery state and flow context",
        "observed": {
            "ok": outcome.ok,
            "prompt_excerpt": prompt[:1200],
        },
        "expected": {
            "ok": True,
            "contains": [
                "recovery_state:",
                "PRINCE2 node AI context packet",
                "active_flow_rule: context moves only through approved PRINCE2 flow edges",
                "core_agent_capabilities: shell=true files=true git=true wet_run_required=true",
            ],
        },
        "node_runtime_source": runtime_source,
    }


_CASE_RUNNERS: dict[str, Callable[[Prince2BenchmarkCase], dict[str, Any]]] = {
    "checklist_structure": _policy_case_checklist_structure,
    "vague_task_rejected": _policy_case_vague_rejection,
    "escalation_trigger": _policy_case_escalation_trigger,
    "critic_accept": _executor_case_accept,
    "critic_block": _executor_case_block,
    "critic_invalid": _executor_case_invalid_critic,
    "wet_run_required": _executor_case_wet_run_required,
    "prompt_context": _executor_case_prompt_packet,
    "recovery_gate": _agent_case_recovery_gate,
    "recovery_prompt_context": _executor_case_recovery_prompt_packet,
}
