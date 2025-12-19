#!/bin/bash
# Prepare Linux A (central) environment: venv + Python deps + basic BLE checks.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -d ".venv" ]]; then
  python3 -m venv --system-site-packages .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install bleak dbus-next matplotlib

echo
echo "[setup_linux_a] Environment ready. Remember to ensure:"
echo "  * Your user is in the 'bluetooth' group (sudo usermod -aG bluetooth \$USER)"
echo "  * Bluetooth adapter powered on: 'bluetoothctl power on'"
echo "  * Run './scripts/tools/run_full_matrix.sh --help' for usage"
