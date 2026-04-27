#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export PYTHONPATH="$ROOT:$PYTHONPATH"
echo "Bootstrapping tests with PYTHONPATH=$PYTHONPATH"
python3 -m unittest discover -s tests -v
