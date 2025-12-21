#!/usr/bin/env python3
"""CLI wrapper for the mock Smart Ring BLE peripheral."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None:  # Allow running as `python scripts/ble/mock/cli.py`
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.ble.mock.app import run_mock  # type: ignore
else:
    from .app import run_mock  # type: ignore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mock Smart Ring BLE peripheral.")
    parser.add_argument("--adapter", default=None, help="Adapter name (e.g., hci0)")
    parser.add_argument("--timeout", type=int, default=0, help="Auto-stop after N seconds (0=run forever)")
    parser.add_argument("--advertise_name", default="MockRingDemo")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789abcdef0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789abcdef1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789abcdef2")
    parser.add_argument(
        "--rssi_uuid",
        default="12345678-1234-5678-1234-56789abcdef3",
        help="Optional mock RSSI characteristic UUID.",
    )
    parser.add_argument("--payload_bytes", type=int, default=120)
    parser.add_argument("--notify_hz", type=int, default=40)
    parser.add_argument("--interval_ms", type=int, default=None, help="Override notify interval in ms.")
    parser.add_argument("--start_cmd", type=lambda x: int(x, 0), default=0x01)
    parser.add_argument("--stop_cmd", type=lambda x: int(x, 0), default=0x02)
    parser.add_argument("--reset_cmd", type=lambda x: int(x, 0), default=0x03)
    parser.add_argument(
        "--mock_rssi_base_dbm",
        type=int,
        default=-55,
        help="Baseline RSSI (dBm) used for mock RSSI characteristic.",
    )
    parser.add_argument(
        "--mock_rssi_variation",
        type=int,
        default=5,
        help="Variation (+/- dBm) for mock RSSI characteristic.",
    )
    parser.add_argument("--mock_drop_percent", type=int, default=0, help="Percentage of notifications to drop intentionally (0-100).")
    parser.add_argument(
        "--interval_jitter_ms",
        type=int,
        default=0,
        help="Add +/- jitter to notify interval (ms) to mimic connection drift.",
    )
    parser.add_argument(
        "--rssi_drift_dbm",
        type=int,
        default=0,
        help="Linear drift applied per notification to mock RSSI (positive or negative).",
    )
    parser.add_argument(
        "--phy_profile",
        choices=["fixed", "varying"],
        default="fixed",
        help="When set to 'varying', adjust notify interval to mimic PHY changes over time.",
    )
    parser.add_argument(
        "--scenario_profile",
        choices=["best", "typical", "body_block", "pocket", "worst"],
        default="typical",
        help="Prebaked mock realism profile (drop/jitter/RSSI behavior).",
    )
    parser.add_argument("--drop_burst_percent", type=int, default=0, help="Chance per tick to start a drop burst (0-100).")
    parser.add_argument("--drop_burst_len", type=int, default=0, help="Length of a drop burst in packets.")
    parser.add_argument("--malformed_chance", type=int, default=0, help="Chance (%) to send a malformed/short packet.")
    parser.add_argument(
        "--latency_spike_ms",
        type=int,
        default=0,
        help="Extra delay in ms injected occasionally to mimic congestion.",
    )
    parser.add_argument(
        "--latency_spike_chance",
        type=int,
        default=0,
        help="Chance (%) per packet to inject the latency spike.",
    )
    parser.add_argument(
        "--rssi_wave_amplitude",
        type=int,
        default=0,
        help="Amplitude of a slow RSSI wave (dB) to mimic movement.",
    )
    parser.add_argument(
        "--rssi_wave_period",
        type=int,
        default=0,
        help="Period (packets) of the RSSI wave; higher = slower change.",
    )
    parser.add_argument(
        "--disconnect_chance",
        type=int,
        default=0,
        help="Chance (%) per packet to simulate a disconnect (stops notifications).",
    )
    parser.add_argument(
        "--rssi_profile_file",
        default=None,
        help="Optional JSON file containing a list of RSSI values to replay cyclically.",
    )
    parser.add_argument(
        "--interval_profile_file",
        default=None,
        help="Optional JSON file with a list of interval ms values to replay cyclically.",
    )
    parser.add_argument(
        "--drop_profile_file",
        default=None,
        help="Optional JSON list of drop probabilities (0-1) applied cyclically per packet.",
    )
    parser.add_argument(
        "--command_ignore_chance",
        type=int,
        default=0,
        help="Chance (%) to ignore a start/stop/reset command (error injection).",
    )
    parser.add_argument(
        "--rssi_drop_threshold",
        type=int,
        default=-80,
        help="If RSSI falls below this dBm, apply extra drop probability.",
    )
    parser.add_argument(
        "--rssi_drop_extra_percent",
        type=int,
        default=5,
        help="Extra drop percent when RSSI is below the threshold.",
    )
    parser.add_argument(
        "--backlog_limit",
        type=int,
        default=0,
        help="Simulated buffer capacity; when exceeded, notifications pause briefly to mimic backpressure.",
    )
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
