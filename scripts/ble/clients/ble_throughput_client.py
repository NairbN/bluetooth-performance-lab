#!/usr/bin/env python3
"""CLI entry for the Smart Ring throughput client."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None:  # Allow running as `python scripts/ble/clients/ble_throughput_client.py`
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.ble.clients.throughput import ThroughputClient  # type: ignore
else:
    from .throughput import ThroughputClient  # type: ignore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BLE throughput logger for Smart Ring DUT.")
    parser.add_argument("--address", required=True, help="BLE address of the DUT (e.g., AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789ABCDEF0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789ABCDEF1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789ABCDEF2")
    parser.add_argument("--payload_bytes", type=int, default=20, help="Payload size hint sent with the start command (20-244).")
    parser.add_argument("--packet_count", type=int, default=0, help="Optional packet count request to embed in the start command.")
    parser.add_argument("--duration_s", type=float, default=0.0, help="Optional duration in seconds to keep the test running.")
    parser.add_argument("--out", default="logs/ble", help="Output directory for CSV/JSON logs.")
    parser.add_argument("--start_cmd", type=lambda x: int(x, 0), default=0x01, help="Start command ID (default 0x01).")
    parser.add_argument("--stop_cmd", type=lambda x: int(x, 0), default=0x02, help="Stop command ID (default 0x02).")
    parser.add_argument("--reset_cmd", type=lambda x: int(x, 0), default=0x03, help="Reset command ID (default 0x03).")
    parser.add_argument("--mtu", type=int, default=247, help="Requested MTU size.")
    parser.add_argument("--phy", choices=["auto", "1m", "2m", "coded"], default="auto", help="Preferred PHY request (best-effort).")
    parser.add_argument("--connect_timeout_s", type=float, default=30.0, help="Seconds to wait for a BLE connection before failing an attempt.")
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
    parser.add_argument("--verbose", action="store_true", help="Print detailed summary logs.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not 20 <= args.payload_bytes <= 244:
        raise SystemExit("payload_bytes must be between 20 and 244 to align with ATT MTU constraints.")
    client = ThroughputClient(args)
    try:
        summary = asyncio.run(client.run())  # type: ignore[name-defined]
    except KeyboardInterrupt:
        if args.verbose:
            print("Interrupted by user; partial logs retained.")
        return
    if args.verbose:
        print("Test summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    import asyncio  # local import to avoid affecting module users

    main()
