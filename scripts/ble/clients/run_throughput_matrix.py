#!/usr/bin/env python3
"""Helper to run a BLE throughput sweep with clear stdout logging."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

if __package__ is None:  # Allow running as `python scripts/ble/clients/run_throughput_matrix.py`
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.ble.clients.matrix_runner import ThroughputMatrixRunner  # type: ignore
else:
    from .matrix_runner import ThroughputMatrixRunner  # type: ignore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a throughput sweep across payload sizes.")
    parser.add_argument("--address", help="BLE address or platform identifier of the DUT / mock.")
    parser.add_argument("--discover_name", default="MockRingDemo", help="If address not provided, scan for this device name.")
    parser.add_argument("--discover_service", default="12345678-1234-5678-1234-56789abcdef0", help="If address not provided, filter scan by this service UUID.")
    parser.add_argument("--discover_timeout", type=float, default=5.0, help="Scan timeout when discovering the mock/DUT.")
    parser.add_argument("--payloads", type=int, nargs="+", default=[20, 60, 120, 180, 244])
    parser.add_argument("--repeats", type=int, default=3, help="Number of trials per payload size.")
    parser.add_argument("--duration_s", type=float, default=30.0, help="Test duration per trial.")
    parser.add_argument("--phy", choices=["auto", "1m", "2m", "coded"], default="coded", help="Preferred PHY request (default coded for range).")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789abcdef0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789abcdef1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789abcdef2")
    parser.add_argument("--out", default="logs/ble", help="Directory for raw throughput logs.")
    parser.add_argument("--client_script", default="scripts/ble/clients/ble_throughput_client.py")
    parser.add_argument("--summary_csv", default="results/tables/ble_matrix_summary.csv")
    parser.add_argument("--manifest_dir", default="results/manifests", help="Directory to write per-run manifest JSONs.")
    parser.add_argument("--lock_dir", default="/tmp/ble_runner_locks", help="Directory for per-adapter run locks.")
    parser.add_argument("--start_cmd", type=lambda x: int(x, 0), default=0x01)
    parser.add_argument("--stop_cmd", type=lambda x: int(x, 0), default=0x02)
    parser.add_argument("--reset_cmd", type=lambda x: int(x, 0), default=0x03)
    parser.add_argument("--mtu", type=int, default=247)
    parser.add_argument(
        "--connect_timeout_s",
        type=float,
        default=30.0,
        help="Seconds to wait for a BLE connection before failing an attempt.",
    )
    parser.add_argument(
        "--connect_attempts",
        type=int,
        default=5,
        help="Connection attempts before giving up (helps ride out transient adapter issues).",
    )
    parser.add_argument(
        "--connect_retry_delay_s",
        type=float,
        default=10.0,
        help="Seconds to sleep between connection attempts when retries are enabled.",
    )
    parser.add_argument("--validate_paths", action="store_true", help="Fail fast if client script is missing.")
    return parser


async def _discover_address(name: str, service: str, timeout: float) -> str:
    try:
        from bleak import BleakScanner
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("bleak is required for discovery; install bleak or provide --address") from exc
    devices = await BleakScanner.discover(timeout=timeout, service_uuids=[service] if service else None)
    for dev in devices:
        if name and dev.name == name:
            return dev.address
        if not name:
            return dev.address
    raise RuntimeError(f"Device not found via scan (name={name}, service={service}, timeout={timeout}s).")


def main() -> None:
    args = build_parser().parse_args()
    if not args.address:
        try:
            addr = asyncio.run(_discover_address(args.discover_name, args.discover_service, args.discover_timeout))
            print(f"[discover] Found device {addr} (name={args.discover_name}, service={args.discover_service})")
            args.address = addr
        except Exception as exc:  # pragma: no cover
            raise SystemExit(f"[discover] Failed to find device: {exc}") from exc
    runner = ThroughputMatrixRunner(args)
    summaries = runner.run()
    runner.print_table(summaries)
    runner.write_outputs(summaries)


if __name__ == "__main__":
    main()
