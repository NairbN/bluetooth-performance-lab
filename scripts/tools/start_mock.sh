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

if command -v bluetoothctl >/dev/null 2>&1; then
  if ! bluetoothctl show | grep -q "Powered: yes"; then
    echo "[start_mock] WARNING: adapter not powered (bluetoothctl show). Enable it or advertisement may fail." >&2
  fi
  if ! bluetoothctl show | grep -qi "ExperimentalFeatures"; then
    echo "[start_mock] NOTE: bluetoothd experimental flags not detected; GATT/advertising may require --experimental." >&2
  fi
fi

DEFAULT_ARGS=(
  --adapter hci0
  --advertise_name MockRingDemo
  --payload_bytes 160
  --rssi_uuid 12345678-1234-5678-1234-56789abcdef3
  --mock_rssi_base_dbm -55
  --mock_rssi_variation 5
  --notify_hz 40
  --quiet
  --log logs/mock_dut.log
)

python scripts/ble/mock/cli.py "${DEFAULT_ARGS[@]}" "$@"
