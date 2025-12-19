#!/usr/bin/env python3
"""Helper to run a BLE throughput sweep with clear stdout logging."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a throughput sweep across payload sizes.")
    parser.add_argument("--address", required=True, help="BLE address of the DUT / mock.")
    parser.add_argument("--payloads", type=int, nargs="+", default=[20, 60, 120, 180, 244])
    parser.add_argument("--repeats", type=int, default=3, help="Number of trials per payload size.")
    parser.add_argument("--duration_s", type=float, default=30.0, help="Test duration per trial.")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789abcdef0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789abcdef1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789abcdef2")
    parser.add_argument("--out", default="logs/ble", help="Directory for raw throughput logs.")
    parser.add_argument("--client_script", default="scripts/ble/ble_throughput_client.py")
    parser.add_argument("--summary_csv", default="results/tables/ble_matrix_summary.csv")
    parser.add_argument("--start_cmd", default="0x01")
    parser.add_argument("--stop_cmd", default="0x02")
    parser.add_argument("--reset_cmd", default="0x03")
    return parser.parse_args()


def newest_log(out_dir: Path, before: set[str]) -> Path | None:
    candidates = [p for p in out_dir.glob("*ble_throughput*.json") if p.name not in before]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run_trial(args: argparse.Namespace, payload: int, trial: int, out_dir: Path) -> Dict[str, float] | None:
    print(f"\n=== Payload {payload} bytes | Trial {trial}/{args.repeats} ===")
    existing = {p.name for p in out_dir.glob("*ble_throughput*.json")}
    cmd = [
        sys.executable,
        args.client_script,
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
        "--start_cmd",
        str(args.start_cmd),
        "--stop_cmd",
        str(args.stop_cmd),
        "--reset_cmd",
        str(args.reset_cmd),
    ]
    subprocess.run(cmd, check=True)
    log_path = newest_log(out_dir, existing)
    if not log_path:
        print("[matrix] WARNING: Throughput script completed but no new JSON log was found.")
        return None
    with log_path.open() as handle:
        data = json.load(handle)
    summary = data["metadata"].get("summary", {})
    summary["payload_bytes"] = payload
    summary["trial"] = trial
    summary["log_json"] = str(log_path)
    summary["log_csv"] = data["metadata"].get("records_file", {}).get("csv")
    throughput = summary.get("throughput_kbps") or 0.0
    print(
        f"[matrix] packets={summary.get('packets')} loss={summary.get('estimated_lost_packets')} "
        f"throughput_kbps={throughput:.2f}"
    )
    return summary


def write_summary(rows: List[Dict[str, float]], csv_path: Path) -> None:
    if not rows:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "payload_bytes",
        "trial",
        "packets",
        "estimated_lost_packets",
        "duration_s",
        "throughput_kbps",
        "notification_rate_per_s",
        "log_json",
        "log_csv",
    ]
    with csv_path.open("w") as handle:
        handle.write(",".join(headers) + "\n")
        for row in rows:
            values = [str(row.get(col, "")) for col in headers]
            handle.write(",".join(values) + "\n")
    print(f"\n[matrix] Summary CSV written to {csv_path}")


def print_table(rows: List[Dict[str, float]]) -> None:
    if not rows:
        print("[matrix] No successful trials recorded.")
        return
    print("\n=== Aggregate Summary ===")
    header = f"{'Payload':>8} {'Trial':>5} {'Packets':>10} {'Loss':>6} {'Throughput(kbps)':>18}"
    print(header)
    for row in rows:
        throughput = row.get("throughput_kbps") or 0.0
        print(
            f"{row.get('payload_bytes'):>8} "
            f"{row.get('trial'):>5} "
            f"{row.get('packets', 0):>10} "
            f"{row.get('estimated_lost_packets', 0):>6} "
            f"{throughput:>18.2f}"
        )


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries: List[Dict[str, float]] = []
    for payload in args.payloads:
        for trial in range(1, args.repeats + 1):
            try:
                result = run_trial(args, payload, trial, out_dir)
            except subprocess.CalledProcessError as exc:
                print(f"[matrix] ERROR: Trial failed with return code {exc.returncode}")
                continue
            if result:
                summaries.append(result)
    print_table(summaries)
    write_summary(summaries, Path(args.summary_csv).expanduser())


if __name__ == "__main__":
    main()
