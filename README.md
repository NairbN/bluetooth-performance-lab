# BLE Performance Lab (Smart Ring Focus)

This repo hosts a vendor-neutral lab environment for validating a Smart Ring DUT’s BLE throughput, latency, and RF performance before hardware is available. It defines the dedicated test GATT service, provides a mock peripheral, central automation scripts, and analysis tooling.

---

## Quick Start

### 1. Prepare Linux B (Mock DUT host)

```bash
cd ~/Workspace/bluetooth-performance-lab
git pull
./scripts/setup_linux_b.sh        # first run or after pull
./scripts/start_mock.sh           # prints adapter MAC and advertises the test service
```

Keep that terminal open; it runs the mock and logs to `logs/mock_dut.log`.

### 2. Prepare Linux A (Central / logger)

```bash
cd ~/Workspace/bluetooth-performance-lab
git pull
./scripts/setup_linux_a.sh        # first run or after pull
source .venv/bin/activate
./scripts/cleanup_outputs.sh --yes   # optional: clear logs/results
```

### 3. Run the BLE test matrix

```bash
./scripts/run_full_matrix.sh --address <MAC_FROM_MOCK> --note "Phone/Scenario"
```

This walks through the default scenarios (baseline, hand-behind-body, phone in pocket, phone in backpack), sweeps payloads/PHYs, logs throughput/latency/RSSI, and generates CSVs + plots automatically.

### 4. Inspect results

- Raw logs: `logs/ble/`
- Aggregated tables: `results/tables/`
- Plots (per scenario + comparison charts for throughput, latency, RSSI availability): `results/plots/`

---

## Components

| Path | Role |
| --- | --- |
| `scripts/start_mock.sh` → `scripts/ble/mock_dut_peripheral.py` | BlueZ-based mock exposing the test GATT service (UUID `12345678-1234-5678-1234-56789ABCDEF0`). Prints adapter MAC, handles Start/Stop/Reset commands, streams `[SEQ][TS][DATA]` notifications. |
| `scripts/ble/ble_throughput_client.py` | Central harness for throughput & packet-loss logging (CSV/JSON). Supports optional `--verbose` for detailed logs. |
| `scripts/ble/ble_latency_client.py` | Measures start-triggered or write-to-notify latency with configurable iterations/timeouts. |
| `scripts/ble/ble_rssi_logger.py` | Best-effort RSSI logger (records limitations when Linux can’t provide continuous values). |
| `scripts/run_full_matrix.sh` (`run_throughput_matrix.sh`) | Automation wrappers covering scenarios, PHYs, payload sweeps, latency, and RSSI. Prints progress bars, per-scenario summaries, and generates plots. |
| `scripts/cleanup_outputs.sh` | Clears `logs/ble/` and `results/*` (optional before each run). |
| `scripts/analysis/ble_log_summarize.py`, `ble_plot.py` | Additional post-processing helpers (summaries/plots). |
| `docs/`, `experiments/`, `notes/` | Detailed context (test plan, topology, mock/device setup, troubleshooting). |

---

## Adjusting Test Parameters

`run_full_matrix.sh` forwards CLI flags to `scripts/ble/run_full_matrix.py`. Common overrides:

| Flag | Default | Purpose |
| --- | --- | --- |
| `--payloads 20 60 120 180 244` | `[20,60,120,180,244]` | Payload sizes for each throughput trial. |
| `--repeats 2` | `2` | Trials per payload per PHY. |
| `--duration_s 30` | `30` | Throughput trial duration (seconds). |
| `--phys auto 2m` | `["auto","2m"]` | PHYs to test per scenario. |
| `--scenarios baseline ...` | `[baseline, hand_behind_body, phone_in_pocket, phone_in_backpack]` | Scenario labels. |
| `--skip_throughput` / `--skip_latency` / `--skip_rssi` | `False` | Disable parts of the matrix. |
| `--latency_iterations 5` | `5` | Samples per latency run. |
| `--rssi_samples 20` | `20` | RSSI readings per scenario. |
| `--note "<text>"` | `""` | Stored in CSV/JSON for traceability (phone model, environment). |

Example: `./scripts/run_full_matrix.sh --address <MAC> --scenarios baseline --duration_s 15 --repeats 1 --skip_latency`.

---

## Metrics Captured

- **Throughput & PER** via seq-number gaps (automated CSV + plots per scenario).
- **Latency** (start-triggered and write-to-notify proxies).
- **RSSI availability / range** and scenario prompts for body-shadow testing.
- **Cross-scenario comparison** charts for quick A/B decisions (RF engineer context).

Power draw, connection-interval stability, and Bluetooth Classic profiles (PAN/A2DP/RFCOMM) are on the roadmap (see `notes/project_overview.md`).

---

## Mock Service Specification

- **Service UUID**: `12345678-1234-5678-1234-56789ABCDEF0`
- **TX characteristic** (`…DEF1`): Notify, `[SEQ_L][SEQ_H][TS_L][TS_H][DATA…]`
- **RX characteristic** (`…DEF2`): Write Without Response
- **Commands**:
  - `0x01`: Start (optional payload size + packet count)
  - `0x02`: Stop
  - `0x03`: Reset

This matches the Smart Ring firmware spec so the BLE stack can implement the same service once hardware is ready.

---

## Help & Docs

- `notes/project_overview.md` – high-level summary, tunables, future roadmap.
- `experiments/ble_gatt/ble_setup.md` – detailed BLE experiment instructions.
- `docs/how_to_run_experiments.md` – step-by-step guide from mock setup to analysis.
- `notes/troubleshooting.md` – BLE-specific fixes (permissions, caching, MTU issues).

For PAN/RFCOMM experiments, see `experiments/pan/` and `experiments/rfcomm/` (legacy testing still in progress).
