#!/usr/bin/env python3
"""Minimal parser for  logs.

Usage:
  python3 scripts/parse_unittest_log.py test_run_log.txt

Outputs:
- Summary counts
- List of failing tests/modules
- Extracted traceback blocks (best-effort)
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass

TEST_HEADER = re.compile(r"^(?P<name>[^\s].*?)\s+\((?P<context>[^)]+)\)\s+\.{3}\s+(?P<result>ok|ERROR|FAIL|skipped)$")
TRACE_START = re.compile(r"^Traceback \(most recent call last\):\s*$")

@dataclass
class TestResult:
    name: str
    context: str
    result: str

def read_text(path: Path) -> str:
    if not path.exists():
        print(f"Log file not found: {path}", file=sys.stderr)
        sys.exit(2)
    return path.read_text(encoding="utf-8", errors="replace")

def parse_results(lines: list[str]) -> list[TestResult]:
    results: list[TestResult] = []
    for line in lines:
        m = TEST_HEADER.match(line.rstrip("\n"))
        if m:
            results.append(
                TestResult(
                    name=m.group("name").strip(),
                    context=m.group("context").strip(),
                    result=m.group("result").strip(),
                )
            )
    return results

def extract_tracebacks(text: str) -> list[str]:
    blocks: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if TRACE_START.match(lines[i]): # Found start of traceback
            start = i
            i += 1
            # Collect lines until a blank line or a new test header/separator, simplistic heuristic.
            while i < len(lines):
                if lines[i].strip() == "": # Break on first blank line signaling end of block
                    i += 1
                    break
                # Heuristic end: next traceback start OR separation headers
                if TRACE_START.match(lines[i]) or re.match(r"^==+$", lines[i]):
                    break
                i += 1
            blocks.append("\n".join(lines[start:i]).strip())
            continue # Continue searching after the collected block
        i += 1
    return [b for b in blocks if b] # Filter out any empty blocks

def main():
    log_path_str = "test_run_log.txt"
    if len(sys.argv) > 1:
        log_path_str = sys.argv[1]

    log_path = Path(log_path_str).expanduser()
    text = read_text(log_path)
    lines = text.splitlines()

    results = parse_results(lines)
    counts = {"ok": 0, "FAIL": 0, "ERROR": 0, "skipped": 0}
    for r in results:
        counts[r.result] = counts.get(r.result, 0) + 1

    failing = [r for r in results if r.result in {"FAIL", "ERROR"}]

    print("=== unittest log summary ===")
    print(f"logfile: {log_path}")
    print(f"tests seen: {len(results)}")
    print("counts:")
    for k in ("ok", "FAIL", "ERROR", "skipped"):
        print(f"  {k}: {counts.get(k, 0)}")

    print("\n=== failing tests (name | context | result) ===")
    if not failing:
        print("(none)")
    else:
        for r in failing:
            print(f"- {r.name} | {r.context} | {r.result}")

    tb_blocks = extract_tracebacks(text)
    if tb_blocks:
        print("\n=== extracted tracebacks (best-effort) ===")
        # Print up to 5 blocks to keep it readable
        for idx, block in enumerate(tb_blocks[:5], start=1):
            print(f"\n--- traceback {idx}/{min(5, len(tb_blocks))} ---")
            print(block)

        if len(tb_blocks) > 5:
            print(f"\n(note: {len(tb_blocks)} total traceback blocks; showing first 5)")

if __name__ == "__main__":
    main()
