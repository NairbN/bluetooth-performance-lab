#!/usr/bin/env python3
"""Generate simple BLE throughput/loss plots from the summary table."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List, Tuple

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot BLE throughput/loss vs payload size.")
    parser.add_argument("--input", required=True, help="CSV summary file from ble_log_summarize.")
    parser.add_argument("--outdir", default="results/plots", help="Directory for generated plots.")
    parser.add_argument("--prefix", default="ble_summary", help="Filename prefix for plots.")
    return parser.parse_args()


def load_series(path: Path) -> Tuple[List[float], List[float], List[float]]:
    payloads: List[float] = []
    throughputs: List[float] = []
    losses: List[float] = []
    with path.open() as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            payload = row.get("payload_bytes")
            throughput = row.get("throughput_kbps")
            loss = row.get("loss_percent")
            if not payload or payload in {"", "None"}:
                continue
            try:
                payload_val = float(payload)
                throughput_val = float(throughput) if throughput else 0.0
                loss_val = float(loss) if loss else 0.0
            except ValueError:
                continue
            payloads.append(payload_val)
            throughputs.append(throughput_val)
            losses.append(loss_val)
    combined = sorted(zip(payloads, throughputs, losses), key=lambda item: item[0])
    if not combined:
        return [], [], []
    sorted_payloads, sorted_throughputs, sorted_losses = zip(*combined)
    return list(sorted_payloads), list(sorted_throughputs), list(sorted_losses)


def plot_series(x: List[float], y: List[float], xlabel: str, ylabel: str, title: str, output: Path):
    if not x:
        print(f"No plot data for {title}; skipping {output}")
        return
    plt.figure()
    plt.plot(x, y, marker="o")
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True, linestyle="--", alpha=0.4)
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output)
    plt.close()
    print(f"Wrote {output}")


def main():
    args = parse_args()
    summary_path = Path(args.input).expanduser()
    outdir = Path(args.outdir).expanduser()
    payloads, throughputs, losses = load_series(summary_path)
    plot_series(payloads, throughputs, "Payload bytes", "Throughput (kbps)", "Throughput vs Payload", outdir / f"{args.prefix}_throughput.png")
    plot_series(payloads, losses, "Payload bytes", "Loss (%)", "Loss vs Payload", outdir / f"{args.prefix}_loss.png")


if __name__ == "__main__":
    main()
