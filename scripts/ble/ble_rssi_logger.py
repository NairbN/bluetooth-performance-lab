#!/usr/bin/env python3
"""BLE RSSI logger for Smart Ring DUT validation.

Attempts to collect RSSI (or equivalent link quality metrics) at a fixed cadence.
If the platform does not expose continuous RSSI, the script records the
limitation in the log so future tooling can decide whether to fall back to a
different adapter or API.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bleak import BleakClient


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


async def _read_rssi(client: BleakClient) -> Optional[int]:
    """Best-effort RSSI accessor that tolerates backend differences."""
    getter = getattr(client, "get_rssi", None)
    if callable(getter):
        try:
            return int(await getter())
        except Exception:  # pragma: no cover - backend-specific behavior
            pass

    backend = getattr(client, "_backend", None)
    if backend is not None:
        value = None
        attr = getattr(backend, "rssi", None)
        if callable(attr):
            try:
                value = attr()
            except Exception:  # pragma: no cover
                value = None
        elif isinstance(attr, (int, float)):
            value = attr
        if value is None:
            props = getattr(backend, "_properties", None)
            if isinstance(props, dict):
                value = props.get("RSSI")
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


async def run_rssi_logger(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.out).expanduser()
    _ensure_output_dir(output_dir)
    timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_name = f"{timestamp_tag}_ble_rssi"
    csv_path = output_dir / f"{base_name}.csv"
    json_path = output_dir / f"{base_name}.json"

    metadata: Dict[str, Any] = {
        "created": _utc_now(),
        "address": args.address,
        "samples_requested": args.samples,
        "interval_s": args.interval_s,
        "notes": [],
    }
    records: List[Dict[str, Any]] = []

    async with BleakClient(args.address) as client:
        metadata["adapter"] = getattr(client, "adapter", "unknown")
        metadata["connected_at"] = _utc_now()
        metadata["rssi_sampling"] = (
            "Requested via bleak client APIs; entries with null RSSI indicate backend limitations."
        )

        for idx in range(1, args.samples + 1):
            rssi = await _read_rssi(client)
            if rssi is None:
                note = "RSSI not exposed by backend"
                metadata["notes"].append(note)
            records.append(
                {
                    "index": idx,
                    "timestamp": _utc_now(),
                    "rssi_dbm": rssi,
                }
            )
            await asyncio.sleep(args.interval_s)

    if metadata["notes"]:
        metadata["notes"] = sorted(set(metadata["notes"]))
    metadata["records_file"] = {"csv": str(csv_path), "json": str(json_path)}

    fieldnames = ["index", "timestamp", "rssi_dbm"]
    with csv_path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record)

    json_blob = {"metadata": metadata, "samples": records}
    with json_path.open("w") as json_file:
        json.dump(json_blob, json_file, indent=2)

    return {
        "samples_collected": len(records),
        "rssi_available": any(r["rssi_dbm"] is not None for r in records),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BLE RSSI logger for Smart Ring DUT.")
    parser.add_argument("--address", required=True, help="BLE address of the DUT (e.g., AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--samples", type=int, default=20, help="Number of RSSI samples to attempt.")
    parser.add_argument("--interval_s", type=float, default=1.0, help="Delay between samples in seconds.")
    parser.add_argument("--out", default="logs/ble", help="Output directory for CSV/JSON logs.")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        summary = asyncio.run(run_rssi_logger(args))
    except KeyboardInterrupt:
        print("Interrupted by user; partial RSSI log retained.")
        return
    print("RSSI logging summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
