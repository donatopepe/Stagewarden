#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SMOKE_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$SMOKE_DIR"
}
trap cleanup EXIT INT TERM

echo "[1/1] Verifying OpenRouter API key wiring"
PYTHONPATH="$PROJECT_DIR" SMOKE_DIR="$SMOKE_DIR" python3 - <<'PY'
import json
import os
import re
from pathlib import Path
from textwrap import dedent

from stagewarden.handoff import HandoffManager, format_run_model
from stagewarden.provider_registry import model_token_env

env_name = model_token_env().get("cheap") or "OPENROUTER_API_KEY"
token = os.environ.get(env_name) or os.environ.get("OPENROUTER_API_KEY")
if not token:
    raise SystemExit("OpenRouter API key is required for this smoke test.")

smoke_dir = Path(os.environ["SMOKE_DIR"])
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
                "model": "openrouter/auto",
                "messages": [
                    {{"role": "system", "content": "Answer with only one letter: A, B, C, or D."}},
                    {{"role": "user", "content": prompt}},
                ],
                "max_tokens": 256,
                "temperature": 0,
                "plugins": [
                    {{
                        "id": "auto-router",
                        "allowed_models": [
                            "anthropic/claude-sonnet-4.5",
                            "openai/gpt-5.1",
                            "google/gemini-3.1-pro-preview",
                        ],
                    }}
                ],
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

os.environ["RUN_MODEL_BIN"] = str(stub)
manager = HandoffManager(timeout_seconds=5)
manager.account_env_by_target = {f"cheap:live": env_name}
prompt = "\n".join(
    [
        "What is the embryological origin of the hyoid bone?",
        "A. The first pharyngeal arch",
        "B. The first and second pharyngeal arches",
        "C. The second pharyngeal arch",
        "D. The second and third pharyngeal arches",
        "Answer:",
    ]
)
result = manager.execute(format_run_model("cheap", prompt, account="live"))

if not result.ok:
    raise SystemExit(result.error or "OpenRouter smoke test failed.")
payload = json.loads(result.output)
if payload.get("account") != "live":
    raise SystemExit("Backend runner did not receive the expected account.")
if payload.get("target") != "cheap:live":
    raise SystemExit("Backend runner did not receive the expected target.")
if payload.get("requested_model") != "cheap":
    raise SystemExit("Backend runner did not receive the expected model.")
if not payload.get("routed_model"):
    raise SystemExit("OpenRouter did not return a routed model.")
if not payload.get("content"):
    raise SystemExit("OpenRouter did not return content.")
matches = re.findall(r"\b([ABCD])\b", payload["content"].upper())
if not matches or matches[-1] != "D":
    raise SystemExit(f"OpenRouter benchmark answer was unexpected: {payload['content']!r}")
usage = payload.get("usage") or {}
if int(usage.get("total_tokens", 0)) <= 0:
    raise SystemExit("OpenRouter usage metadata was not returned.")

print(f"OpenRouter env used: {env_name}")
print("Backend runner confirmed real OpenRouter call.")
print("OpenRouter smoke test completed.")
PY
