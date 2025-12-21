#!/usr/bin/env python3
"""Shared orchestration for throughput/latency/RSSI sweeps."""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.patches import Patch

    _mpl_version = getattr(matplotlib, "__version__", "unknown")
    _mpl_available = True
except Exception:  # pylint: disable=broad-except
    plt = None  # type: ignore
    Patch = None  # type: ignore
    _mpl_version = "unavailable"
    _mpl_available = False


UUID_RE = re.compile(r"^[0-9a-fA-F-]{16,36}$")


def _validate_uuid(value: str, name: str) -> None:
    if not UUID_RE.match(value):
        raise ValueError(f"{name} does not look like a UUID: {value}")


def _validate_payload(value: int) -> None:
    if not 20 <= int(value) <= 244:
        raise ValueError(f"Payload {value} is outside 20-244 bytes (ATT constraints).")


def _validate_paths(args, fields: Sequence[str]) -> None:
    for field in fields:
        path = Path(getattr(args, field)).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Script path not found for --{field.replace('_', '-')}: {path}")


def _validate_config(args) -> None:
    _validate_uuid(args.service_uuid, "service_uuid")
    _validate_uuid(args.tx_uuid, "tx_uuid")
    _validate_uuid(args.rx_uuid, "rx_uuid")
    for value in getattr(args, "payloads", []):
        _validate_payload(value)
    if getattr(args, "validate_paths", False):
        to_check = []
        for field in ["throughput_script", "latency_script", "rssi_script", "client_script"]:
            if hasattr(args, field):
                to_check.append(field)
        _validate_paths(args, to_check)


def _acquire_lock(lock_dir: Path, key: str):
    """Simple per-adapter lock to avoid concurrent runs on the same adapter/address."""
    lock_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", key or "default")
    path = lock_dir / f"{name}.lock"
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, b"locked")
        return (fd, path)
    except FileExistsError:
        raise RuntimeError(f"Another run appears to be using {key}; lock {path} exists.")


def _release_lock(lock):
    if not lock:
        return
    fd, path = lock
    try:
        os.close(fd)
    except Exception:
        pass
    try:
        os.unlink(path)
    except Exception:
        pass


def _run_cmd(cmd: Sequence[str]) -> None:
    subprocess.run(cmd, check=True)


