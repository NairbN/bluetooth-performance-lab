#!/bin/bash
# Wrapper for the throughput-only sweep.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -d ".venv" ]]; then
  echo "[run_throughput_matrix.sh] .venv not found. Run ./scripts/tools/setup_linux_a.sh first." >&2
  exit 1
fi

pyscript="scripts/ble/run_throughput_matrix.py"

source .venv/bin/activate

DEFAULT_ARGS=(
  --payloads 20 60 120 180 244
  --repeats 3
  --duration_s 30
)

python "$pyscript" "${DEFAULT_ARGS[@]}" "$@"
