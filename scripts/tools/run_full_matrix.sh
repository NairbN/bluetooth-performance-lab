#!/bin/bash
# Wrapper around scripts/ble/run_full_matrix.py with sensible defaults.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -d ".venv" ]]; then
  echo "[run_full_matrix] .venv not found. Run ./scripts/tools/setup_linux_a.sh first." >&2
  exit 1
fi

source .venv/bin/activate

DEFAULT_ARGS=(
  --phys auto
  --payloads 20 60 120 180 244
  --repeats 2
  --duration_s 30
  --latency_iterations 5
  --rssi_samples 20
  --note "LinuxA+MockRing"
  --prompt
)

python scripts/ble/run_full_matrix.py "${DEFAULT_ARGS[@]}" "$@"
