#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SMOKE_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$SMOKE_DIR"
}
trap cleanup EXIT INT TERM

echo "[1/1] Running live OpenRouter benchmark baseline"
PYTHONPATH="$PROJECT_DIR" PROJECT_DIR="$PROJECT_DIR" SMOKE_DIR="$SMOKE_DIR" python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path
from textwrap import dedent

from stagewarden.provider_registry import model_token_env

env_name = model_token_env().get("cheap") or "OPENROUTER_API_KEY"
token = os.environ.get(env_name) or os.environ.get("OPENROUTER_API_KEY")
if not token:
    raise SystemExit("OpenRouter API key is required for this smoke test.")

smoke_dir = Path(os.environ["SMOKE_DIR"])
fixed_model = "google/gemini-3.1-pro-preview"
stub = smoke_dir / "run_model_test_stub"
stub.write_text(
    dedent(
        f"""\
        #!/usr/bin/env python3
        from __future__ import annotations

        import json
        import os
        import sys
        import urllib.request


        def main() -> int:
            if len(sys.argv) < 3:
                print(json.dumps({{"error": "usage: stub <model> <prompt>"}}))
                return 1

            requested_model = sys.argv[1]
            prompt = sys.argv[2]
            api_key = os.environ.get("{env_name}", "")
            if not api_key:
                print(json.dumps({{"error": "missing {env_name}"}}))
                return 1

            payload = {{
                "model": "{fixed_model}",
                "messages": [
                    {{"role": "system", "content": "Answer with only one letter: A, B, C, or D."}},
                    {{"role": "user", "content": prompt}},
                ],
                "max_tokens": 256,
                "temperature": 0,
            }}
            request = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={{
                    "Authorization": f"Bearer {{api_key}}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://stagewarden.local",
                    "X-Title": "Stagewarden tests",
                }},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)

            choices = data.get("choices") or []
            message = choices[0].get("message") if choices else {{}}
            content = str((message or {{}}).get("content") or (message or {{}}).get("reasoning") or "").strip()
            print(json.dumps({{
                "account": os.environ.get("STAGEWARDEN_MODEL_ACCOUNT", ""),
                "target": os.environ.get("STAGEWARDEN_MODEL_TARGET", ""),
                "requested_model": requested_model,
                "routed_model": data.get("model", ""),
                "content": content,
                "usage": data.get("usage", {{}}),
                "action": {{"type": "complete", "message": content or "OpenRouter call completed."}},
            }}))
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        """
    )
)
stub.chmod(0o755)

output_path = Path(os.environ["SMOKE_DIR"]) / "openrouter-benchmark.json"
history_path = Path(os.environ["SMOKE_DIR"]) / "openrouter-benchmark-history.jsonl"
env = dict(os.environ)
env["PYTHONPATH"] = os.environ.get("PYTHONPATH", "")
env["RUN_MODEL_BIN"] = str(stub)
completed = subprocess.run(
    [
        "python3",
        "-m",
        "stagewarden.main",
        "--openrouter-benchmark",
        "--openrouter-benchmark-output",
        str(output_path),
        "--openrouter-benchmark-history",
        str(history_path),
    ],
    cwd=Path(os.environ["PROJECT_DIR"]),
    env=env,
    capture_output=True,
    text=True,
    timeout=300,
    check=False,
)
if completed.returncode != 0:
    raise SystemExit(completed.stderr or completed.stdout or "OpenRouter benchmark CLI failed.")

payload = json.loads(completed.stdout)
if payload.get("command") != "openrouter benchmark":
    raise SystemExit("Benchmark CLI did not report the expected command.")
if payload.get("schema", {}).get("name") != "stagewarden.openrouter_benchmark":
    raise SystemExit("Benchmark CLI did not emit the shared schema.")
if not payload.get("suites", {}).get("general", {}).get("passed"):
    raise SystemExit("General OpenRouter baseline did not pass.")
if not payload.get("suites", {}).get("reasoning", {}).get("passed"):
    raise SystemExit("Reasoning OpenRouter baseline did not pass.")
if not payload.get("suites", {}).get("truthfulness", {}).get("passed"):
    raise SystemExit("Truthfulness OpenRouter baseline did not pass.")
if not payload.get("overall", {}).get("passed"):
    raise SystemExit("Overall OpenRouter benchmark baseline did not pass.")
if not payload.get("history", {}).get("enabled"):
    raise SystemExit("Benchmark history tracking was not enabled.")
if not payload.get("history", {}).get("appended"):
    raise SystemExit("Benchmark history snapshot was not appended.")
if payload.get("overall", {}).get("regressed"):
    raise SystemExit("Benchmark reported an unexpected regression on the initial run.")
if payload.get("overall", {}).get("total_cases") != 9:
    raise SystemExit("Benchmark CLI reported an unexpected case count.")
if payload.get("overall", {}).get("suite_count") != 3:
    raise SystemExit("Benchmark CLI reported an unexpected suite count.")
if not output_path.exists():
    raise SystemExit("Benchmark output file was not written.")
if not history_path.exists():
    raise SystemExit("Benchmark history file was not written.")

saved = json.loads(output_path.read_text(encoding="utf-8"))
if saved.get("command") != "openrouter benchmark":
    raise SystemExit("Benchmark output file did not contain the expected command.")

print(f"OpenRouter env used: {env_name}")
print("Backend runner confirmed real OpenRouter benchmark suite.")
print("OpenRouter benchmark smoke test completed.")
PY
