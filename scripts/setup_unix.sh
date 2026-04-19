#!/usr/bin/env sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.11+ first." >&2
  exit 1
fi

USER_BIN=$("$PYTHON_BIN" - <<'PY'
import site
print(site.USER_BASE + "/bin")
PY
)

if ! command -v git >/dev/null 2>&1; then
  echo "git not found. Install git before installing Stagewarden." >&2
  exit 1
fi

INSTALL_MODE="editable"
if ! "$PYTHON_BIN" -m pip install --user -e "$PROJECT_DIR"; then
  INSTALL_MODE="source launcher"
  mkdir -p "$USER_BIN"
  cat > "$USER_BIN/stagewarden" <<EOF
#!/usr/bin/env sh
PYTHONPATH="$PROJECT_DIR:\${PYTHONPATH:-}" exec "$PYTHON_BIN" -m stagewarden.main "\$@"
EOF
  chmod +x "$USER_BIN/stagewarden"
  echo "Editable install failed; installed source launcher fallback."
fi

case ":$PATH:" in
  *":$USER_BIN:"*) ;;
  *)
    echo ""
    echo "Add this to your shell profile if stagewarden is not found:"
    echo "export PATH=\"$USER_BIN:\$PATH\""
    ;;
esac

echo "Stagewarden installed ($INSTALL_MODE)."
echo "Run: stagewarden"
if "$PYTHON_BIN" -m stagewarden.main doctor >/dev/null 2>&1; then
  echo "Post-install check: stagewarden doctor OK"
else
  echo "Next: run 'stagewarden doctor' to validate Python, git, PATH, repo, and provider setup."
fi
