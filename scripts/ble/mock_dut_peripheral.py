"""CLI wrapper for the mock Smart Ring BLE peripheral."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None:  # Allow running as `python scripts/ble/mock_dut_peripheral.py`
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.ble.mock.app import run_mock  # type: ignore
else:
    from .mock.app import run_mock  # type: ignore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mock Smart Ring BLE peripheral.")
    parser.add_argument("--adapter", default=None, help="Adapter name (e.g., hci0)")
    parser.add_argument("--timeout", type=int, default=0, help="Auto-stop after N seconds (0=run forever)")
    parser.add_argument("--advertise_name", default="MockRingDemo")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789abcdef0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789abcdef1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789abcdef2")
    parser.add_argument("--rssi_uuid", default="12345678-1234-5678-1234-56789abcdef3", help="Optional mock RSSI characteristic UUID.")
    parser.add_argument("--payload_bytes", type=int, default=120)
    parser.add_argument("--notify_hz", type=int, default=40)
    parser.add_argument("--interval_ms", type=int, default=None, help="Override notify interval in ms.")
    parser.add_argument("--start_cmd", type=lambda x: int(x, 0), default=0x01)
    parser.add_argument("--stop_cmd", type=lambda x: int(x, 0), default=0x02)
    parser.add_argument("--reset_cmd", type=lambda x: int(x, 0), default=0x03)
    parser.add_argument("--mock_rssi_base_dbm", type=int, default=-55, help="Baseline RSSI (dBm) used for mock RSSI characteristic.")
    parser.add_argument("--mock_rssi_variation", type=int, default=5, help="Variation (+/- dBm) for mock RSSI characteristic.")
    parser.add_argument("--log", default=None, help="Optional log file path")
    parser.add_argument("--quiet", action="store_true", help="Reduce stdout noise")
    parser.add_argument("--verbose", action="store_true", help="Force verbose console logging (overrides --quiet).")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if getattr(args, "verbose", False):
        args.quiet = False
    run_mock(args)


if __name__ == "__main__":
    main()
