# Running the BLE Performance Lab

This guide replaces the old experiment walkthroughs. It describes the **current, automation-first workflow** for validating the Smart Ring BLE service with the mock peripheral and for preparing the lab for real hardware.

---

## 1. Environment Summary

| Role | Host | Responsibilities |
| --- | --- | --- |
| Linux B | Mock peripheral | Runs `scripts/tools/start_mock.sh`, advertises the Smart Ring GATT service, logs mock events. |
| Linux A | Central + analysis | Runs the throughput/latency/RSSI clients (usually via `run_full_matrix.sh`), stores logs/results, generates plots. |

Key directories:

- `logs/ble/` – raw CSV/JSON output per run
- `results/tables/` – aggregated CSVs (matrix exports)
- `results/plots/` – PNG charts per scenario + comparisons
- `logs/mock_dut.log` – optional mock peripheral log

All commands below assume you cloned the repo to `~/Workspace/bluetooth-performance-lab`.

---

## 2. Prerequisites

1. **Python environment** (both hosts)
   ```bash
   cd ~/Workspace/bluetooth-performance-lab
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -U pip
   ./scripts/tools/setup_linux_a.sh     # run on Linux A
   ./scripts/tools/setup_linux_b.sh     # run on Linux B
   ```

2. **BlueZ configuration (Linux B / mock)**
   - Ensure `bluetoothd` runs with `--experimental` so the mock can register GATT services.
   - Force the adapter into LE-only mode to prevent BR/EDR connections from stealing the link:
     ```bash
     sudo btmgmt -i hci0 power off
     sudo btmgmt -i hci0 le on
     sudo btmgmt -i hci0 bredr off
     sudo btmgmt -i hci0 power on
     ```

3. **Permissions** – add your user to the `bluetooth` group (log out/in) or run the tooling via `sudo`.

---

## 3. Starting the Mock Peripheral (Linux B)

```bash
cd ~/Workspace/bluetooth-performance-lab
source .venv/bin/activate
./scripts/tools/start_mock.sh --adapter hci0 --log logs/mock_dut.log
```

The script prints:

- Adapter MAC (copy it; Linux A will use it as `--address`)
- Advertising name (`MockRingDemo` by default)
- Mock log path (`logs/mock_dut.log`)

Leave the mock running while you collect data.

---

## 4. Running the Full Matrix (Linux A)

Activate the environment, then launch the automation helper:

```bash
cd ~/Workspace/bluetooth-performance-lab
source .venv/bin/activate
./scripts/tools/run_full_matrix.sh \
  --address 1C:4D:70:1E:13:A0 \
  --note "Pixel8+MockRing" \
  --connect_timeout_s 30 \
  --connect_attempts 5 \
  --connect_retry_delay_s 10
```

What happens:

- The wrapper calls `scripts/ble/run_full_matrix.py` with defaults (scenarios, payloads, PHYs, repeats).
- Each throughput, latency, and RSSI run now **inherits the same connection retry policy**, so temporary BlueZ hiccups are retried consistently. The CLI prints lines such as `[throughput] Connected … on attempt 2/5`.
- Logs land under `logs/ble/`; each run writes both CSV and JSON plus metadata (connection attempts, command errors).
- Aggregated CSVs go to `results/tables/` and plots to `results/plots/` automatically at the end of the run.

Use `--skip_throughput`, `--skip_latency`, or `--skip_rssi` if you need to debug a single phase. Add `--prompt` if you want to reposition hardware between scenarios.

---

## 5. Single-Test Debugging

When reproducing a bug outside the matrix, run the clients directly:

```bash
# Throughput sanity check
python scripts/ble/ble_throughput_client.py \
  --address 1C:4D:70:1E:13:A0 \
  --duration_s 20 \
  --connect_attempts 5 --connect_timeout_s 30

# Latency probe
python scripts/ble/ble_latency_client.py \
  --address 1C:4D:70:1E:13:A0 \
  --mode trigger --iterations 10 \
  --connect_attempts 5 --connect_timeout_s 30

# RSSI logger
python scripts/ble/ble_rssi_logger.py \
  --address 1C:4D:70:1E:13:A0 \
  --samples 30 --interval_s 1.0 \
  --connect_attempts 5 --connect_timeout_s 30
```

Every client prints retry progress and records connection metadata in its JSON output.

---

## 6. Cache Clearing & Recovery

Linux sometimes refuses new LE connections after firmware or topology changes. Use the helper to clear cached bond/service data and restart bluetoothd:

```bash
scripts/tools/clear_bt_cache.sh \
  --adapter AA:BB:CC:DD:EE:FF \
  --device 1C:4D:70:1E:13:A0 \
  --yes
```

- Run it on both hosts if each cached the other’s address.
- Use `--all` to wipe every cached device under the adapter.
- Afterward, restart the mock or rerun `start_mock.sh`.

---

## 7. Outputs to Expect

| Location | Contents |
| --- | --- |
| `logs/ble/*ble_throughput*.json/csv` | Per-trial packets, timing, retry stats, command logs. |
| `logs/ble/*ble_latency*.json/csv` | Iteration-level latencies, timeout counts, connection retry metadata. |
| `logs/ble/*ble_rssi*.json/csv` | RSSI samples with notes when unavailable. |
| `results/tables/full_matrix_*.csv` | Aggregated throughput, latency, and RSSI tables including `connection_attempts_used` and `command_errors`. |
| `results/plots/` | Scenario per-payload throughput plots (colored by retry/error health), latency bar charts, RSSI availability, and comparison charts. |

Archive completed runs with `scripts/tools/archive_results.sh --tag "<notes>"` to stash the logs/results.

---

## 8. Troubleshooting Cheat Sheet

| Symptom | Fix |
| --- | --- |
| Repeated `BleakDeviceNotFoundError` even though the mock is running | Force adapters into LE-only mode (`btmgmt` commands above) and clear caches via `clear_bt_cache.sh`. |
| Progress logs show multiple retry failures per scenario | Increase `--connect_retry_delay_s`, ensure no other central is connected, and confirm RSSI is reasonable (≥ -85 dBm). |
| Throughput stops cleanly but teardown throws `Service Discovery has not been performed yet` | Expected when the link drops late; the clients already log the error and continue. Focus on underlying RF stability. |
| RSSI logger always reports `rssi_dbm=null` | Adapter doesn’t expose RSSI via user space; rely on the mock RSSI characteristic or per-controller tools. |
| Plots show orange/red markers (retries/errors) | Check `connection_attempts_used` and `command_errors` columns in the CSV, inspect `logs/ble/...json` for command failures, and capture `btmon` traces if it’s frequent. |

With LE-only mode enforced, cache cleared, and automation flags in place, the lab scripts can now loop through entire scenario matrices reliably.
