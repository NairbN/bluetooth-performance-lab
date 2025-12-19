"""RSSI logging client for the Smart Ring BLE test service."""

from __future__ import annotations

import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bleak import BleakClient


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RssiClient:
    """Samples RSSI at a fixed cadence (best effort)."""

    def __init__(self, args):
        self.args = args
        self.records: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {
            "created": utc_now(),
            "address": args.address,
            "samples_requested": args.samples,
            "interval_s": args.interval_s,
            "notes": [],
        }
        self.mock_rssi_uuid: Optional[str] = getattr(args, "mock_rssi_uuid", None) or None
        self._mock_rssi_supported: Optional[bool] = None
        self._mock_rssi_noted = False

    async def run(self) -> Dict[str, Any]:
        output_dir = Path(self.args.out).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base_name = f"{timestamp_tag}_ble_rssi"
        self.csv_path = output_dir / f"{base_name}.csv"
        self.json_path = output_dir / f"{base_name}.json"

        async with BleakClient(self.args.address) as client:
            self.metadata["adapter"] = getattr(client, "adapter", "unknown")
            self.metadata["connected_at"] = utc_now()
            self.metadata["rssi_sampling"] = (
                "Requested via bleak client APIs; entries with null RSSI indicate backend limitations."
            )
            if self.mock_rssi_uuid:
                self.metadata["mock_rssi_uuid"] = self.mock_rssi_uuid

            for idx in range(1, self.args.samples + 1):
                rssi = await self._read_rssi(client)
                if rssi is None:
                    note = "RSSI not exposed by backend"
                    self.metadata["notes"].append(note)
                self.records.append({"index": idx, "timestamp": utc_now(), "rssi_dbm": rssi})
                await asyncio.sleep(self.args.interval_s)

        if self.metadata["notes"]:
            self.metadata["notes"] = sorted(set(self.metadata["notes"]))
        self.metadata["records_file"] = {"csv": str(self.csv_path), "json": str(self.json_path)}
        self._write_outputs()
        return {
            "samples_collected": len(self.records),
            "rssi_available": any(r["rssi_dbm"] is not None for r in self.records),
        }

    async def _read_rssi(self, client: BleakClient) -> Optional[int]:
        getter = getattr(client, "get_rssi", None)
        if callable(getter):
            try:
                return int(await getter())
            except Exception:
                pass

        backend = getattr(client, "_backend", None)
        if backend is not None:
            value = None
            attr = getattr(backend, "rssi", None)
            if callable(attr):
                try:
                    value = attr()
                except Exception:
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
        return await self._read_mock_rssi(client)

    async def _read_mock_rssi(self, client: BleakClient) -> Optional[int]:
        if not self.mock_rssi_uuid or self._mock_rssi_supported is False:
            return None
        try:
            data = await client.read_gatt_char(self.mock_rssi_uuid)
        except Exception:
            self._mock_rssi_supported = False
            return None
        if not data:
            self._mock_rssi_supported = False
            return None
        if isinstance(data, (bytes, bytearray)):
            raw = data[0]
        else:
            raw = data[0] if data else None
        if raw is None:
            self._mock_rssi_supported = False
            return None
        value = int.from_bytes(bytes([raw & 0xFF]), byteorder="little", signed=True)
        self._mock_rssi_supported = True
        if not self._mock_rssi_noted:
            self.metadata["notes"].append("Mock RSSI characteristic used")
            self._mock_rssi_noted = True
        return value

    def _write_outputs(self) -> None:
        fieldnames = ["index", "timestamp", "rssi_dbm"]
        with self.csv_path.open("w", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for record in self.records:
                writer.writerow(record)

        json_blob = {"metadata": self.metadata, "samples": self.records}
        with self.json_path.open("w") as json_file:
            json.dump(json_blob, json_file, indent=2)
