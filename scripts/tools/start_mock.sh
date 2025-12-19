#!/bin/bash
# Convenience wrapper to launch the mock DUT peripheral with recommended defaults.
set -euo pipefail

# Re-run via sudo if necessary so BlueZ APIs are available.
if [[ $EUID -ne 0 ]]; then
  exec sudo "$0" "$@"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -d ".venv" ]]; then
  echo "[start_mock] .venv not found. Run ./scripts/tools/setup_linux_b.sh first." >&2
  exit 1
fi

source .venv/bin/activate

DEFAULT_ARGS=(
  --adapter hci0
  --advertise_name MockRingDemo
  --payload_bytes 160
  --notify_hz 40
  --quiet
  --log logs/mock_dut.log
)

python scripts/ble/mock_dut_peripheral.py "${DEFAULT_ARGS[@]}" "$@"
