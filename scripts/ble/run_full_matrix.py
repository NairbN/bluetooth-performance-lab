#!/usr/bin/env python3
"""End-to-end BLE test driver covering payload/PHY/scenario permutations.

This helper runs throughput, latency, and RSSI scripts across multiple scenarios
so a single command can gather the data required by the lab plan.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run BLE throughput/latency/RSSI sweeps for multiple scenarios.")
    parser.add_argument("--address", required=True, help="BLE address of the DUT or mock.")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=[
            "baseline",
            "hand_behind_body",
            "phone_in_pocket",
            "phone_in_backpack",
        ],
        help="Scenario labels used to annotate results.",
    )
    parser.add_argument("--payloads", type=int, nargs="+", default=[20, 60, 120, 180, 244])
    parser.add_argument("--phys", nargs="+", default=["auto", "2m"], help="PHY settings to request per scenario.")
    parser.add_argument("--repeats", type=int, default=2, help="Trials per payload/PHY combination.")
    parser.add_argument("--duration_s", type=float, default=30.0, help="Throughput duration per trial.")
    parser.add_argument("--latency_iterations", type=int, default=5, help="Latency samples per run.")
    parser.add_argument("--latency_mode", choices=["start", "trigger"], default="start")
    parser.add_argument("--rssi_samples", type=int, default=20)
    parser.add_argument("--rssi_interval_s", type=float, default=1.0)
    parser.add_argument("--out", default="logs/ble", help="Directory where individual logs are written.")
    parser.add_argument("--results_dir", default="results/tables", help="Directory to store aggregated CSVs.")
    parser.add_argument("--note", default="", help="Optional note appended to every row (e.g., phone model).")
    parser.add_argument("--prompt", action="store_true", help="Prompt before each scenario to allow repositioning.")
    parser.add_argument("--skip_throughput", action="store_true")
    parser.add_argument("--skip_latency", action="store_true")
    parser.add_argument("--skip_rssi", action="store_true")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789abcdef0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789abcdef1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789abcdef2")
    parser.add_argument("--start_cmd", default="0x01")
    parser.add_argument("--stop_cmd", default="0x02")
    parser.add_argument("--reset_cmd", default="0x03")
    parser.add_argument("--throughput_script", default="scripts/ble/ble_throughput_client.py")
    parser.add_argument("--latency_script", default="scripts/ble/ble_latency_client.py")
    parser.add_argument("--rssi_script", default="scripts/ble/ble_rssi_logger.py")
    parser.add_argument("--mtu", type=int, default=247)
    return parser.parse_args()


def _list_logs(out_dir: Path, pattern: str) -> Dict[str, Path]:
    return {p.name: p for p in out_dir.glob(pattern)}


def _new_log(out_dir: Path, before: Dict[str, Path], pattern: str) -> Optional[Path]:
    after = _list_logs(out_dir, pattern)
    new_entries = [path for name, path in after.items() if name not in before]
    if not new_entries:
        return None
    return max(new_entries, key=lambda p: p.stat().st_mtime)


def _run_cmd(cmd: Sequence[str]) -> None:
    print(f"[runner] Exec: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def run_throughput_trial(
    args: argparse.Namespace,
    scenario: str,
    phy: str,
    payload: int,
    trial: int,
    out_dir: Path,
) -> Optional[Dict[str, float]]:
    before = _list_logs(out_dir, "*ble_throughput*.json")
    cmd = [
        sys.executable,
        args.throughput_script,
        "--address",
        args.address,
        "--service_uuid",
        args.service_uuid,
        "--tx_uuid",
        args.tx_uuid,
        "--rx_uuid",
        args.rx_uuid,
        "--payload_bytes",
        str(payload),
        "--duration_s",
        str(args.duration_s),
        "--out",
        str(out_dir),
        "--phy",
        phy,
        "--mtu",
        str(args.mtu),
        "--start_cmd",
        str(args.start_cmd),
        "--stop_cmd",
        str(args.stop_cmd),
        "--reset_cmd",
        str(args.reset_cmd),
    ]
    _run_cmd(cmd)
    log_path = _new_log(out_dir, before, "*ble_throughput*.json")
    if not log_path:
        print("[runner] WARNING: throughput log not found.")
        return None
    with log_path.open() as handle:
        data = json.load(handle)
    summary = data["metadata"].get("summary", {})
    record = {
        "scenario": scenario,
        "phy": phy,
        "payload_bytes": payload,
        "trial": trial,
        "packets": summary.get("packets"),
        "estimated_lost_packets": summary.get("estimated_lost_packets"),
        "duration_s": summary.get("duration_s"),
        "throughput_kbps": summary.get("throughput_kbps"),
        "notification_rate_per_s": summary.get("notification_rate_per_s"),
        "log_json": str(log_path),
        "log_csv": data["metadata"].get("records_file", {}).get("csv"),
        "notes": args.note,
    }
    return record


def run_latency_trial(
    args: argparse.Namespace,
    scenario: str,
    phy: str,
    trial: int,
    out_dir: Path,
) -> Optional[Dict[str, float]]:
    before = _list_logs(out_dir, "*ble_latency*.json")
    cmd = [
        sys.executable,
        args.latency_script,
        "--address",
        args.address,
        "--service_uuid",
        args.service_uuid,
        "--tx_uuid",
        args.tx_uuid,
        "--rx_uuid",
        args.rx_uuid,
        "--payload_bytes",
        str(max(20, min(244, args.payloads[-1]))),
        "--mode",
        args.latency_mode,
        "--iterations",
        str(args.latency_iterations),
        "--out",
        str(out_dir),
        "--phy",
        phy,
        "--mtu",
        str(args.mtu),
        "--start_cmd",
        str(args.start_cmd),
        "--stop_cmd",
        str(args.stop_cmd),
        "--reset_cmd",
        str(args.reset_cmd),
    ]
    _run_cmd(cmd)
    log_path = _new_log(out_dir, before, "*ble_latency*.json")
    if not log_path:
        print("[runner] WARNING: latency log not found.")
        return None
    with log_path.open() as handle:
        data = json.load(handle)
    summary = data["metadata"].get("summary", {})
    record = {
        "scenario": scenario,
        "phy": phy,
        "trial": trial,
        "mode": args.latency_mode,
        "avg_latency_s": summary.get("avg_latency_s"),
        "min_latency_s": summary.get("min_latency_s"),
        "max_latency_s": summary.get("max_latency_s"),
        "samples": summary.get("samples"),
        "timeouts": summary.get("timeouts"),
        "log_json": str(log_path),
        "log_csv": data["metadata"].get("records_file", {}).get("csv"),
        "notes": args.note,
    }
    return record


def run_rssi_trial(
    args: argparse.Namespace,
    scenario: str,
    phy: str,
    trial: int,
    out_dir: Path,
) -> Optional[Dict[str, float]]:
    before = _list_logs(out_dir, "*ble_rssi*.json")
    cmd = [
        sys.executable,
        args.rssi_script,
        "--address",
        args.address,
        "--samples",
        str(args.rssi_samples),
        "--interval_s",
        str(args.rssi_interval_s),
        "--out",
        str(out_dir),
    ]
    _run_cmd(cmd)
    log_path = _new_log(out_dir, before, "*ble_rssi*.json")
    if not log_path:
        print("[runner] WARNING: RSSI log not found.")
        return None
    with log_path.open() as handle:
        data = json.load(handle)
    metadata = data.get("metadata", {})
    record = {
        "scenario": scenario,
        "phy": phy,
        "trial": trial,
        "samples_collected": metadata.get("samples_requested"),
        "rssi_available": any(sample.get("rssi_dbm") is not None for sample in data.get("samples", [])),
        "log_json": str(log_path),
        "log_csv": data.get("metadata", {}).get("records_file", {}).get("csv"),
        "notes": args.note,
    }
    return record


def write_csv(rows: List[Dict[str, float]], headers: Sequence[str], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        handle.write(",".join(headers) + "\n")
        for row in rows:
            values = [str(row.get(field, "")) for field in headers]
            handle.write(",".join(values) + "\n")
    print(f"[runner] Wrote {len(rows)} rows to {path}")


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    throughput_rows: List[Dict[str, float]] = []
    latency_rows: List[Dict[str, float]] = []
    rssi_rows: List[Dict[str, float]] = []

    for scenario in args.scenarios:
        print(f"\n=== Scenario: {scenario} ===")
        if args.prompt:
            input("Adjust DUT/phone placement for this scenario, then press Enter to continue...")
        for phy in args.phys:
            print(f"[runner] Scenario {scenario} | PHY {phy}")
            if not args.skip_throughput:
                for payload in args.payloads:
                    for trial in range(1, args.repeats + 1):
                        summary = run_throughput_trial(args, scenario, phy, payload, trial, out_dir)
                        if summary:
                            throughput_rows.append(summary)
            if not args.skip_latency:
                for trial in range(1, 2):
                    summary = run_latency_trial(args, scenario, phy, trial, out_dir)
                    if summary:
                        latency_rows.append(summary)
            if not args.skip_rssi:
                for trial in range(1, 2):
                    summary = run_rssi_trial(args, scenario, phy, trial, out_dir)
                    if summary:
                        rssi_rows.append(summary)

    results_dir = Path(args.results_dir).expanduser()
    write_csv(
        throughput_rows,
        [
            "scenario",
            "phy",
            "payload_bytes",
            "trial",
            "packets",
            "estimated_lost_packets",
            "duration_s",
            "throughput_kbps",
            "notification_rate_per_s",
            "log_json",
            "log_csv",
            "notes",
        ],
        results_dir / "full_matrix_throughput.csv",
    )
    write_csv(
        latency_rows,
        [
            "scenario",
            "phy",
            "trial",
            "mode",
            "avg_latency_s",
            "min_latency_s",
            "max_latency_s",
            "samples",
            "timeouts",
            "log_json",
            "log_csv",
            "notes",
        ],
        results_dir / "full_matrix_latency.csv",
    )
    write_csv(
        rssi_rows,
        [
            "scenario",
            "phy",
            "trial",
            "samples_collected",
            "rssi_available",
            "log_json",
            "log_csv",
            "notes",
        ],
        results_dir / "full_matrix_rssi.csv",
    )


if __name__ == "__main__":
    main()
