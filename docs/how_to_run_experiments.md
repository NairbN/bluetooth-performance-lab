# How to Run the BLE Experiments (Mock DUT → Analysis)

This guide walks through every step required to validate the BLE tooling using the mock Smart Ring DUT, collect logs, and produce tables/plots. It assumes two Linux hosts (Linux A and Linux B) as described in the repository docs.

---

## 1. What You Will Run

1. **Mock DUT peripheral** (`scripts/ble/mock_dut_peripheral.py`) on one machine to emulate the Smart Ring service.
2. **Central clients** on the other machine:
   - Throughput: `scripts/ble/ble_throughput_client.py`
   - Latency: `scripts/ble/ble_latency_client.py`
   - RSSI logger: `scripts/ble/ble_rssi_logger.py`
3. **Log capture**: each central script writes CSV/JSON under `logs/ble/`.
4. **Post-processing**:
   - `scripts/analysis/ble_log_summarize.py` → `results/tables/`
   - `scripts/analysis/ble_plot.py` → `results/plots/`

No real RF validation occurs in this rehearsal; the goal is to confirm software workflows end-to-end.

---

## 2. Machine Roles

- **Recommended assignment**
  - **Linux B (mock peripheral):** runs `mock_dut_peripheral.py`, advertises the Smart Ring test service, and logs optional events to `logs/mock_dut.log`.
  - **Linux A (central + analysis):** runs the bleak-based clients, stores `logs/ble/`, and later executes the analysis scripts.
- **Why separate machines?** Using different adapters guarantees that the central scripts connect over an actual BLE link and prevents advertisement/connection conflicts on a single adapter. It mirrors the final topology (phone ↔ ring) and avoids kernel limitations around simultaneous peripheral + central roles.
- **Swap option:** If hardware availability differs, you may swap roles (Linux A = peripheral, Linux B = central). Update adapter names and addresses accordingly; all commands remain valid.

---

## 3. Prerequisites & Setup

### 3.1 Python Environment

1. Ensure Python ≥ 3.10 is installed on both machines (`python3 --version`).
2. Create a virtual environment (optional but recommended):

   ```bash
   python3 -m venv ~/ble_lab_env
   source ~/ble_lab_env/bin/activate
   ```

3. Install required packages:

   ```bash
   pip install bleak dbus-next matplotlib
   ```

   - `bleak` – required by all central scripts.
   - `dbus-next` – required by the mock peripheral (BlueZ GATT server).
   - `matplotlib` – required for `scripts/analysis/ble_plot.py`.

Keep venv activation consistent on both hosts.

### 3.2 BlueZ Requirements for the Mock Peripheral

`mock_dut_peripheral.py` needs BlueZ with experimental GATT server enabled. Pick one of the following approaches **on the peripheral machine** (Linux B in the recommended layout).

**Option A — Temporary/manual**

1. Stop the running service:

   ```bash
   sudo systemctl stop bluetooth
   ```

2. Launch the daemon manually with experimental features:

   ```bash
   sudo /usr/lib/bluetooth/bluetoothd --experimental
   ```

   - Path may differ by distribution (e.g., `/usr/sbin/bluetoothd`). Keep the terminal open while the mock is running.

3. When finished, terminate the manual daemon (Ctrl+C) and restart the service (`sudo systemctl start bluetooth`).

**Option B — Systemd override (recommended)**

1. Create or edit an override:

   ```bash
   sudo systemctl edit bluetooth
   ```

2. Add:

   ```
   [Service]
   ExecStart=
   ExecStart=/usr/lib/bluetooth/bluetoothd --experimental
   ```

3. Reload and restart:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart bluetooth
   ```

4. Verify the adapter exposes `GattManager1`/`LEAdvertisingManager1` via `busctl tree org.bluez` or `bluetoothctl show`.

### 3.3 Permissions

- **User groups:** Add your user to the `bluetooth` group (log out/in). Otherwise, commands may return `Operation not permitted`.
- **Sudo fallback:** If group membership isn’t available, run the scripts with `sudo` but note that Python venv paths may differ.
- **Error handling:** When `mock_dut_peripheral.py` or the central clients report permission errors, confirm:
  - Adapter is powered (`bluetoothctl power on`).
  - `rfkill` is not blocking Bluetooth (`rfkill list`).
  - No other applications (GUI tools, bluetoothctl interactive sessions) are holding the adapter.

---

## 4. “First Successful Run” Quick Start

This section delivers a minimal smoke test to confirm your environment works before running full matrices.

1. **Peripheral prep (Linux B)**
   - Ensure `bluetoothd` is running with `--experimental`.
   - Activate the Python environment and run:

     ```bash
     python scripts/ble/mock_dut_peripheral.py \
       --adapter hci0 \
       --advertise_name MockRingDemo \
       --payload_bytes 160 \
       --notify_hz 40 \
       --out logs/mock_dut.log
     ```

   - The script prints when the service is registered and begins advertising. Leave it running.

2. **Central scan (Linux A)**

   ```bash
   bluetoothctl scan on
   ```

   - Wait for `MockRingDemo` and note the MAC address (e.g., `AA:BB:CC:DD:EE:FF`). Press Ctrl+C to stop scanning.

3. **Run a short throughput test (Linux A)**

   ```bash
   python scripts/ble/ble_throughput_client.py \
     --address AA:BB:CC:DD:EE:FF \
     --payload_bytes 160 \
     --duration_s 20
   ```

   - The script prints a summary at exit.

4. **Verify logs**
   - Confirm `logs/ble/` now contains timestamped `.csv` and `.json` files (e.g., `20250301_120000_ble_throughput.csv`).
   - If `--out logs/mock_dut.log` was used, the peripheral machine should show entries under `logs/mock_dut.log`.

5. Stop the peripheral with Ctrl+C when done.

---

## 5. Throughput Experiment Matrix

Rehearse a simple sweep before the real DUT arrives:

- **Payload sizes:** 20, 60, 120, 180, 244 bytes.
- **Duration:** 30 seconds per run.
- **Repeats:** 3 iterations per payload (rename logs accordingly).

Example command template (Linux A):

```bash
python scripts/ble/ble_throughput_client.py \
  --address AA:BB:CC:DD:EE:FF \
  --payload_bytes {PAYLOAD} \
  --duration_s 30 \
  --out logs/ble/ \
  --packet_count 0
