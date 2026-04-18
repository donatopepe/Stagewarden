#!/usr/bin/env sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.11+ first." >&2
  exit 1
fi

"$PYTHON_BIN" -m pip install --user -e "$PROJECT_DIR"

USER_BIN=$("$PYTHON_BIN" - <<'PY'
import site
print(site.USER_BASE + "/bin")
PY
)

case ":$PATH:" in
  *":$USER_BIN:"*) ;;
  *)
    echo ""
    echo "Add this to your shell profile if stagewarden is not found:"
    echo "export PATH=\"$USER_BIN:\$PATH\""
    ;;
esac

echo "Stagewarden installed."
echo "Run: stagewarden"
