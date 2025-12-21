#!/bin/bash
# Wrapper for the throughput-only sweep.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -d ".venv" ]]; then
  echo "[run_throughput_matrix.sh] .venv not found. Run ./scripts/tools/setup_linux_a.sh first." >&2
  exit 1
fi

pyscript="scripts/ble/clients/run_throughput_matrix.py"

source .venv/bin/activate
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="$REPO_ROOT:${PYTHONPATH:-}"

if command -v bluetoothctl >/dev/null 2>&1; then
  if ! bluetoothctl show | grep -q "Powered: yes"; then
    echo "[run_throughput_matrix] WARNING: adapter not powered (bluetoothctl show). Enable it or runs may fail." >&2
  fi
fi

DEFAULT_ARGS=(
  --payloads 20 60 120 180 244
  --repeats 3
  --duration_s 30
)

"$PYTHON_BIN" -m scripts.ble.clients.run_throughput_matrix "${DEFAULT_ARGS[@]}" "$@"
