#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export RUN_MODEL_BIN="${RUN_MODEL_BIN:-$repo_root/scripts/run_model_omniroute.py}"
export STAGEWARDEN_OMNIROUTE_MODEL="${STAGEWARDEN_OMNIROUTE_MODEL:-auto/coding:free}"

response="$($RUN_MODEL_BIN cheap 'Reply with exactly STAGEWARDEN_FREE_OK')"
if [[ "$response" != *STAGEWARDEN_FREE_OK* ]]; then
  printf 'Unexpected OmniRoute response: %s\n' "$response" >&2
  exit 1
fi
printf 'OmniRoute free route OK (%s)\n' "$STAGEWARDEN_OMNIROUTE_MODEL"
