#!/usr/bin/env python3
"""Summarize BLE throughput logs into table-friendly metrics.

This script ingests the CSV/JSON logs produced by
`scripts/ble/clients/ble_throughput_client.py` and emits a consolidated CSV table with
duration, packet counts, estimated loss, and jitter metrics.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize BLE throughput logs.")
    parser.add_argument("--input", required=True, help="Input file or directory containing CSV/JSON logs.")
    parser.add_argument("--out", required=True, help="Output CSV path under results/tables/.")
    return parser.parse_args()


def collect_inputs(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    results: List[Path] = []
    seen_stems = set()
    for candidate in sorted(path.glob("*")):
        if not candidate.is_file():
            continue
        suffix = candidate.suffix.lower()
        stem = candidate.stem
        if suffix == ".json":
            results.append(candidate)
            seen_stems.add(stem)
        elif suffix == ".csv" and stem not in seen_stems:
            results.append(candidate)
    return results


def load_records(file_path: Path) -> Tuple[List[Dict[str, float]], Optional[Dict[str, object]]]:
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        data = json.loads(file_path.read_text())
        records = [
            {
                "seq": entry.get("seq", -1),
                "raw_len": entry.get("raw_len", entry.get("payload_len", 0) + 4),
                "arrival_epoch": entry.get("arrival_epoch"),
            }
            for entry in data.get("packets", [])
            if entry.get("arrival_epoch") is not None
        ]
        return records, data.get("metadata")

    if suffix == ".csv":
        records = []
        with file_path.open() as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                arrival = row.get("arrival_epoch")
                if not arrival:
                    continue
                records.append(
                    {
                        "seq": int(row.get("seq", -1)),
                        "raw_len": int(row.get("raw_len", row.get("payload_len", 0))),
                        "arrival_epoch": float(arrival),
                    }
                )
        sibling = file_path.with_suffix(".json")
        metadata = None
        if sibling.exists():
            metadata = json.loads(sibling.read_text()).get("metadata")
        return records, metadata

    raise ValueError(f"Unsupported log format: {file_path}")


def summarize(records: Iterable[Dict[str, float]]) -> Dict[str, float]:
    packets = list(records)
    if not packets:
        return {
            "duration_s": 0.0,
            "packets_received": 0,
            "estimated_packets_lost": 0,
            "loss_percent": 0.0,
            "throughput_kbps": 0.0,
            "avg_interarrival_ms": 0.0,
            "jitter_ms": 0.0,
        }

    packets.sort(key=lambda item: item["arrival_epoch"])
    start = packets[0]["arrival_epoch"]
    end = packets[-1]["arrival_epoch"]
    duration = max(0.0, end - start)

    total_bytes = sum(int(item["raw_len"]) for item in packets)
    prev_seq = None
    lost = 0
    valid_packets = 0
    for item in packets:
        seq = int(item.get("seq", -1))
        if seq < 0:
            continue
        valid_packets += 1
        if prev_seq is not None:
            gap = (seq - prev_seq) & 0xFFFF
            if gap > 1:
                lost += gap - 1
        prev_seq = seq

    denominator = valid_packets + lost
    loss_percent = (lost / denominator * 100.0) if denominator else 0.0
    throughput = (total_bytes * 8 / 1000.0) / duration if duration > 0 else 0.0

    interarrivals: List[float] = []
    for idx in range(1, len(packets)):
        delta = packets[idx]["arrival_epoch"] - packets[idx - 1]["arrival_epoch"]
        if delta >= 0:
            interarrivals.append(delta * 1000.0)
    if interarrivals:
        avg_interarrival = sum(interarrivals) / len(interarrivals)
        jitter = statistics.pstdev(interarrivals) if len(interarrivals) > 1 else 0.0
    else:
        avg_interarrival = 0.0
        jitter = 0.0

    return {
        "duration_s": duration,
        "packets_received": valid_packets,
        "estimated_packets_lost": lost,
        "loss_percent": loss_percent,
        "throughput_kbps": throughput,
        "avg_interarrival_ms": avg_interarrival,
        "jitter_ms": jitter,
    }


def main():
    args = parse_args()
    input_path = Path(args.input).expanduser()
    output_path = Path(args.out).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, object]] = []
    for path in collect_inputs(input_path):
        records, metadata = load_records(path)
        stats = summarize(records)
        payload = None
        if metadata:
            payload = metadata.get("payload_bytes_requested") or metadata.get("payload_bytes")
        row = {
            "source": str(path),
            "payload_bytes": payload,
            **stats,
        }
        rows.append(row)

    fieldnames = [
        "source",
        "payload_bytes",
        "duration_s",
        "packets_received",
        "estimated_packets_lost",
        "loss_percent",
        "throughput_kbps",
        "avg_interarrival_ms",
        "jitter_ms",
    ]
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Wrote {len(rows)} summaries to {output_path}")


if __name__ == "__main__":
    main()
