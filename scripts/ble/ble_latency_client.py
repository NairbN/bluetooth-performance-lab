"""CLI entry for the Smart Ring latency client."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.ble.clients.latency import LatencyClient  # type: ignore
else:
    from .clients.latency import LatencyClient  # type: ignore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BLE latency measurement harness for Smart Ring DUT.")
    parser.add_argument("--address", required=True, help="BLE address of the DUT (e.g., AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789ABCDEF0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789ABCDEF1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789ABCDEF2")
    parser.add_argument("--payload_bytes", type=int, default=20, help="Payload size hint for latency commands.")
    parser.add_argument("--packet_count", type=int, default=1, help="Packet count for start-mode latency (ignored in trigger mode).")
    parser.add_argument("--mode", choices=["start", "trigger"], default="start", help="Latency definition to use.")
    parser.add_argument("--iterations", type=int, default=5, help="Number of latency samples to collect.")
    parser.add_argument("--timeout_s", type=float, default=5.0, help="Timeout per iteration before marking a failure.")
    parser.add_argument("--inter_delay_s", type=float, default=1.0, help="Delay between iterations.")
    parser.add_argument("--out", default="logs/ble", help="Output directory for CSV/JSON logs.")
    parser.add_argument("--start_cmd", type=lambda x: int(x, 0), default=0x01, help="Start command opcode.")
    parser.add_argument("--stop_cmd", type=lambda x: int(x, 0), default=0x02, help="Stop command opcode.")
    parser.add_argument("--reset_cmd", type=lambda x: int(x, 0), default=0x03, help="Reset command opcode.")
    parser.add_argument("--mtu", type=int, default=247, help="Requested MTU size.")
    parser.add_argument("--phy", choices=["auto", "1m", "2m", "coded"], default="auto", help="Preferred PHY request (best-effort).")
    parser.add_argument("--verbose", action="store_true", help="Print detailed summary logs.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not 20 <= args.payload_bytes <= 244:
        raise SystemExit("payload_bytes must be between 20 and 244.")
    client = LatencyClient(args)
    try:
        summary = asyncio.run(client.run())  # type: ignore[name-defined]
    except KeyboardInterrupt:
        if args.verbose:
            print("Interrupted by user; partial logs retained.")
        return
    if args.verbose:
        print("Latency summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    import asyncio

    main()
