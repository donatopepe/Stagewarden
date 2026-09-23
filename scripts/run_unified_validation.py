#!/usr/bin/env python3
"""Run Stagewarden's fixed-order unified wet validation matrix."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "tests" / "data" / "unified_validation_matrix.json"


def load_matrix(path: Path = MATRIX_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("gates"), list):
        raise ValueError("unified validation matrix requires gates list")
    gates = payload["gates"]
    ids = [str(item.get("id", "")) for item in gates if isinstance(item, dict)]
    if len(ids) != len(gates) or any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("unified validation gate IDs must be unique and non-empty")
    for gate in gates:
        if not isinstance(gate, dict) or not isinstance(gate.get("expect"), dict):
            raise ValueError("each gate requires expect object")
        if not isinstance(gate.get("command", gate.get("commands")), list):
            raise ValueError(f"gate {gate.get('id')!r} requires command or commands")
    return payload


def _run(command: list[str], *, cwd: Path, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(ROOT), os.environ.get("PYTHONPATH", "")] ))},
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _json_ok(stdout: str) -> bool:
    try:
        json.loads(stdout)
    except json.JSONDecodeError:
        return False
    return True


def _evaluate(gate: dict[str, Any], runs: list[dict[str, Any]]) -> tuple[bool, str]:
    expect = gate["expect"]
    for run in runs:
        if run["returncode"] != int(expect.get("returncode", 0)):
            return False, f"returncode={run['returncode']}"
        contains = expect.get("stdout_contains")
        if contains and str(contains) not in run["stdout"]:
            return False, f"stdout missing {contains!r}"
        if expect.get("json") and not _json_ok(run["stdout"]):
            return False, "stdout is not JSON"
        json_expect = expect.get("json") if isinstance(expect.get("json"), dict) else {}
        if json_expect:
            try:
                payload = json.loads(run["stdout"])
            except json.JSONDecodeError:
                return False, "stdout is not JSON"
            for path, expected in json_expect.items():
                value: Any = payload
                for part in str(path).split("."):
                    if not isinstance(value, dict) or part not in value:
                        return False, f"JSON path missing {path}"
                    value = value[part]
                if value != expected:
                    return False, f"JSON {path}={value!r}, expected {expected!r}"
    return True, "ok"


def run_matrix(*, timeout: int = 1800) -> dict[str, Any]:
    matrix = load_matrix()
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="stagewarden-unified-") as tmp:
        cli_cwd = Path(tmp)
        for gate in matrix["gates"]:
            commands = gate.get("commands") if isinstance(gate.get("commands"), list) else [gate["command"]]
            runs = []
            for command in commands:
                run = _run([str(item) for item in command], cwd=cli_cwd if gate["id"] == "cli_smoke" else ROOT, timeout=timeout)
                runs.append(run)
            passed, detail = _evaluate(gate, runs)
            results.append({
                "id": gate["id"],
                "label": gate.get("label", gate["id"]),
                "passed": passed,
                "detail": detail,
                "runs": [
                    {
                        **run,
                        "stdout": run["stdout"][-4000:],
                        "stderr": run["stderr"][-4000:],
                    }
                    for run in runs
                ],
            })
            if not passed:
                break
    passed_count = sum(1 for item in results if item["passed"])
    return {
        "command": "unified validation",
        "matrix": str(MATRIX_PATH.relative_to(ROOT)),
        "gate_count": len(matrix["gates"]),
        "executed": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "passed": len(results) == len(matrix["gates"]) and passed_count == len(matrix["gates"]),
        "gates": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    if args.list:
        print(json.dumps(load_matrix(), indent=2))
        return 0
    report = run_matrix(timeout=args.timeout)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
