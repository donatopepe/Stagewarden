#!/usr/bin/env python3
"""Run Stagewarden battery simulations from canonical data/simulation_matrix.json."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "data" / "simulation_matrix.json"


def load_matrix(path: Path = MATRIX_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("simulation matrix must be a JSON object")
    scenarios = payload.get("scenarios")
    categories = payload.get("categories")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("simulation matrix requires non-empty scenarios")
    if not isinstance(categories, list) or not categories:
        raise ValueError("simulation matrix requires non-empty categories")
    ids = [str(item.get("id", "")) for item in scenarios if isinstance(item, dict)]
    if len(ids) != len(set(ids)) or any(not item for item in ids):
        raise ValueError("simulation matrix scenario IDs must be unique and non-empty")
    known = set(ids)
    category_ids: set[str] = set()
    for category in categories:
        if not isinstance(category, dict):
            raise ValueError("simulation matrix category must be an object")
        category_id = str(category.get("id", ""))
        if not category_id or category_id in category_ids:
            raise ValueError("simulation matrix category IDs must be unique and non-empty")
        category_ids.add(category_id)
        listed = category.get("scenario_ids")
        if not isinstance(listed, list) or not listed:
            raise ValueError(f"category {category_id!r} requires scenario_ids")
        if any(str(item) not in known for item in listed):
            raise ValueError(f"category {category_id!r} references unknown scenario")
    scenario_categories = {str(item.get("id")): str(item.get("category", "")) for item in scenarios if isinstance(item, dict)}
    if set(scenario_categories.values()) != category_ids:
        raise ValueError("every scenario category must reference a declared category")
    for category in categories:
        category_id = str(category["id"])
        listed = {str(item) for item in category["scenario_ids"]}
        actual = {scenario_id for scenario_id, value in scenario_categories.items() if value == category_id}
        if listed != actual:
            raise ValueError(f"category {category_id!r} does not match scenario category assignments")
    return payload


def _run_battery(*, workspace: Path, scenario_ids: list[str] | None = None) -> tuple[int, dict[str, Any]]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT), env.get("PYTHONPATH", "")]))
    command = [sys.executable, "-m", "stagewarden.main", "battery", "--json"]
    if scenario_ids is not None:
        env["STAGEWARDEN_BATTERY_SCENARIOS"] = ",".join(scenario_ids)
    completed = subprocess.run(
        command,
        cwd=workspace,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        report = {
            "command": "battery",
            "ready": False,
            "error": f"battery emitted invalid JSON: {exc}",
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
        return completed.returncode or 1, report
    if not isinstance(report, dict):
        return completed.returncode or 1, {"command": "battery", "ready": False, "error": "battery report is not an object"}
    return completed.returncode, report


def _scenario_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = report.get("simulations", [])
    if not isinstance(items, list):
        return {}
    return {str(item.get("name")): item for item in items if isinstance(item, dict) and item.get("name")}


def _selection(matrix: dict[str, Any], *, scenario_id: str | None, category: str | None) -> list[str]:
    scenarios = [item for item in matrix["scenarios"] if isinstance(item, dict)]
    if scenario_id:
        selected = [item for item in scenarios if str(item.get("id")) == scenario_id]
        if not selected:
            raise ValueError(f"unknown scenario: {scenario_id}")
        return [scenario_id]
    if category:
        selected = [item for item in scenarios if str(item.get("category")) == category]
        if not selected:
            raise ValueError(f"unknown or empty category: {category}")
        return [str(item["id"]) for item in selected]
    return [str(item["id"]) for item in scenarios]


def build_report(matrix: dict[str, Any], battery: dict[str, Any], *, selection: list[str], mode: str) -> dict[str, Any]:
    observed = _scenario_map(battery)
    cases: list[dict[str, Any]] = []
    for scenario_id in selection:
        item = observed.get(scenario_id)
        if item is None:
            cases.append({"id": scenario_id, "status": "missing", "ok": False})
            continue
        cases.append({
            "id": scenario_id,
            "status": "pass" if item.get("ok") else "fail",
            "ok": bool(item.get("ok")),
            "message": str(item.get("message", "")),
            "duration_ms": item.get("duration_ms", 0),
        })
    passed = sum(1 for case in cases if case["ok"])
    failed = len(cases) - passed
    return {
        "command": "simulation matrix",
        "matrix": {
            "path": str(MATRIX_PATH),
            "version": matrix.get("_version", 1),
            "scenario_count": len(matrix["scenarios"]),
            "category_count": len(matrix["categories"]),
        },
        "selection": {"mode": mode, "scenario_ids": selection, "count": len(selection)},
        "execution": {
            "runner": "stagewarden battery",
            "battery_ready": bool(battery.get("ready")),
            "battery_total": battery.get("total"),
            "battery_passed": battery.get("passed"),
            "battery_failed": battery.get("failed"),
        },
        "cases": cases,
        "coverage": {
            "selected": len(cases),
            "observed": sum(1 for case in cases if case["status"] != "missing"),
            "passed": passed,
            "failed": failed,
            "rate": round(passed / len(cases), 3) if cases else 0.0,
        },
        "passed": failed == 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scenario", help="Run one matrix scenario ID.")
    group.add_argument("--category", help="Run all scenarios in one matrix category.")
    parser.add_argument("--list", action="store_true", help="List matrix scenarios and categories without running battery.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON (default).")
    args = parser.parse_args(argv)
    try:
        matrix = load_matrix()
        if args.list:
            report = {
                "command": "simulation matrix list",
                "matrix": {"path": str(MATRIX_PATH), "version": matrix.get("_version", 1)},
                "categories": matrix["categories"],
                "scenarios": matrix["scenarios"],
                "coverage": {"scenario_count": len(matrix["scenarios"]), "category_count": len(matrix["categories"])},
                "passed": True,
            }
        else:
            selection = _selection(matrix, scenario_id=args.scenario, category=args.category)
            mode = "total" if not args.scenario and not args.category else ("scenario" if args.scenario else "category")
            with tempfile.TemporaryDirectory(prefix="stagewarden-matrix-") as tmp:
                _, battery = _run_battery(workspace=Path(tmp), scenario_ids=selection)
            report = build_report(matrix, battery, selection=selection, mode=mode)
    except (OSError, ValueError) as exc:
        report = {"command": "simulation matrix", "passed": False, "error": str(exc)}
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
