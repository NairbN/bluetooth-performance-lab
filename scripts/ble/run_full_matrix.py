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

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.patches import Patch

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
    parser.add_argument("--plots_dir", default="results/plots", help="Directory to store generated plots.")
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
    parser.add_argument(
        "--connect_timeout_s",
        type=float,
        default=20.0,
        help="Seconds to wait for throughput client connections before failing a trial.",
    )
    parser.add_argument(
        "--connect_attempts",
        type=int,
        default=3,
        help="Number of connection attempts to try per throughput run.",
    )
    parser.add_argument(
        "--connect_retry_delay_s",
        type=float,
        default=5.0,
        help="Seconds to wait between connection attempts when retries are enabled.",
    )
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
    subprocess.run(cmd, check=True)


def _progress(label: str, current: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return f"{label}: [????????] {current}/{total}"
    ratio = min(max(current / total, 0.0), 1.0)
    filled = int(ratio * width)
    bar = "#" * filled + "-" * (width - filled)
    return f"{label}: [{bar}] {current}/{total}"


def _plot_scenario(rows: List[Dict[str, float]], scenario: str, phy: str, plots_dir: Path) -> None:
    data: Dict[int, List[float]] = {}
    health: Dict[int, Dict[str, int]] = {}
    for row in rows:
        payload = row.get("payload_bytes")
        throughput = row.get("throughput_kbps")
        if not isinstance(payload, int):
            continue
        if not isinstance(throughput, (int, float)):
            continue
        data.setdefault(payload, []).append(float(throughput))
        stats = health.setdefault(payload, {"trials": 0, "retries": 0, "errors": 0})
        stats["trials"] += 1
        attempts = row.get("connection_attempts_used")
        errors = row.get("command_errors")
        if isinstance(attempts, (int, float)) and attempts > 1:
            stats["retries"] += 1
        if isinstance(errors, (int, float)) and errors > 0:
            stats["errors"] += 1
    if not data:
        return
    payloads = sorted(data.keys())
    averages = [sum(data[p]) / len(data[p]) for p in payloads]
    palette = {
        "clean": ("#27ae60", "Clean run"),
        "retry": ("#f39c12", "Needed connection retry"),
        "error": ("#c0392b", "Command/teardown error"),
    }

    def _bucket(stats: Dict[str, int]) -> str:
        if stats.get("errors"):
            return "error"
        if stats.get("retries"):
            return "retry"
        return "clean"

    color_order: List[str] = []
    colors: List[str] = []
    for payload in payloads:
        stats = health.get(payload, {})
        bucket = _bucket(stats)
        colors.append(palette[bucket][0])
        if bucket not in color_order:
            color_order.append(bucket)

    plt.figure()
    plt.plot(payloads, averages, color="#34495e", linewidth=1.2, alpha=0.8)
    plt.scatter(payloads, averages, c=colors, s=70, edgecolors="black", linewidths=0.5, zorder=3)
    plt.title(f"{scenario} | PHY {phy} Throughput")
    plt.xlabel("Payload (bytes)")
    plt.ylabel("Throughput (kbps)")
    plt.grid(True, linestyle="--", alpha=0.5)

    if color_order:
        handles = [Patch(facecolor=palette[key][0], edgecolor="none", label=palette[key][1]) for key in color_order]
        plt.legend(handles=handles, loc="best")

    plots_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{scenario}_{phy}_throughput".replace(" ", "_")
    path = plots_dir / f"{safe_name}.png"
    plt.savefig(path, bbox_inches="tight")
    plt.close()


def _plot_latency(latency_rows: List[Dict[str, float]], scenario: str, phy: str, plots_dir: Path) -> None:
    samples = [row for row in latency_rows if row.get("scenario") == scenario and row.get("phy") == phy]
    if not samples:
        return
    values = [row.get("avg_latency_s") for row in samples if isinstance(row.get("avg_latency_s"), (int, float))]
    if not values:
        return
    plt.figure()
    plt.bar(range(len(values)), values)
    plt.title(f"{scenario} | PHY {phy} Latency (avg per run)")
    plt.ylabel("Latency (s)")
    plt.xlabel("Run index")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plots_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{scenario}_{phy}_latency".replace(" ", "_")
    plt.tight_layout()
    plt.savefig(plots_dir / f"{safe_name}.png")
    plt.close()


def _plot_rssi(rssi_rows: List[Dict[str, float]], scenario: str, phy: str, plots_dir: Path) -> None:
    samples = [row for row in rssi_rows if row.get("scenario") == scenario and row.get("phy") == phy]
    if not samples:
        return
    available = [1 if row.get("rssi_available") else 0 for row in samples]
    if not available:
        return
    plt.figure()
    plt.bar(range(len(available)), available)
    plt.title(f"{scenario} | PHY {phy} RSSI availability")
    plt.ylabel("Has RSSI samples (1=yes, 0=no)")
    plt.xlabel("Run index")
    plt.ylim(0, 1.2)
    plots_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{scenario}_{phy}_rssi".replace(" ", "_")
    plt.tight_layout()
    plt.savefig(plots_dir / f"{safe_name}.png")
    plt.close()


def _plot_comparison_throughput(summaries: Dict[Tuple[str, str], Dict[str, float]], plots_dir: Path) -> None:
    palette = {
        "clean": ("#27ae60", "All runs clean"),
        "retry": ("#f39c12", "Had retries"),
        "error": ("#c0392b", "Had command errors"),
    }
    labels: List[str] = []
    values: List[float] = []
    colors: List[str] = []
    legend_order: List[str] = []
    for (scenario, phy), summary in summaries.items():
        avg = summary.get("avg_throughput_kbps")
        if avg is None:
            continue
        labels.append(f"{scenario}\n{phy}")
        values.append(avg)
        bucket = "clean"
        if summary.get("error_trials"):
            bucket = "error"
        elif summary.get("retry_trials"):
            bucket = "retry"
        color = palette[bucket][0]
        colors.append(color)
        if bucket not in legend_order:
            legend_order.append(bucket)

    if not labels:
        return
    plt.figure(figsize=(max(6, len(labels) * 0.8), 4))
    plt.bar(range(len(labels)), values, color=colors)
    plt.xticks(range(len(labels)), labels, rotation=45, ha="right")
    plt.ylabel("Avg Throughput (kbps)")
    plt.title("Scenario Comparison")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    if legend_order:
        handles = [Patch(facecolor=palette[key][0], edgecolor="none", label=palette[key][1]) for key in legend_order]
        plt.legend(handles=handles, loc="best")
    plots_dir.mkdir(parents=True, exist_ok=True)
    path = plots_dir / "scenario_comparison.png"
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def _plot_comparison_latency(latency_rows: List[Dict[str, float]], plots_dir: Path) -> None:
    entries = [
        (f"{row['scenario']}\n{row['phy']}", row["avg_latency_s"])
        for row in latency_rows
        if isinstance(row.get("avg_latency_s"), (int, float))
    ]
    if not entries:
        return
    labels, values = zip(*entries)
    plt.figure(figsize=(max(6, len(labels) * 0.8), 4))
    plt.bar(range(len(labels)), values)
    plt.xticks(range(len(labels)), labels, rotation=45, ha="right")
    plt.ylabel("Latency (s)")
    plt.title("Latency Comparison")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plots_dir.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(plots_dir / "scenario_comparison_latency.png")
    plt.close()


def _plot_comparison_rssi(rssi_rows: List[Dict[str, float]], plots_dir: Path) -> None:
    entries = [
        (f"{row['scenario']}\n{row['phy']}", 1 if row.get("rssi_available") else 0)
        for row in rssi_rows
    ]
    if not entries:
        return
    labels, values = zip(*entries)
    plt.figure(figsize=(max(6, len(labels) * 0.8), 4))
    plt.bar(range(len(labels)), values)
    plt.xticks(range(len(labels)), labels, rotation=45, ha="right")
    plt.ylabel("RSSI samples available")
    plt.title("RSSI Collection Status")
    plots_dir.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(plots_dir / "scenario_comparison_rssi.png")
    plt.close()


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
        "--connect_timeout_s",
        str(args.connect_timeout_s),
        "--connect_attempts",
        str(args.connect_attempts),
        "--connect_retry_delay_s",
        str(args.connect_retry_delay_s),
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
        "connection_attempts_used": summary.get("connection_attempts_used"),
        "command_errors": summary.get("command_errors"),
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
    results_dir = Path(args.results_dir).expanduser()
    plots_dir = Path(args.plots_dir).expanduser()
    throughput_rows: List[Dict[str, float]] = []
    latency_rows: List[Dict[str, float]] = []
    rssi_rows: List[Dict[str, float]] = []
    scenario_summaries: Dict[Tuple[str, str], Dict[str, float]] = {}

    def summarize_throughput(rows: List[Dict[str, float]]) -> Dict[str, float]:
        valid = [row for row in rows if isinstance(row.get("throughput_kbps"), (int, float))]
        if not valid:
            return {}
        avg = sum(row["throughput_kbps"] for row in valid) / len(valid)
        loss = sum(row.get("estimated_lost_packets", 0) for row in valid)
        packets = sum(row.get("packets", 0) for row in valid)
        retries = sum(
            1
            for row in valid
            if isinstance(row.get("connection_attempts_used"), (int, float)) and row["connection_attempts_used"] > 1
        )
        errors = sum(
            1
            for row in valid
            if isinstance(row.get("command_errors"), (int, float)) and row["command_errors"] > 0
        )
        return {
            "avg_throughput_kbps": avg,
            "total_packets": packets,
            "total_loss": loss,
            "total_trials": len(valid),
            "retry_trials": retries,
            "error_trials": errors,
        }

    scenario_total = len(args.scenarios) * len(args.phys)
    scenario_counter = 0

    try:
        for scenario in args.scenarios:
            if args.prompt:
                input(f"[runner] Position hardware for scenario '{scenario}', then press Enter to continue...")
            for phy in args.phys:
                scenario_counter += 1
                print(f"\n=== {_progress('Scenario', scenario_counter, scenario_total)} {scenario} | PHY {phy} ===")

                if not args.skip_throughput:
                    combo_total = len(args.payloads) * args.repeats
                    combo_counter = 0
                    for payload in args.payloads:
                        for trial in range(1, args.repeats + 1):
                            combo_counter += 1
                            print(
                                _progress("  Throughput", combo_counter, combo_total)
                                + f" payload={payload} trial={trial}",
                                flush=True,
                            )
                            summary = run_throughput_trial(args, scenario, phy, payload, trial, out_dir)
                            if summary:
                                throughput_rows.append(summary)
                if not args.skip_latency:
                    print("  Latency: collecting samples", flush=True)
                    summary = run_latency_trial(args, scenario, phy, 1, out_dir)
                    if summary:
                        latency_rows.append(summary)
                if not args.skip_rssi:
                    print("  RSSI: collecting samples", flush=True)
                    summary = run_rssi_trial(args, scenario, phy, 1, out_dir)
                    if summary:
                        rssi_rows.append(summary)

                scenario_rows = [
                    row for row in throughput_rows if row.get("scenario") == scenario and row.get("phy") == phy
                ]
                scenario_summary = summarize_throughput(scenario_rows)
                scenario_summaries[(scenario, phy)] = scenario_summary
                _plot_scenario(scenario_rows, scenario, phy, plots_dir)
                _plot_latency(latency_rows, scenario, phy, plots_dir)
                _plot_rssi(rssi_rows, scenario, phy, plots_dir)
                if scenario_summary:
                    print(
                        f"  Summary -> avg throughput: {scenario_summary['avg_throughput_kbps']:.2f} kbps, "
                        f"packets: {scenario_summary['total_packets']}, "
                        f"loss: {scenario_summary['total_loss']}"
                        + (
                            f", retries {scenario_summary['retry_trials']}/{scenario_summary['total_trials']}, "
                            f"cmd errors {scenario_summary['error_trials']}"
                            if scenario_summary.get("total_trials")
                            else ""
                        ),
                        flush=True,
                    )
                else:
                    print("  Summary -> no valid throughput data recorded.", flush=True)
    except KeyboardInterrupt:
        print("\n[runner] Interrupted by user; summarizing completed scenarios.")

    throughput_table = [
        "scenario",
        "phy",
        "payload_bytes",
        "trial",
        "packets",
        "estimated_lost_packets",
        "duration_s",
        "throughput_kbps",
        "notification_rate_per_s",
        "connection_attempts_used",
        "command_errors",
        "log_json",
        "log_csv",
        "notes",
    ]
    write_csv(throughput_rows, throughput_table, results_dir / "full_matrix_throughput.csv")
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

    if scenario_summaries:
        print("\n=== Scenario Comparison ===")
        for (scenario, phy), summary in scenario_summaries.items():
            if summary:
                print(
                    f"{scenario} | PHY {phy}: "
                    f"{summary['avg_throughput_kbps']:.2f} kbps avg, "
                    f"packets {summary['total_packets']}, "
                    f"loss {summary['total_loss']}"
                )
            else:
                print(f"{scenario} | PHY {phy}: no throughput data")
    _plot_comparison_throughput(scenario_summaries, plots_dir)
    _plot_comparison_latency(latency_rows, plots_dir)
    _plot_comparison_rssi(rssi_rows, plots_dir)


if __name__ == "__main__":
    main()
