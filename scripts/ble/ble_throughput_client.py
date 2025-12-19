#!/usr/bin/env python3
"""BLE throughput and packet-loss logger for the Smart Ring DUT.

The script connects to the DUT, validates the placeholder test service, and
records every notification (sequence number, DUT timestamp, arrival time, and
payload length). Output is written to CSV and JSON files under logs/ble/ so the
same data can be used for later analysis.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bleak import BleakClient


VERBOSE_LOG = False


def log_step(message: str) -> None:
    if VERBOSE_LOG:
        print(f"[ble_throughput] {message}")


def _int_value(value: str) -> int:
    """Parse CLI integers that may be decimal or hex (e.g., 0x01)."""
    return int(value, 0)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


@dataclass
class NotificationRecord:
    seq: int
    dut_ts: int
    arrival_time: str
    arrival_epoch: float
    payload_len: int
    raw_len: int


@dataclass
class NotificationCollector:
    records: List[NotificationRecord] = field(default_factory=list)
    first_epoch: Optional[float] = None
    last_epoch: Optional[float] = None
    prev_seq: Optional[int] = None
    lost_packets: int = 0
    total_bytes: int = 0

    def handle(self, _: int, data: bytearray) -> None:
        now = time.time()
        self.first_epoch = self.first_epoch or now
        self.last_epoch = now
        raw_len = len(data)
        payload_len = max(0, raw_len - 4)
        seq = int.from_bytes(data[0:2], byteorder="little", signed=False) if raw_len >= 2 else -1
        dut_ts = int.from_bytes(data[2:4], byteorder="little", signed=False) if raw_len >= 4 else -1

        if seq >= 0 and self.prev_seq is not None:
            gap = (seq - self.prev_seq) & 0xFFFF
            if gap > 1:
                self.lost_packets += gap - 1
        if seq >= 0:
            self.prev_seq = seq

        self.total_bytes += raw_len
        record = NotificationRecord(
            seq=seq,
            dut_ts=dut_ts,
            arrival_time=_utc_now(),
            arrival_epoch=now,
            payload_len=payload_len,
            raw_len=raw_len,
        )
        self.records.append(record)

    @property
    def packet_count(self) -> int:
        return len(self.records)

    def summary(self) -> Dict[str, Any]:
        duration = 0.0
        if self.first_epoch and self.last_epoch and self.last_epoch > self.first_epoch:
            duration = self.last_epoch - self.first_epoch

        throughput_kbps = 0.0
        notification_rate = 0.0
        if duration > 0:
            throughput_kbps = (self.total_bytes * 8 / 1000.0) / duration
            notification_rate = self.packet_count / duration

        return {
            "packets": self.packet_count,
            "estimated_lost_packets": self.lost_packets,
            "duration_s": duration,
            "throughput_kbps": throughput_kbps,
            "notification_rate_per_s": notification_rate,
            "bytes_recorded": self.total_bytes,
        }


async def attempt_mtu_request(client: BleakClient, desired: int) -> Dict[str, Any]:
    info: Dict[str, Any] = {"requested": desired}
    request_fn = getattr(client, "request_mtu", None)
    if callable(request_fn):
        try:
            negotiated = await request_fn(desired)
            info["status"] = "success"
            info["negotiated"] = negotiated
        except Exception as exc:  # pragma: no cover - best-effort logging
            info["status"] = "failed"
            info["error"] = str(exc)
    else:
        info["status"] = "unsupported_by_bleak"
    return info


async def attempt_phy_request(client: BleakClient, phy: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {"requested": phy}
    if phy == "auto":
        info["status"] = "skipped"
        return info
    request_fn = getattr(client, "set_preferred_phy", None)
    if callable(request_fn):
        try:
            # Many backends expect keyword arguments; use both tx/rx for clarity.
            await request_fn(tx_phys=phy, rx_phys=phy)
            info["status"] = "success"
        except Exception as exc:  # pragma: no cover
            info["status"] = "failed"
            info["error"] = str(exc)
    else:
        info["status"] = "unsupported_by_bleak"
    return info


def validate_characteristics(services, service_uuid: str, tx_uuid: str, rx_uuid: str):
    """Ensure the required service and characteristics exist."""
    service = services.get_service(service_uuid)
    if service is None:
        raise RuntimeError(f"Service {service_uuid} not found on device")
    tx_char = service.get_characteristic(tx_uuid)
    rx_char = service.get_characteristic(rx_uuid)
    if tx_char is None:
        raise RuntimeError(f"TX characteristic {tx_uuid} not found in service")
    if rx_char is None:
        raise RuntimeError(f"RX characteristic {rx_uuid} not found in service")
    return tx_char, rx_char


async def run_throughput_test(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.out).expanduser()
    _ensure_output_dir(output_dir)
    timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_name = f"{timestamp_tag}_ble_throughput"
    csv_path = output_dir / f"{base_name}.csv"
    json_path = output_dir / f"{base_name}.json"

    metadata: Dict[str, Any] = {
        "created": _utc_now(),
        "address": args.address,
        "service_uuid": args.service_uuid,
        "tx_uuid": args.tx_uuid,
        "rx_uuid": args.rx_uuid,
        "payload_bytes_requested": args.payload_bytes,
        "packet_count_requested": args.packet_count,
        "duration_requested_s": args.duration_s,
        "command_ids": {
            "start": args.start_cmd,
            "stop": args.stop_cmd,
            "reset": args.reset_cmd,
        },
        "mtu_request": args.mtu,
        "phy_request": args.phy,
        "connection_interval_control": "Not supported from user space; logging only.",
    }
    command_log: List[Dict[str, Any]] = []
    collector = NotificationCollector()

    log_step(f"Connecting to {args.address} ...")
    async with BleakClient(args.address) as client:
        metadata["adapter"] = getattr(client, "adapter", "unknown")
        metadata["connected_at"] = _utc_now()
        log_step(f"Connected via adapter {metadata['adapter']}")
        try:
            services = client.services  # Bleak >= 2.0 exposes services as a property.
        except Exception:
            get_services = getattr(client, "get_services", None)
            if callable(get_services):
                services = await get_services()
            else:
                raise RuntimeError(
                    "Bleak client has not performed service discovery yet."
                )
        tx_char, rx_char = validate_characteristics(services, args.service_uuid, args.tx_uuid, args.rx_uuid)
        log_step(f"Validated service {args.service_uuid} (TX {tx_char.uuid}, RX {rx_char.uuid})")
        metadata["mtu_result"] = await attempt_mtu_request(client, args.mtu)
        log_step(f"MTU negotiation: {metadata['mtu_result'].get('status')}")
        metadata["phy_result"] = await attempt_phy_request(client, args.phy)
        log_step(f"PHY request: {metadata['phy_result'].get('status')}")

        def notification_handler(sender: int, data: bytearray):
            collector.handle(sender, data)

        log_step("Enabling notifications on TX characteristic")
        await client.start_notify(tx_char.uuid, notification_handler)
        if args.duration_s:
            run_desc = f"duration {args.duration_s}s"
        elif args.packet_count:
            run_desc = f"packet_count {args.packet_count}"
        else:
            run_desc = "continuous"
        log_step(f"Test armed (payload {args.payload_bytes} bytes, {run_desc})")

        async def send_command(name: str, cmd_id: int, payload: bytes = b"") -> None:
            packet = bytes([cmd_id]) + payload
            await client.write_gatt_char(rx_char.uuid, packet, response=False)
            log_step(f"Sent {name} command (0x{cmd_id:02X}) payload_len={len(payload)}")
            command_log.append(
                {
                    "ts": _utc_now(),
                    "name": name,
                    "command_id": cmd_id,
                    "payload_hex": payload.hex(),
                }
            )

        await send_command("reset", args.reset_cmd)
        await asyncio.sleep(0.2)

        start_payload = bytearray()
        start_payload.append(args.payload_bytes & 0xFF)
        start_payload += struct.pack("<H", args.packet_count or 0)
        await send_command("start", args.start_cmd, bytes(start_payload))
        metadata["test_start"] = _utc_now()

        stop_event = asyncio.Event()

        async def stop_after_delay(delay: float):
            await asyncio.sleep(delay)
            stop_event.set()

        duration_task: Optional[asyncio.Task] = None
        if args.duration_s:
            duration_task = asyncio.create_task(stop_after_delay(args.duration_s))

        try:
            while not stop_event.is_set():
                await asyncio.sleep(0.1)
                if args.packet_count and collector.packet_count >= args.packet_count:
                    stop_event.set()
        finally:
            await send_command("stop", args.stop_cmd)
            await asyncio.sleep(0.2)
            await client.stop_notify(tx_char.uuid)
            if duration_task:
                duration_task.cancel()
            metadata["test_end"] = _utc_now()

    metadata["command_log"] = command_log
    metadata["summary"] = collector.summary()
    metadata["records_file"] = {
        "csv": str(csv_path),
        "json": str(json_path),
    }

    fieldnames = ["seq", "dut_ts", "arrival_time", "payload_len", "raw_len", "arrival_epoch"]
    with csv_path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for rec in collector.records:
            writer.writerow(
                {
                    "seq": rec.seq,
                    "dut_ts": rec.dut_ts,
                    "arrival_time": rec.arrival_time,
                    "payload_len": rec.payload_len,
                    "raw_len": rec.raw_len,
                    "arrival_epoch": f"{rec.arrival_epoch:.6f}",
                }
            )

    json_blob = {
        "metadata": metadata,
        "packets": [
            {
                "seq": rec.seq,
                "dut_ts": rec.dut_ts,
                "arrival_time": rec.arrival_time,
                "arrival_epoch": rec.arrival_epoch,
                "payload_len": rec.payload_len,
                "raw_len": rec.raw_len,
            }
            for rec in collector.records
        ],
    }
    with json_path.open("w") as json_file:
        json.dump(json_blob, json_file, indent=2)

    return metadata["summary"]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BLE throughput logger for Smart Ring DUT.")
    parser.add_argument("--address", required=True, help="BLE address of the DUT (e.g., AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789ABCDEF0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789ABCDEF1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789ABCDEF2")
    parser.add_argument("--payload_bytes", type=int, default=20, help="Payload size hint sent with the start command (20-244).")
    parser.add_argument("--packet_count", type=int, default=0, help="Optional packet count request to embed in the start command.")
    parser.add_argument("--duration_s", type=float, default=0.0, help="Optional duration in seconds to keep the test running.")
    parser.add_argument("--out", default="logs/ble", help="Output directory for CSV/JSON logs.")
    parser.add_argument("--start_cmd", type=_int_value, default=0x01, help="Start command ID (default 0x01).")
    parser.add_argument("--stop_cmd", type=_int_value, default=0x02, help="Stop command ID (default 0x02).")
    parser.add_argument("--reset_cmd", type=_int_value, default=0x03, help="Reset command ID (default 0x03).")
    parser.add_argument("--mtu", type=int, default=247, help="Requested MTU size.")
    parser.add_argument("--phy", choices=["auto", "1m", "2m", "coded"], default="auto", help="Preferred PHY request (best-effort).")
    parser.add_argument("--verbose", action="store_true", help="Print detailed progress logs.")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    global VERBOSE_LOG  # pylint: disable=global-statement
    VERBOSE_LOG = args.verbose
    if not 20 <= args.payload_bytes <= 244:
        parser.error("payload_bytes must be between 20 and 244 to align with ATT MTU constraints.")
    try:
        summary = asyncio.run(run_throughput_test(args))
    except KeyboardInterrupt:
        if VERBOSE_LOG:
            print("Interrupted by user; partial logs (if any) retained.")
        return
    if VERBOSE_LOG:
        print("Test summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