def _progress(label: str, current: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return f"{label}: [????????] {current}/{total}"
    ratio = min(max(current / total, 0.0), 1.0)
    filled = int(ratio * width)
    bar = "#" * filled + "-" * (width - filled)
    return f"{label}: [{bar}] {current}/{total}"


class LogTracker:
    """Tracks log files before/after a subprocess run to locate new outputs."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir

    def snapshot(self, pattern: str) -> Dict[str, Path]:
        return {p.name: p for p in self.out_dir.glob(pattern)}

    def newest_after(self, pattern: str, before: Dict[str, Path]) -> Optional[Path]:
        after = self.snapshot(pattern)
        new_entries = [path for name, path in after.items() if name not in before]
        if not new_entries:
            return None
        return max(new_entries, key=lambda p: p.stat().st_mtime)


@dataclass
class ThroughputConfig:
    script: str
    address: str
    service_uuid: str
    tx_uuid: str
    rx_uuid: str
    duration_s: float
    mtu: int
    start_cmd: str | int
    stop_cmd: str | int
    reset_cmd: str | int
    connect_timeout_s: float
    connect_attempts: int
    connect_retry_delay_s: float
    note: str = ""


class ThroughputTrialRunner:
    """Runs a single throughput trial and returns the parsed summary row."""

    def __init__(self, config: ThroughputConfig, out_dir: Path):
        self.config = config
        self.out_dir = out_dir
        self.logs = LogTracker(out_dir)

    def run(self, payload: int, trial: int, *, scenario: str | None, phy: str | None) -> Optional[Dict[str, float]]:
        _validate_payload(payload)
        before = self.logs.snapshot("*ble_throughput*.json")
        cmd = [
            sys.executable,
            self.config.script,
            "--address",
            self.config.address,
            "--service_uuid",
            self.config.service_uuid,
            "--tx_uuid",
            self.config.tx_uuid,
            "--rx_uuid",
            self.config.rx_uuid,
            "--payload_bytes",
            str(payload),
            "--duration_s",
            str(self.config.duration_s),
            "--out",
            str(self.out_dir),
            "--start_cmd",
            str(self.config.start_cmd),
            "--stop_cmd",
            str(self.config.stop_cmd),
            "--reset_cmd",
            str(self.config.reset_cmd),
            "--mtu",
            str(self.config.mtu),
            "--connect_timeout_s",
            str(self.config.connect_timeout_s),
            "--connect_attempts",
            str(self.config.connect_attempts),
            "--connect_retry_delay_s",
            str(self.config.connect_retry_delay_s),
        ]
        if phy:
            cmd += ["--phy", phy]
        _run_cmd(cmd)
        log_path = self.logs.newest_after("*ble_throughput*.json", before)
        if not log_path:
            print("[runner] WARNING: throughput log not found.")
            return None
        with log_path.open() as handle:
            data = json.load(handle)
        summary = data["metadata"].get("summary", {})
        return {
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
            "notes": self.config.note,
        }


@dataclass
class LatencyConfig:
    script: str
    address: str
    service_uuid: str
    tx_uuid: str
    rx_uuid: str
    payload_bytes: int
    mode: str
    iterations: int
    mtu: int
    start_cmd: str | int
    stop_cmd: str | int
    reset_cmd: str | int
    connect_timeout_s: float
    connect_attempts: int
    connect_retry_delay_s: float
    note: str = ""


class LatencyTrialRunner:
    """Runs the latency client once for a given scenario/PHY."""

    def __init__(self, config: LatencyConfig, out_dir: Path):
        self.config = config
        self.out_dir = out_dir
        self.logs = LogTracker(out_dir)

    def run(self, *, scenario: str, phy: str, trial: int) -> Optional[Dict[str, float]]:
        before = self.logs.snapshot("*ble_latency*.json")
        cmd = [
            sys.executable,
            self.config.script,
            "--address",
            self.config.address,
            "--service_uuid",
            self.config.service_uuid,
            "--tx_uuid",
            self.config.tx_uuid,
            "--rx_uuid",
            self.config.rx_uuid,
            "--payload_bytes",
            str(self.config.payload_bytes),
            "--mode",
            self.config.mode,
            "--iterations",
            str(self.config.iterations),
            "--out",
            str(self.out_dir),
            "--phy",
            phy,
            "--mtu",
            str(self.config.mtu),
            "--start_cmd",
            str(self.config.start_cmd),
            "--stop_cmd",
            str(self.config.stop_cmd),
            "--reset_cmd",
            str(self.config.reset_cmd),
            "--connect_timeout_s",
            str(self.config.connect_timeout_s),
            "--connect_attempts",
            str(self.config.connect_attempts),
            "--connect_retry_delay_s",
            str(self.config.connect_retry_delay_s),
        ]
        _run_cmd(cmd)
        log_path = self.logs.newest_after("*ble_latency*.json", before)
        if not log_path:
            print("[runner] WARNING: latency log not found.")
            return None
        with log_path.open() as handle:
            data = json.load(handle)
        summary = data["metadata"].get("summary", {})
        return {
            "scenario": scenario,
            "phy": phy,
            "trial": trial,
            "mode": self.config.mode,
            "avg_latency_s": summary.get("avg_latency_s"),
            "min_latency_s": summary.get("min_latency_s"),
            "max_latency_s": summary.get("max_latency_s"),
            "samples": summary.get("samples"),
            "timeouts": summary.get("timeouts"),
            "log_json": str(log_path),
            "log_csv": data["metadata"].get("records_file", {}).get("csv"),
            "notes": self.config.note,
        }


@dataclass
class RssiConfig:
    script: str
    address: str
    samples: int
    interval_s: float
    connect_timeout_s: float
    connect_attempts: int
    connect_retry_delay_s: float
    note: str = ""


class RssiTrialRunner:
    """Runs the RSSI logger once for a given scenario/PHY."""

    def __init__(self, config: RssiConfig, out_dir: Path):
        self.config = config
        self.out_dir = out_dir
        self.logs = LogTracker(out_dir)

    def run(self, *, scenario: str, phy: str, trial: int) -> Optional[Dict[str, float]]:
        before = self.logs.snapshot("*ble_rssi*.json")
        cmd = [
            sys.executable,
            self.config.script,
            "--address",
            self.config.address,
            "--samples",
            str(self.config.samples),
            "--interval_s",
            str(self.config.interval_s),
            "--out",
            str(self.out_dir),
            "--connect_timeout_s",
            str(self.config.connect_timeout_s),
            "--connect_attempts",
            str(self.config.connect_attempts),
            "--connect_retry_delay_s",
            str(self.config.connect_retry_delay_s),
        ]
        _run_cmd(cmd)
        log_path = self.logs.newest_after("*ble_rssi*.json", before)
        if not log_path:
            print("[runner] WARNING: RSSI log not found.")
            return None
        with log_path.open() as handle:
            data = json.load(handle)
        metadata = data.get("metadata", {})
        return {
            "scenario": scenario,
            "phy": phy,
            "trial": trial,
            "samples_collected": metadata.get("samples_requested"),
            "rssi_available": any(sample.get("rssi_dbm") is not None for sample in data.get("samples", [])),
            "log_json": str(log_path),
            "log_csv": metadata.get("records_file", {}).get("csv"),
            "notes": self.config.note,
        }


class MatrixPlotter:
    """Handles per-scenario and comparison plots."""

    def __init__(self, plots_dir: Path):
        self.plots_dir = plots_dir
        self.available = _mpl_available
        if not self.available:
            print("[plots] WARNING: matplotlib not available; skipping plot generation.")

    def plot_scenario(self, rows: List[Dict[str, float]], scenario: str, phy: str) -> None:
        if not self.available:
            return
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
            print(f"[plots] No throughput data for {scenario} | {phy}; skipping plot.")
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

        self.plots_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{scenario}_{phy}_throughput".replace(" ", "_")
        path = self.plots_dir / f"{safe_name}.png"
        plt.savefig(path, bbox_inches="tight")
        plt.close()

    def plot_latency(self, latency_rows: List[Dict[str, float]], scenario: str, phy: str) -> None:
        if not self.available:
            return
        samples = [row for row in latency_rows if row.get("scenario") == scenario and row.get("phy") == phy]
        if not samples:
            print(f"[plots] No latency data for {scenario} | {phy}; skipping plot.")
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
        self.plots_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{scenario}_{phy}_latency".replace(" ", "_")
        plt.tight_layout()
        plt.savefig(self.plots_dir / f"{safe_name}.png")
        plt.close()

    def plot_rssi(self, rssi_rows: List[Dict[str, float]], scenario: str, phy: str) -> None:
        if not self.available:
            return
        samples = [row for row in rssi_rows if row.get("scenario") == scenario and row.get("phy") == phy]
        if not samples:
            print(f"[plots] No RSSI data for {scenario} | {phy}; skipping plot.")
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
        self.plots_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{scenario}_{phy}_rssi".replace(" ", "_")
        plt.tight_layout()
        plt.savefig(self.plots_dir / f"{safe_name}.png")
        plt.close()

    def plot_comparison_throughput(self, summaries: Dict[Tuple[str, str], Dict[str, float]]) -> None:
        if not self.available:
            return
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
        self.plots_dir.mkdir(parents=True, exist_ok=True)
        path = self.plots_dir / "scenario_comparison.png"
        plt.tight_layout()
        plt.savefig(path)
        plt.close()

    def plot_comparison_latency(self, latency_rows: List[Dict[str, float]]) -> None:
        if not self.available:
            return
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
        self.plots_dir.mkdir(parents=True, exist_ok=True)
        plt.tight_layout()
        plt.savefig(self.plots_dir / "scenario_comparison_latency.png")
        plt.close()

    def plot_comparison_rssi(self, rssi_rows: List[Dict[str, float]]) -> None:
        if not self.available:
            return
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
        self.plots_dir.mkdir(parents=True, exist_ok=True)
        plt.tight_layout()
        plt.savefig(self.plots_dir / "scenario_comparison_rssi.png")
        plt.close()


def write_csv(rows: List[Dict[str, float]], headers: Sequence[str], path: Path) -> None:
    if not rows:
        print(f"[runner] WARNING: no rows to write for {path.name}; skipping file.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        handle.write(",".join(headers) + "\n")
        for row in rows:
            values = [str(row.get(field, "")) for field in headers]
            handle.write(",".join(values) + "\n")
    print(f"[runner] Wrote {len(rows)} rows to {path}")


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


def _load_completed_trials(csv_path: Path) -> set[Tuple[str, str, int, int]]:
    if not csv_path.exists():
        return set()
    completed = set()
    try:
        with csv_path.open() as handle:
            header = handle.readline().strip().split(",")
            idx = {name: pos for pos, name in enumerate(header)}
            for line in handle:
                parts = line.strip().split(",")
                try:
                    scenario = parts[idx["scenario"]]
                    phy = parts[idx["phy"]]
                    payload = int(parts[idx["payload_bytes"]])
                    trial = int(parts[idx["trial"]])
                    completed.add((scenario, phy, payload, trial))
                except Exception:
                    continue
    except Exception:
        return set()
    if completed:
        print(f"[runner] Resume enabled; skipping {len(completed)} previously recorded trials.")
    return completed


@dataclass
class FullMatrixResults:
    throughput_rows: List[Dict[str, float]]
    latency_rows: List[Dict[str, float]]
    rssi_rows: List[Dict[str, float]]
    scenario_summaries: Dict[Tuple[str, str], Dict[str, float]]
    errors: List[str]


class FullMatrixRunner:
    """Coordinates payload/PHY/scenario sweeps across throughput, latency, and RSSI."""

    def __init__(self, args):
        self.args = args
        _validate_config(args)
        self.out_dir = Path(args.out).expanduser()
        self.results_dir = Path(args.results_dir).expanduser()
        self.plots_dir = Path(args.plots_dir).expanduser()
        self.manifest_dir = Path(getattr(args, "manifest_dir", "results/manifests")).expanduser()
        self.lock_dir = Path(getattr(args, "lock_dir", "/tmp/ble_runner_locks")).expanduser()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.plotter = MatrixPlotter(self.plots_dir)
        self.throughput_runner = ThroughputTrialRunner(
            ThroughputConfig(
                script=args.throughput_script,
                address=args.address,
                service_uuid=args.service_uuid,
                tx_uuid=args.tx_uuid,
                rx_uuid=args.rx_uuid,
                duration_s=args.duration_s,
                mtu=args.mtu,
                start_cmd=args.start_cmd,
                stop_cmd=args.stop_cmd,
                reset_cmd=args.reset_cmd,
                connect_timeout_s=args.connect_timeout_s,
                connect_attempts=args.connect_attempts,
                connect_retry_delay_s=args.connect_retry_delay_s,
                note=args.note,
            ),
            self.out_dir,
        )
        self.latency_runner = LatencyTrialRunner(
            LatencyConfig(
                script=args.latency_script,
                address=args.address,
                service_uuid=args.service_uuid,
                tx_uuid=args.tx_uuid,
                rx_uuid=args.rx_uuid,
                payload_bytes=max(20, min(244, args.payloads[-1])),
                mode=args.latency_mode,
                iterations=args.latency_iterations,
                mtu=args.mtu,
                start_cmd=args.start_cmd,
                stop_cmd=args.stop_cmd,
                reset_cmd=args.reset_cmd,
                connect_timeout_s=args.connect_timeout_s,
                connect_attempts=args.connect_attempts,
                connect_retry_delay_s=args.connect_retry_delay_s,
                note=args.note,
            ),
            self.out_dir,
        )
        self.rssi_runner = RssiTrialRunner(
            RssiConfig(
                script=args.rssi_script,
                address=args.address,
                samples=args.rssi_samples,
                interval_s=args.rssi_interval_s,
                connect_timeout_s=args.connect_timeout_s,
                connect_attempts=args.connect_attempts,
                connect_retry_delay_s=args.connect_retry_delay_s,
                note=args.note,
            ),
            self.out_dir,
        )

    def run(self) -> FullMatrixResults:
        lock = _acquire_lock(self.lock_dir, self.args.address)
        started_at = datetime.now(timezone.utc).isoformat()
        throughput_rows: List[Dict[str, float]] = []
        latency_rows: List[Dict[str, float]] = []
        rssi_rows: List[Dict[str, float]] = []
        scenario_summaries: Dict[Tuple[str, str], Dict[str, float]] = {}
        scenario_errors: List[str] = []
        skip_trials = _load_completed_trials(self.results_dir / "full_matrix_throughput.csv") if getattr(self.args, "resume", False) else set()

        scenario_total = len(self.args.scenarios) * len(self.args.phys)
        scenario_counter = 0

        try:
            for scenario in self.args.scenarios:
                if self.args.prompt:
                    input(f"[runner] Position hardware for scenario '{scenario}', then press Enter to continue...")
                for phy in self.args.phys:
                    scenario_counter += 1
                    print(f"\n=== {_progress('Scenario', scenario_counter, scenario_total)} {scenario} | PHY {phy} ===")

                    scenario_rows = throughput_rows

                    if not self.args.skip_throughput:
                        combo_total = len(self.args.payloads) * self.args.repeats
                        combo_counter = 0
                        for payload in self.args.payloads:
                            for trial in range(1, self.args.repeats + 1):
                                combo_counter += 1
                                key = (scenario, phy, payload, trial)
                                if key in skip_trials:
                                    print(
                                        _progress("  Throughput", combo_counter, combo_total)
                                        + f" payload={payload} trial={trial} [skipped resume]",
                                        flush=True,
                                    )
                                    continue
                                print(
                                    _progress("  Throughput", combo_counter, combo_total)
                                    + f" payload={payload} trial={trial}",
                                    flush=True,
                                )
                                try:
                                    summary = self.throughput_runner.run(payload, trial, scenario=scenario, phy=phy)
                                    if summary:
                                        throughput_rows.append(summary)
                                except Exception as exc:  # pylint: disable=broad-except
                                    scenario_errors.append(
                                        f"{scenario}|{phy} throughput payload={payload} trial={trial}: {exc}"
                                    )
                                    print(f"[runner] ERROR: {scenario_errors[-1]}", flush=True)
                    if not self.args.skip_latency:
                        print("  Latency: collecting samples", flush=True)
                        try:
                            summary = self.latency_runner.run(scenario=scenario, phy=phy, trial=1)
                            if summary:
                                latency_rows.append(summary)
                        except Exception as exc:  # pylint: disable=broad-except
                            scenario_errors.append(f"{scenario}|{phy} latency: {exc}")
                            print(f"[runner] ERROR: {scenario_errors[-1]}", flush=True)
                    if not self.args.skip_rssi:
                        print("  RSSI: collecting samples", flush=True)
                        try:
                            summary = self.rssi_runner.run(scenario=scenario, phy=phy, trial=1)
                            if summary:
                                rssi_rows.append(summary)
                        except Exception as exc:  # pylint: disable=broad-except
                            scenario_errors.append(f"{scenario}|{phy} rssi: {exc}")
                            print(f"[runner] ERROR: {scenario_errors[-1]}", flush=True)

                    scenario_trials = [
                        row for row in scenario_rows if row.get("scenario") == scenario and row.get("phy") == phy
                    ]
                    scenario_summary = summarize_throughput(scenario_trials)
                    scenario_summaries[(scenario, phy)] = scenario_summary
                    self.plotter.plot_scenario(scenario_trials, scenario, phy)
                    self.plotter.plot_latency(latency_rows, scenario, phy)
                    self.plotter.plot_rssi(rssi_rows, scenario, phy)
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

        if scenario_errors:
            print("\n[runner] Completed with errors:")
            for err in scenario_errors:
                print(f"  - {err}")

        ended_at = datetime.now(timezone.utc).isoformat()
        results = FullMatrixResults(
            throughput_rows=throughput_rows,
            latency_rows=latency_rows,
            rssi_rows=rssi_rows,
            scenario_summaries=scenario_summaries,
            errors=scenario_errors,
        )
        self._write_manifest(results, started_at, ended_at)
        _release_lock(lock)
        return results

    def write_outputs(self, results: FullMatrixResults) -> None:
        write_csv(
            results.throughput_rows,
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
                "connection_attempts_used",
                "command_errors",
                "log_json",
                "log_csv",
                "notes",
            ],
            self.results_dir / "full_matrix_throughput.csv",
        )
        write_csv(
            results.latency_rows,
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
            self.results_dir / "full_matrix_latency.csv",
        )
        write_csv(
            results.rssi_rows,
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
            self.results_dir / "full_matrix_rssi.csv",
        )

        if results.scenario_summaries:
            print("\n=== Scenario Comparison ===")
            for (scenario, phy), summary in results.scenario_summaries.items():
                if summary:
                    print(
                        f"{scenario} | PHY {phy}: "
                        f"{summary['avg_throughput_kbps']:.2f} kbps avg, "
                        f"packets {summary['total_packets']}, "
                        f"loss {summary['total_loss']}"
                    )
                else:
                    print(f"{scenario} | PHY {phy}: no throughput data")
        try:
            self.plotter.plot_comparison_throughput(results.scenario_summaries)
            self.plotter.plot_comparison_latency(results.latency_rows)
            self.plotter.plot_comparison_rssi(results.rssi_rows)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[plots] WARNING: comparison plots failed ({exc}). Matplotlib {_mpl_version}")

    def _write_manifest(self, results: FullMatrixResults, started_at: str, ended_at: str) -> None:
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        manifest = {
            "run_id": run_id,
            "type": "full_matrix",
            "address": self.args.address,
            "scenarios": self.args.scenarios,
            "phys": self.args.phys,
            "payloads": self.args.payloads,
            "repeats": self.args.repeats,
            "started_at": started_at,
            "ended_at": ended_at,
            "status": "completed_with_errors" if results.errors else "completed",
            "errors": results.errors,
            "outputs": {
                "throughput_csv": str(self.results_dir / "full_matrix_throughput.csv"),
                "latency_csv": str(self.results_dir / "full_matrix_latency.csv"),
                "rssi_csv": str(self.results_dir / "full_matrix_rssi.csv"),
                "plots_dir": str(self.plots_dir),
            },
            "summary": {f"{k[0]}|{k[1]}": v for k, v in results.scenario_summaries.items()},
            "args": {
                "note": self.args.note,
                "mtu": self.args.mtu,
                "connect_timeout_s": self.args.connect_timeout_s,
                "connect_attempts": self.args.connect_attempts,
                "connect_retry_delay_s": self.args.connect_retry_delay_s,
            },
        }
        path = self.manifest_dir / f"{run_id}_manifest.json"
        try:
            with path.open("w") as handle:
                json.dump(manifest, handle, indent=2)
            print(f"[runner] Manifest written to {path}")
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[runner] WARNING: failed to write manifest ({exc})")


class ThroughputMatrixRunner:
    """Throughput-only payload sweep used by lab automation."""

    def __init__(self, args):
        self.args = args
        _validate_config(args)
        self.out_dir = Path(args.out).expanduser()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_dir = Path(getattr(args, "manifest_dir", "results/manifests")).expanduser()
        self.lock_dir = Path(getattr(args, "lock_dir", "/tmp/ble_runner_locks")).expanduser()
        self.runner = ThroughputTrialRunner(
            ThroughputConfig(
                script=args.client_script,
                address=args.address,
                service_uuid=args.service_uuid,
                tx_uuid=args.tx_uuid,
                rx_uuid=args.rx_uuid,
                duration_s=args.duration_s,
                mtu=args.mtu,
                start_cmd=args.start_cmd,
                stop_cmd=args.stop_cmd,
                reset_cmd=args.reset_cmd,
                connect_timeout_s=args.connect_timeout_s,
                connect_attempts=args.connect_attempts,
                connect_retry_delay_s=args.connect_retry_delay_s,
                note="",
            ),
            self.out_dir,
        )

    def run(self) -> List[Dict[str, float]]:
        lock = _acquire_lock(self.lock_dir, self.args.address)
        started_at = datetime.now(timezone.utc).isoformat()
        summaries: List[Dict[str, float]] = []
        total = len(self.args.payloads) * self.args.repeats
        counter = 0
        for payload in self.args.payloads:
            _validate_payload(payload)
            for trial in range(1, self.args.repeats + 1):
                counter += 1
                print(f"\n=== {_progress('Throughput', counter, total)} payload={payload} trial={trial} ===")
                try:
                    result = self.runner.run(payload, trial, scenario=None, phy=self.args.phy)
                except subprocess.CalledProcessError as exc:
                    print(f"[matrix] ERROR: Trial failed with return code {exc.returncode}")
                    continue
                if result:
                    summaries.append(result)
        ended_at = datetime.now(timezone.utc).isoformat()
        self._write_manifest(summaries, started_at, ended_at)
        _release_lock(lock)
        return summaries

    @staticmethod
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

    def write_outputs(self, rows: List[Dict[str, float]]) -> None:
        write_csv(
            rows,
            [
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
            ],
            Path(self.args.summary_csv).expanduser(),
        )

    def _write_manifest(self, rows: List[Dict[str, float]], started_at: str, ended_at: str) -> None:
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        manifest = {
            "run_id": run_id,
            "type": "throughput_matrix",
            "address": self.args.address,
            "phy": self.args.phy,
            "payloads": self.args.payloads,
            "repeats": self.args.repeats,
            "started_at": started_at,
            "ended_at": ended_at,
            "status": "completed",
            "errors": [],
            "outputs": {
                "throughput_csv": str(Path(self.args.summary_csv).expanduser()),
                "logs_dir": str(self.out_dir),
            },
            "args": {
                "mtu": self.args.mtu,
                "connect_timeout_s": self.args.connect_timeout_s,
                "connect_attempts": self.args.connect_attempts,
                "connect_retry_delay_s": self.args.connect_retry_delay_s,
            },
            "results_count": len(rows),
        }
        path = self.manifest_dir / f"{run_id}_manifest.json"
        try:
            with path.open("w") as handle:
                json.dump(manifest, handle, indent=2)
            print(f"[matrix] Manifest written to {path}")
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[matrix] WARNING: failed to write manifest ({exc})")
