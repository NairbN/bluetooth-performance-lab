"""CLI entry for the RSSI logger."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.ble.clients.rssi import RssiClient  # type: ignore
else:
    from .clients.rssi import RssiClient  # type: ignore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BLE RSSI logger for Smart Ring DUT.")
    parser.add_argument("--address", required=True, help="BLE address of the DUT (e.g., AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--samples", type=int, default=20, help="Number of RSSI samples to attempt.")
    parser.add_argument("--interval_s", type=float, default=1.0, help="Delay between samples in seconds.")
    parser.add_argument("--out", default="logs/ble", help="Output directory for CSV/JSON logs.")
    parser.add_argument(
        "--mock_rssi_uuid",
        default="12345678-1234-5678-1234-56789abcdef3",
        help="Optional fallback characteristic for mock RSSI data.",
    )
    parser.add_argument("--connect_timeout_s", type=float, default=30.0, help="Seconds to wait per connection attempt.")
    parser.add_argument(
        "--connect_attempts",
        type=int,
        default=5,
        help="Connection attempts before giving up.",
    )
    parser.add_argument(
        "--connect_retry_delay_s",
        type=float,
        default=10.0,
        help="Seconds to sleep between connection attempts when retries are enabled.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print summary after logging.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = RssiClient(args)
    try:
        summary = asyncio.run(client.run())  # type: ignore[name-defined]
    except KeyboardInterrupt:
        if args.verbose:
            print("Interrupted by user; partial RSSI log retained.")
        return
    if args.verbose:
        print("RSSI logging summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    import asyncio

    main()
