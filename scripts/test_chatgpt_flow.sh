#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
STORE_DIR="${STAGEWARDEN_SECRET_STORE_DIR:-/tmp/stagewarden-chatgpt-smoke}"
RUN_STUB_DIR="$(mktemp -d)"
RUN_STUB="$RUN_STUB_DIR/run_model_test_stub"

cleanup() {
  rm -rf "$RUN_STUB_DIR"
}
trap cleanup EXIT INT TERM

cat > "$RUN_STUB" <<'EOF'
#!/usr/bin/env python3
import json
import os
print(json.dumps({
    "account": os.environ.get("STAGEWARDEN_MODEL_ACCOUNT", ""),
    "target": os.environ.get("STAGEWARDEN_MODEL_TARGET", ""),
    "token": os.environ.get("CHATGPT_TOKEN", ""),
}))
EOF
chmod +x "$RUN_STUB"

rm -rf "$STORE_DIR"
mkdir -p "$STORE_DIR"

echo "[1/3] Simulated Codex-style device login for chatgpt profile"
LOGIN_OUTPUT=$(
  printf 'account login chatgpt personale\naccounts\nmodels\nexit\n' | \
    STAGEWARDEN_SECRET_STORE_DIR="$STORE_DIR" \
    STAGEWARDEN_OPENAI_CLIENT_ID="client-id" \
    PYTHONPATH="$PROJECT_DIR" \
    python3 - <<'PY'
from io import StringIO
from pathlib import Path

from stagewarden.auth import AuthResult
from stagewarden.config import AgentConfig
from stagewarden.main import run_interactive_shell
import stagewarden.main as main_module

original_run = main_module.OpenAIDeviceCodeFlow.run

def fake_run(self):
    return AuthResult(
        True,
        "Device code login completed.",
        token="access-token-123",
        secret_payload='{"access_token":"access-token-123","refresh_token":"refresh-token-123","id_token":"id-token-123"}',
    )

main_module.OpenAIDeviceCodeFlow.run = fake_run
try:
    input_stream = StringIO("account login chatgpt personale\naccounts\nmodels\nexit\n")
    output_stream = StringIO()
    run_interactive_shell(AgentConfig(workspace_root=Path("."), max_steps=1), input_stream=input_stream, output_stream=output_stream)
    print(output_stream.getvalue(), end="")
finally:
    main_module.OpenAIDeviceCodeFlow.run = original_run
PY
)
printf '%s\n' "$LOGIN_OUTPUT"

echo "[2/3] Reading stored token from secret store"
TOKEN_OUTPUT=$(
  STAGEWARDEN_SECRET_STORE_DIR="$STORE_DIR" \
    PYTHONPATH="$PROJECT_DIR" \
    python3 - <<'PY'
from stagewarden.secrets import SecretStore
loaded = SecretStore().load_token("chatgpt", "personale")
print({"ok": loaded.ok, "message": loaded.message, "secret": loaded.secret})
PY
)
printf '%s\n' "$TOKEN_OUTPUT"

echo "[3/3] Verifying backend token injection via HandoffManager"
HANDOFF_OUTPUT=$(
  RUN_MODEL_BIN="$RUN_STUB" \
  STAGEWARDEN_SECRET_STORE_DIR="$STORE_DIR" \
  PYTHONPATH="$PROJECT_DIR" \
    python3 - <<'PY'
from stagewarden.handoff import HandoffManager, format_run_model
result = HandoffManager(timeout_seconds=5).execute(
    format_run_model("chatgpt", "prompt", account="personale")
)
print({"ok": result.ok, "output": result.output, "error": result.error})
PY
)
printf '%s\n' "$HANDOFF_OUTPUT"

echo "Smoke test completed."
