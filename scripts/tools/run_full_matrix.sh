#!/bin/bash
# Wrapper around scripts/ble/clients/run_full_matrix.py with sensible defaults.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -d ".venv" ]]; then
  echo "[run_full_matrix] .venv not found. Run ./scripts/tools/setup_linux_a.sh first." >&2
  exit 1
fi

source .venv/bin/activate

if command -v bluetoothctl >/dev/null 2>&1; then
  if ! bluetoothctl show | grep -q "Powered: yes"; then
    echo "[run_full_matrix] WARNING: adapter not powered (bluetoothctl show). Enable it or runs may fail." >&2
  fi
else
  echo "[run_full_matrix] WARNING: bluetoothctl not found; skipping adapter preflight." >&2
fi

DEFAULT_ARGS=(
  --phys coded auto
  --payloads 20 60 120 180 244
  --repeats 2
  --duration_s 30
  --latency_iterations 5
  --rssi_samples 20
  --note "LinuxA+MockRing"
  --prompt
)

python scripts/ble/clients/run_full_matrix.py "${DEFAULT_ARGS[@]}" "$@"
