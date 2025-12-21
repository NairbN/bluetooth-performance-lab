#!/bin/bash
# Helper to prepare Linux B for running the BLE mock + central tooling.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -d ".venv" ]]; then
  python3 -m venv --system-site-packages .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install bleak dbus-next matplotlib

sudo install -d /etc/systemd/system/bluetooth.service.d
sudo tee /etc/systemd/system/bluetooth.service.d/override.conf >/dev/null <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/libexec/bluetooth/bluetoothd --experimental
EOF

sudo tee /etc/dbus-1/system.d/org.bluez.example.conf >/dev/null <<'EOF'
<!DOCTYPE busconfig PUBLIC
  "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
  "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <policy user="root">
    <allow own="org.bluez.example"/>
    <allow own_prefix="org.bluez.example"/>
  </policy>
  <policy group="bluetooth">
    <allow own="org.bluez.example"/>
    <allow own_prefix="org.bluez.example"/>
  </policy>
</busconfig>
EOF

sudo systemctl daemon-reload
sudo systemctl restart bluetooth

echo
echo "[setup_linux_b] Bluetoothd restarted with --experimental."
echo "  * Ensure adapter is powered: 'bluetoothctl power on'"
echo "  * After the central connects, you can verify RSSI is exposed with:"
echo "      bluetoothctl info <CENTRAL_MAC> | grep RSSI"
echo "    If RSSI is absent, controller/driver may not report it; mock will fall back to synthetic RSSI."
echo "  * Force LE-only if needed (prevents BR/EDR conflicts): 'btmgmt le on; btmgmt bredr off'"
echo "  * If testing RF sensitivity, consider disabling Wi‑Fi temporarily to reduce interference."
