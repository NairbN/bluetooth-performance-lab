# Smart Ring BLE Lab Software Guide

This document ties together the mock peripheral, client runners, automation wrappers, and outputs. It references the BLE test service defined in `docs/test_sw_requirements.md` and shows how to operate the stack end-to-end.

## 1) Architecture & Spec Anchor
- Test service UUIDs and command semantics are defined in `docs/test_sw_requirements.md` (TX Notify `…DEF1`, RX WriteNoResp `…DEF2`, Start/Stop/Reset commands).
- The lab is split into a **mock peripheral** (Linux B) and **clients + automation** (Linux A). Both hosts should run with BlueZ experimental flags and LE-only mode enabled.

## 2) Components at a Glance
- `scripts/ble/mock/cli.py` (`scripts/tools/start_mock.sh`): BlueZ-based mock peripheral that implements the test service, accepts Start/Stop/Reset, and streams `[SEQ][TS][DATA]` notifications. Supports realism knobs (drops, jitter, RSSI shaping, malformed packets, disconnects) and scenario presets (`best`, `typical`, `body_block`, `pocket`, `worst`).
- `scripts/ble/clients/ble_throughput_client.py`: Central client that connects to the mock/DUT, negotiates MTU/PHY (best effort), sends commands, logs packets, and emits JSON/CSV summaries (throughput, estimated loss, retries, command errors).
- `scripts/ble/clients/ble_latency_client.py`: Measures start-triggered or trigger-mode latency; logs averages/min/max plus timeouts.
- `scripts/ble/clients/ble_rssi_logger.py`: Best-effort RSSI sampler; records unavailability when adapters do not expose RSSI.
- `scripts/ble/clients/run_full_matrix.py`: Orchestrates throughput/latency/RSSI sweeps across scenarios, PHYs, payloads, and repeats. Handles resume, per-adapter locking, manifest writes, and optional plotting (matplotlib best effort).
- `scripts/ble/clients/run_throughput_matrix.py`: Throughput-only sweep with the same retry/lock/manifest behavior.
- `scripts/ble/clients/common.py`: Shared validation (UUIDs, payload bounds, path checks) and helpers.
- `scripts/ble/clients/health_check.py`: JSON preflight for dependencies, adapter power state, LE-only mode, and BlueZ experimental flags (useful for a backend/UI).
- Shell wrappers under `scripts/tools/`: `run_full_matrix.sh`, `run_throughput_matrix.sh`, `start_mock.sh`, `setup_linux_a.sh`, `setup_linux_b.sh`, `clear_bt_cache.sh`, `cleanup_outputs.sh`.

## 3) Data Flow & Outputs
1. Start mock on Linux B → advertises the test service from the spec.
2. Run clients/matrix on Linux A → connects via address, negotiates MTU/PHY best effort, issues Start/Stop/Reset, collects metrics.
3. Logs land in `logs/ble/*.json/csv` with connection metadata (`connection_attempts_used`, `command_errors`).
4. Aggregated CSVs land in `results/tables/full_matrix_*.csv`; plots (when matplotlib is available) in `results/plots/`.
5. Each matrix/throughput run writes a JSON manifest under `results/manifests/` (path overridable) so a backend can index runs without parsing CSVs.

## 4) Mock Peripheral Details
- Aligns to the spec UUIDs by default; override with `--service_uuid/--tx_uuid/--rx_uuid`.
- Realism controls:
  - Presets: `--scenario_profile best|typical|body_block|pocket|worst`.
  - Fine controls: `--mock_drop_percent`, `--drop_burst_percent/--drop_burst_len`, `--interval_jitter_ms` or `--interval_profile_file`, `--latency_spike_ms/chance`, `--malformed_chance`, `--disconnect_chance`, `--rssi_wave_*`, `--rssi_profile_file`, `--rssi_drift_dbm`, `--rssi_drop_threshold/--rssi_drop_extra_percent`, `--backlog_limit`, `--command_ignore_chance`.
  - PHY/MTU realism: Can occasionally ignore commands or pause to mimic backpressure; does not require pairing unless you add security to characteristics.
- Attempts to read real adapter RSSI first; falls back to shaped synthetic RSSI if unavailable.

## 5) Client & Matrix Behavior
- All clients share connection retry flags: `--connect_timeout_s`, `--connect_attempts`, `--connect_retry_delay_s`.
- MTU/PHY requests are best effort; failures are logged but not fatal.
- Resume: `run_full_matrix.py` can skip completed throughput trials when `--resume` is set (reads existing throughput CSV).
- Locking: A per-adapter lock under `--lock_dir` prevents concurrent runs on the same adapter.
- Manifests: Each run records args, outputs, summaries, and errors in JSON for backend indexing.
- Plotting: Plots are optional; warnings are emitted if matplotlib is missing or data is empty.

## 6) Setup & Health Checks
- Prep scripts:
  - `scripts/tools/setup_linux_b.sh` (mock host) and `setup_linux_a.sh` (client host) install deps.
  - Enforce LE-only mode and disable Wi‑Fi for stability (both hosts): `btmgmt power off; btmgmt le on; btmgmt bredr off; btmgmt power on; nmcli radio wifi off`.
  - Ensure BlueZ runs with `--experimental` (required for the mock GATT server).
- Health check (client side):
  ```bash
  python scripts/ble/clients/health_check.py --adapter hci0 --json
  ```
  Reports bleak/matplotlib availability, adapter power/LE-only, experimental flag hints, and permissions.
- Cache clearing (both hosts if discovery/pairing gets stuck):
  ```bash
  scripts/tools/clear_bt_cache.sh --adapter <ADAPTER_MAC> --device <PEER_MAC> --yes
  ```

## 7) Running Tests
- Mock host (Linux B):
  ```bash
  ./scripts/tools/start_mock.sh --adapter hci0 --scenario_profile typical --log logs/mock_dut.log
  ```
- Matrix (Linux A):
  ```bash
  ./scripts/tools/run_full_matrix.sh \
    --address <MOCK_MAC> \
    --note "Pixel8+MockRing" \
    --connect_timeout_s 30 --connect_attempts 5 --connect_retry_delay_s 10 \
    --resume
  ```
  Use `--skip_throughput/--skip_latency/--skip_rssi` to debug phases; `--prompt` to pause between scenarios.
- Throughput-only sweep:
  ```bash
  ./scripts/tools/run_throughput_matrix.sh --address <MOCK_MAC> --phy coded --payloads 60 120 244
  ```
- Single-run debugging: invoke the client scripts directly (see `README.md` examples).

## 8) Testing the Software
- Unit tests live in `tests/` and cover mock realism, client summaries, matrix orchestration (manifests, locking, resume). Run:
  ```bash
  python -m unittest discover -s tests -v
  ```
- Optional: install `pytest` to run with richer reporting.

## 9) Limitations & Notes
- Real hardware quirks (controller buffering, connection interval quirks, PHY negotiations) remain best-effort until DUT is available.
- RSSI availability depends on adapter/driver; the mock provides shaped RSSI when the platform cannot.
- Pairing/bonding is not required by default; add security only if you secure the characteristics to match future firmware policy.

## 10) Quick Cross-References
- Spec + required UUIDs: `docs/test_sw_requirements.md`
- End-to-end usage & stability checklist: `docs/how_to_run_experiments.md`
- Coverage plan: `docs/test_coverage_plan.md`
- Architecture & roadmap: `notes/project_overview.md`
