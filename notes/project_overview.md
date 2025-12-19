# BLE Performance Lab – Project Overview

## Purpose

Provide a vendor-neutral BLE throughput test harness for the Smart Ring DUT:

- Defines the dedicated GATT test service (UUID `12345678-1234-5678-1234-56789ABCDEF0`) so firmware can implement Step 1 of the test plan without ambiguity.
- Supplies a mock peripheral, central scripts, and analysis tooling so throughput, latency, RSSI, and PER can be measured before actual hardware arrives.
- Documents test procedures (distance steps, body-shadow, coexistence) and automates them via CLI wrappers.

## Structure

| Component | Description |
| --- | --- |
| `scripts/ble/mock_dut_peripheral.py` + `scripts/start_mock.sh` | BlueZ-based mock exposing the test service; prints adapter MAC, processes Start/Stop/Reset commands, and streams `[SEQ][TS][DATA]` notifications with proper pacing. |
| `scripts/ble/ble_throughput_client.py` | Central logger: validates service/characteristics, sends commands, records notifications, exports CSV/JSON summaries (packets, PER, throughput, jitter). |
| `scripts/ble/ble_latency_client.py` | Measures “start command → notification” and “write → notification” latencies with configurable iterations/timeouts. |
| `scripts/ble/ble_rssi_logger.py` | Best-effort RSSI sampler (logs limitations if Linux can’t provide continuous values). |
| `scripts/ble/run_throughput_matrix.py` / `run_full_matrix.py` (+ shell wrappers) | End-to-end automation: sweeps payloads/PHYs/scenarios, prints progress + summaries, generates per-scenario plots and a final comparison chart. |
| Setup/Cleanup (`scripts/setup_linux_a.sh`, `setup_linux_b.sh`, `cleanup_outputs.sh`) | One-command environment prep on each machine plus log/results reset. |
| Analysis (`scripts/analysis/ble_log_summarize.py`, `ble_plot.py`) | Converts raw logs to tables and plots; full-matrix runner now auto-emits key plots. |

## Workflow

1. **Mock (Linux B)**: `./scripts/setup_linux_b.sh` (once) → `./scripts/start_mock.sh` (prints MAC, advertises service).
2. **Central (Linux A)**: `./scripts/setup_linux_a.sh` (once) → `source .venv/bin/activate` → optional `./scripts/cleanup_outputs.sh --yes`.
3. **Run tests**: `./scripts/run_full_matrix.sh --address <MAC> --note "<phone/scenario>"` (prompts between baseline, hand-behind-body, pocket, backpack; sweeps payloads + PHYs; logs throughput/latency/RSSI).
4. **Results**: Raw logs in `logs/ble/`; aggregated CSVs under `results/tables/`; per-scenario and comparison plots (throughput, latency, RSSI availability) in `results/plots/`. Summaries printed live and after completion (even if interrupted).

### Adjusting Test Parameters

Both `run_full_matrix.sh` and `run_throughput_matrix.sh` are thin wrappers over the Python scripts, so append flags to override defaults:

| Flag | Default | Effect |
| --- | --- | --- |
| `--payloads 20 60 120 180 244` | `[20,60,120,180,244]` | Payload sweep per trial. |
| `--repeats 2` | `2` | Trials per payload per PHY. |
| `--duration_s 30` | `30` | Throughput trial duration (seconds). |
| `--phys auto 2m` | `["auto","2m"]` | PHYs to test per scenario. |
| `--scenarios ...` | `baseline hand_behind_body phone_in_pocket phone_in_backpack` | Scenario labels; order drives prompt sequence. |
| `--skip_throughput/--skip_latency/--skip_rssi` | `False` | Disable a category of tests if not needed. |
| `--latency_iterations 5` | `5` | Samples per latency run. |
| `--rssi_samples 20` | `20` | Number of RSSI readings per scenario. |
| `--note "<text>"` | `""` | Tag stored in CSV/log metadata (phone model, location, etc.). |

Example: `./scripts/run_full_matrix.sh --address <MAC> --payloads 40 80 --repeats 1 --skip_latency`.

## Metrics Covered

- **Throughput & PER**: seq-based loss detection, payload sweeps, PHY variations; auto-generated plots.
- **Latency**: start-triggered or write-to-notification proxies.
- **RSSI & Range**: logging script and documented procedure (0.5–1 m steps, disconnect/reconnect tracking).
- **Body-shadow & coexistence**: captured via the scenario prompts in `run_full_matrix`.
- **Extensibility**: Additional RF/power metrics can be layered by integrating sniffer data, current probes, or GUI wrappers.

## Future Extensions

- GUI front-end to drive the same scripts (adapter selection, scenario control, live plot previews).
- Firmware hooks or external instruments for connection-interval stability and power draw logging.
- Sniffer integration (nRF52840 DK / CC2642) for over-the-air validation.
- Expand beyond the throughput test service to exercise additional GATT profiles (e.g., control, sensor streams) while reusing the same central automation.
- Add parallel test harnesses for Bluetooth Classic profiles (e.g., PAN, A2DP, RFCOMM) so the same lab workflow can validate coexistence and throughput across both BLE and Classic stacks.
