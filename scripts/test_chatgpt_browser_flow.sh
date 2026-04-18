#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
STORE_DIR="${STAGEWARDEN_SECRET_STORE_DIR:-/tmp/stagewarden-chatgpt-browser-flow}"

rm -rf "$STORE_DIR"
mkdir -p "$STORE_DIR"

echo "[1/3] Simulated browser login for chatgpt profile"
STAGEWARDEN_SECRET_STORE_DIR="$STORE_DIR" \
STAGEWARDEN_SKIP_BROWSER=1 \
STAGEWARDEN_AUTH_AUTO_CALLBACK_TOKEN="chatgpt-browser-session-token" \
python3 -m stagewarden.main --interactive <<'EOF'
account login chatgpt personale
accounts
exit
EOF

echo
echo "[2/3] Reading stored token from secret store"
STAGEWARDEN_SECRET_STORE_DIR="$STORE_DIR" python3 - <<'PY'
from stagewarden.secrets import SecretStore
loaded = SecretStore().load_token("chatgpt", "personale")
print({"ok": loaded.ok, "message": loaded.message, "secret": loaded.secret})
PY

echo
echo "[3/3] Verifying backend token injection via HandoffManager"
STAGEWARDEN_SECRET_STORE_DIR="$STORE_DIR" python3 - <<'PY'
import os
import tempfile
import textwrap
from pathlib import Path

from stagewarden.handoff import HandoffManager, format_run_model

with tempfile.TemporaryDirectory() as tmp_dir:
    stub = Path(tmp_dir) / "run_model_test_stub"
    stub.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            print(json.dumps({
                "account": os.environ.get("STAGEWARDEN_MODEL_ACCOUNT", ""),
                "target": os.environ.get("STAGEWARDEN_MODEL_TARGET", ""),
                "token": os.environ.get("CHATGPT_TOKEN", ""),
            }))
            """
        )
    )
    stub.chmod(0o755)
    os.environ["RUN_MODEL_BIN"] = str(stub)
    result = HandoffManager(timeout_seconds=5).execute(format_run_model("chatgpt", "prompt", account="personale"))
    print({"ok": result.ok, "output": result.output, "error": result.error})
PY

echo
echo "Smoke test completed."
