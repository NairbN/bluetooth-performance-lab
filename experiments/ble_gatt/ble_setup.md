# BLE GATT Test Harness Setup

These instructions cover how to prepare the BLE central-side tooling so we can exercise the Smart Ring test service once hardware becomes available. No DUT is required yet; placeholders illustrate the expected flow.

## 1. Prerequisites

- Linux host with Python 3.10+.
- Create a local virtual environment so `pip` does not touch the system interpreter (Debian/Ubuntu now block that via PEP 668):

  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip bleak
  ```

  Deactivate with `deactivate` when you are done; re-run `source .venv/bin/activate` before using the BLE scripts.
- Bluetooth adapter enabled and not connected to other devices.
- DUT BLE address (placeholder example: `AA:BB:CC:DD:EE:FF`).
- Test service UUIDs (defaults below, override when firmware changes):
  - Service: `12345678-1234-5678-1234-56789ABCDEF0`
  - TX Notify characteristic: `12345678-1234-5678-1234-56789ABCDEF1`
  - RX Write Without Response characteristic: `12345678-1234-5678-1234-56789ABCDEF2`

## 2. Directory Structure

```
scripts/ble/ble_throughput_client.py
scripts/ble/ble_latency_client.py
scripts/ble/ble_rssi_logger.py
logs/ble/           # Created automatically per run
```

Name each run using the timestamped filenames the scripts emit (e.g., `20250214_153000_ble_throughput.json`). Include device name, phone type, distance, and scenario details inside your lab notebook or test matrix so raw logs remain traceable.

## 3. Running the Throughput Client

1. Power on the DUT and make it advertising the dedicated test service.
2. Run:

```bash
python scripts/ble/ble_throughput_client.py \
  --address AA:BB:CC:DD:EE:FF \
  --payload_bytes 180 \
  --duration_s 120 \
  --packet_count 0
```

3. The script will:
   - Connect, discover the service/characteristics, and enable notifications.
   - Attempt MTU and PHY requests (logging success or "unsupported").
   - Send Reset → Start commands and capture all notifications.
   - Write CSV and JSON files under `logs/ble/` along with a summary (packets, estimated loss, throughput).
4. Stop the test by letting the duration elapse or pressing Ctrl+C (partial logs are still kept).

## 4. Running the Latency Client

Two modes exist:

- **Start mode (default):** Measures time from Start command to first notification.
- **Trigger mode:** Sends a Start command requesting one packet per iteration and measures write-to-notify latency.

Example (5 samples, trigger mode):

```bash
python scripts/ble/ble_latency_client.py \
  --address AA:BB:CC:DD:EE:FF \
  --mode trigger \
  --iterations 5 \
  --timeout_s 3.0
```

Outputs mirror the throughput script: per-iteration CSV/JSON logs plus a summary (avg/min/max latency, timeout count).

## 5. Running the RSSI Logger

Basic usage:

```bash
python scripts/ble/ble_rssi_logger.py \
  --address AA:BB:CC:DD:EE:FF \
  --samples 30 \
  --interval_s 1.0
```

The logger polls RSSI once per second. If the backend does not expose RSSI, the JSON metadata records the limitation and the CSV still logs timestamps with `null` RSSI values so gaps are obvious.

## 6. Expected Behavior

- Each script auto-creates `logs/ble/` and names files with UTC timestamps.
- CSV files contain per-event records; JSON files include metadata (adapter info, commands issued, MTU/PHY attempts, latency definition, etc.).
- Summaries print to stdout for quick sanity checks; full analysis happens later using notebooks or spreadsheets.

## 7. Common Errors + Fixes

- **`Operation not permitted` when connecting:** Run the script with appropriate permissions (e.g., user in the `bluetooth` group) or via `sudo` as a last resort.
- **Device not found / connection timeout:** Verify the address, ensure the DUT is advertising, and confirm no other host is connected. Use `bluetoothctl scan on` to confirm visibility.
- **UUID mismatch errors:** Update the `--service_uuid`, `--tx_uuid`, or `--rx_uuid` arguments if the DUT firmware changed. Clear OS caches (e.g., delete `~/.cache/bluetooth`) when UUIDs were recently updated.
- **Notifications never arrive:** Confirm the TX CCCD is writable (the throughput script fails fast otherwise). Reboot the DUT if it continues ignoring Start commands.
- **MTU negotiation sticks at default:** Linux user-space cannot force MTU on all stacks; the script logs the limitation so this is expected on some platforms.
- **RSSI always null:** Some adapters/drivers hide RSSI for active connections. Note it in the test log and consider using a sniffer (nRF52840 DK) for detailed RF metrics.

## 8. Post-Run Checklist

- Move or copy the generated logs into test-specific folders under `logs/ble/<date>_<scenario>/` to keep multi-device runs separate.
- Update `docs/test_coverage_plan.md` tables with device, scenario, and log filenames.
- Record environmental details (distance, orientation, interference sources) alongside each run before starting the next scenario.

## 9. Quick Start References

For a full end-to-end walkthrough (mock peripheral setup, central scripts, log processing, and troubleshooting), follow `docs/how_to_run_experiments.md`. Pair it with `experiments/ble_gatt/mock_dut_setup.md` when staging the mock DUT so both machines are configured consistently before you run the central clients.
