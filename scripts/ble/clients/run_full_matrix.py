#!/usr/bin/env python3
"""End-to-end BLE test driver covering payload/PHY/scenario permutations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None:  # Allow running as `python scripts/ble/clients/run_full_matrix.py`
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.ble.clients.matrix_runner import FullMatrixRunner  # type: ignore
else:
    from .matrix_runner import FullMatrixRunner  # type: ignore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run BLE throughput/latency/RSSI sweeps for multiple scenarios.")
    parser.add_argument("--address", required=True, help="BLE address of the DUT or mock.")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["baseline", "hand_behind_body", "phone_in_pocket", "phone_in_backpack"],
        help="Scenario labels used to annotate results.",
    )
    parser.add_argument("--payloads", type=int, nargs="+", default=[20, 60, 120, 180, 244])
    parser.add_argument("--phys", nargs="+", default=["coded", "auto"], help="PHY settings to request per scenario (default prefers coded for range).")
    parser.add_argument("--repeats", type=int, default=2, help="Trials per payload/PHY combination.")
    parser.add_argument("--duration_s", type=float, default=30.0, help="Throughput duration per trial.")
    parser.add_argument("--latency_iterations", type=int, default=5, help="Latency samples per run.")
    parser.add_argument("--latency_mode", choices=["start", "trigger"], default="start")
    parser.add_argument("--rssi_samples", type=int, default=20)
    parser.add_argument("--rssi_interval_s", type=float, default=1.0)
    parser.add_argument("--out", default="logs/ble", help="Directory where individual logs are written.")
    parser.add_argument("--results_dir", default="results/tables", help="Directory to store aggregated CSVs.")
    parser.add_argument("--plots_dir", default="results/plots", help="Directory to store generated plots.")
    parser.add_argument("--note", default="", help="Optional note appended to every row (e.g., phone model).")
    parser.add_argument("--prompt", action="store_true", help="Prompt before each scenario to allow repositioning.")
    parser.add_argument("--skip_throughput", action="store_true")
    parser.add_argument("--skip_latency", action="store_true")
    parser.add_argument("--skip_rssi", action="store_true")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789abcdef0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789abcdef1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789abcdef2")
    parser.add_argument("--start_cmd", type=lambda x: int(x, 0), default=0x01)
    parser.add_argument("--stop_cmd", type=lambda x: int(x, 0), default=0x02)
    parser.add_argument("--reset_cmd", type=lambda x: int(x, 0), default=0x03)
    parser.add_argument("--throughput_script", default="scripts/ble/clients/ble_throughput_client.py")
    parser.add_argument("--latency_script", default="scripts/ble/clients/ble_latency_client.py")
    parser.add_argument("--rssi_script", default="scripts/ble/clients/ble_rssi_logger.py")
    parser.add_argument("--mtu", type=int, default=247)
    parser.add_argument("--manifest_dir", default="results/manifests", help="Directory to write per-run manifest JSONs.")
    parser.add_argument("--lock_dir", default="/tmp/ble_runner_locks", help="Directory for per-adapter run locks.")
    parser.add_argument("--validate_paths", action="store_true", help="Fail fast if client scripts are missing.")
    parser.add_argument(
        "--connect_timeout_s",
        type=float,
        default=30.0,
        help="Seconds to wait for throughput client connections before failing a trial.",
    )
    parser.add_argument(
        "--connect_attempts",
        type=int,
        default=5,
        help="Number of connection attempts to try per throughput run.",
    )
    parser.add_argument(
        "--connect_retry_delay_s",
        type=float,
        default=10.0,
        help="Seconds to wait between connection attempts when retries are enabled.",
    )
    parser.add_argument("--resume", action="store_true", help="Skip trials already recorded in existing throughput CSVs.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    runner = FullMatrixRunner(args)
    results = runner.run()
    runner.write_outputs(results)


if __name__ == "__main__":
    main()