```

For repeat tracking, note trial number in a spreadsheet or rename/move logs after each run (e.g., `logs/ble/20250301_130500_ble_throughput_payload120_trial2.csv`).

**Mock peripheral tuning (Linux B):**

- `--payload_bytes`: default payload size used unless overridden by the Start command.
- `--notify_hz` or `--interval_ms`: adjust to simulate different notification rates; lower rates may prevent queue buildup.
- Keep the peripheral running with consistent settings during a sweep to avoid additional variables.

---

## 6. Latency Experiment Procedure

The latency script estimates how long it takes from issuing a Start command until the mock DUT’s next notification. It provides two modes:

- `--mode start`: measures “Start command → first notification” latency.
- `--mode trigger`: sends Start commands that request a single packet per iteration to emulate “write-to-notify” latency.

Example (Linux A):

```bash
python scripts/ble/ble_latency_client.py \
  --address AA:BB:CC:DD:EE:FF \
  --mode trigger \
  --iterations 10 \
  --timeout_s 3.0 \
  --inter_delay_s 1.0
```

Outputs:

- CSV/JSON files under `logs/ble/` with per-iteration latency (`latency_s`).
- Summary printed to stdout showing average/min/max latency and timeout counts.

Interpretation: These numbers validate that the software is capturing proxy latency; they are not final DUT performance metrics because the mock lacks real link-layer scheduling.

---

## 7. RSSI / Range Rehearsal

Run the RSSI logger to validate the logging pipeline:

```bash
python scripts/ble/ble_rssi_logger.py \
  --address AA:BB:CC:DD:EE:FF \
  --samples 30 \
  --interval_s 1.0
```

Limitations:

- Some Linux adapters do not expose continuous RSSI through `bleak`. In those cases, the CSV will list timestamps with `null`/empty RSSI values, and the JSON metadata will note the limitation.
- This rehearsal is only to ensure the script runs; for real range testing consider controller-specific APIs (`btmgmt`, vendor tools) or an external sniffer (nRF52840 DK, CC2642).

---

## 8. Analysis Pipeline

Once logs exist under `logs/ble/`, run the analysis scripts on Linux A.

1. **Summarize logs into a table:**

   ```bash
   python scripts/analysis/ble_log_summarize.py \
     --input logs/ble/ \
     --out results/tables/ble_summary.csv
   ```

   - Produces `results/tables/ble_summary.csv` containing duration, packet counts, estimated loss, throughput, and jitter for each log file.

2. **Generate plots:**

   ```bash
   python scripts/analysis/ble_plot.py \
     --input results/tables/ble_summary.csv \
     --outdir results/plots \
     --prefix ble_summary
   ```

   - Outputs:
     - `results/plots/ble_summary_throughput.png`
     - `results/plots/ble_summary_loss.png`

Review the plots to confirm the analysis pipeline works; replace mock data with real DUT logs later.

---

## 9. Expected Files After Completion

- `logs/ble/*.csv` and `logs/ble/*.json` — per-run raw data from throughput, latency, and RSSI scripts.
- `logs/mock_dut.log` — optional peripheral event log if `--out` was supplied.
- `results/tables/ble_summary.csv` — consolidated summary table from the analyzer.
- `results/plots/ble_summary_throughput.png`
- `results/plots/ble_summary_loss.png`

Organize log folders per scenario (e.g., `logs/ble/20250301_mock/`) to keep matrices tidy.

---

## 10. Troubleshooting

| Issue | Symptoms | Fix |
| --- | --- | --- |
| BlueZ not running with `--experimental` | `org.bluez.Error.NotSupported` when registering GATT/advertisement | Enable experimental mode via manual `bluetoothd --experimental` (Option A) or systemd override (Option B). Restart the daemon. |
| Permission errors (`Operation not permitted`, `AdapterNotReady`) | Peripheral or central scripts exit immediately | Add user to `bluetooth` group, ensure adapter is powered, verify no GUI tools are holding the adapter. As a last resort, run scripts with `sudo`. |
| Mock peripheral not advertising | `bluetoothctl scan on` never shows the mock name | Check that `mock_dut_peripheral.py` is running, adapter is powered (`bluetoothctl power on`), and `rfkill list` shows Bluetooth unblocked. |
| Central cannot connect | `bleak` connection timeout or immediate disconnect | Make sure only one central is attempting to connect. Stop any lingering `bluetoothctl connect` sessions. Verify the MAC address hasn’t changed (re-scan). |
| Notifications not flowing | Throughput script stuck waiting, peripheral log lacks “Start command received” | Confirm CCCD writes succeed (script exits if they fail). Verify the UUIDs match the mock (service/characteristics). Restart peripheral and central scripts. |
| Missing Python dependencies | Import errors for `bleak`, `dbus-next`, or `matplotlib` | Activate the correct venv and run `pip install bleak dbus-next matplotlib`. Update `pip` if necessary. |

If issues persist, capture `btmon` traces and the peripheral log for later debugging.

---

You now have a full rehearsal path from mock advertisement to plots. Repeat the workflow with the real Smart Ring DUT once hardware becomes available.
