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

echo "[1/3] Simulated Stagewarden login for chatgpt profile"
LOGIN_OUTPUT=$(
  printf 'account login chatgpt personale\naccounts\nmodels\nexit\n' | \
    STAGEWARDEN_SECRET_STORE_DIR="$STORE_DIR" \
    STAGEWARDEN_SKIP_BROWSER=1 \
    STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN="chatgpt-session-token" \
    PYTHONPATH="$PROJECT_DIR" \
    python3 -m stagewarden.main --interactive --max-steps 1
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
