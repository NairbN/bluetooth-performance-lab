#!/usr/bin/env python3
"""BLE latency characterization helper for the Smart Ring DUT.

Two latency definitions are supported:
1. start — time from sending the Start TX command to the first notification.
2. trigger — time from sending a short Start command (packet_count=1) to the
   notification it triggers. This approximates write-to-notification latency.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bleak import BleakClient


def _int_value(value: str) -> int:
    return int(value, 0)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


@dataclass
class LatencySample:
    iteration: int
    mode: str
    start_time: str
    notification_time: str
    latency_s: float
    seq: int
    dut_ts: int


class NotificationStream:
    """Queues notifications so latency measurements can await the next event."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()

    def handler(self, _: int, data: bytearray) -> None:
        now = time.perf_counter()
        record = {
            "arrival_mono": now,
            "arrival_time": _utc_now(),
            "seq": int.from_bytes(data[0:2], "little") if len(data) >= 2 else -1,
            "dut_ts": int.from_bytes(data[2:4], "little") if len(data) >= 4 else -1,
        }
        self._queue.put_nowait(record)

    def clear(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover - defensive
                break

    async def wait_for_notification(self, timeout: float) -> Dict[str, Any]:
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)


async def attempt_mtu_request(client: BleakClient, desired: int) -> Dict[str, Any]:
    info: Dict[str, Any] = {"requested": desired}
    request_fn = getattr(client, "request_mtu", None)
    if callable(request_fn):
        try:
            negotiated = await request_fn(desired)
            info["status"] = "success"
            info["negotiated"] = negotiated
        except Exception as exc:  # pragma: no cover
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
            await request_fn(tx_phys=phy, rx_phys=phy)
            info["status"] = "success"
        except Exception as exc:  # pragma: no cover
            info["status"] = "failed"
            info["error"] = str(exc)
    else:
        info["status"] = "unsupported_by_bleak"
    return info


def validate_characteristics(services, service_uuid: str, tx_uuid: str, rx_uuid: str):
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


async def run_latency_test(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.out).expanduser()
    _ensure_output_dir(output_dir)
    timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_name = f"{timestamp_tag}_ble_latency"
    csv_path = output_dir / f"{base_name}.csv"
    json_path = output_dir / f"{base_name}.json"

    metadata: Dict[str, Any] = {
        "created": _utc_now(),
        "address": args.address,
        "service_uuid": args.service_uuid,
        "tx_uuid": args.tx_uuid,
        "rx_uuid": args.rx_uuid,
        "mode": args.mode,
        "iterations": args.iterations,
        "timeout_s": args.timeout_s,
        "inter_iteration_delay_s": args.inter_delay_s,
        "payload_bytes": args.payload_bytes,
        "latency_definition": (
            "Start command to first notification"
            if args.mode == "start"
            else "Start command with packet_count=1 to next notification (write-to-notify proxy)"
        ),
        "mtu_request": args.mtu,
        "phy_request": args.phy,
        "connection_interval_control": "Not supported from user space; logging only.",
    }
    command_log: List[Dict[str, Any]] = []
    samples: List[LatencySample] = []
    stream = NotificationStream()

    async with BleakClient(args.address) as client:
        metadata["adapter"] = getattr(client, "adapter", "unknown")
        metadata["connected_at"] = _utc_now()
        try:
            services = client.services
        except Exception:
            get_services = getattr(client, "get_services", None)
            if callable(get_services):
                services = await get_services()
            else:
                raise RuntimeError("Bleak client services not available yet.")
        tx_char, rx_char = validate_characteristics(services, args.service_uuid, args.tx_uuid, args.rx_uuid)
        metadata["mtu_result"] = await attempt_mtu_request(client, args.mtu)
        metadata["phy_result"] = await attempt_phy_request(client, args.phy)

        def handler(sender: int, data: bytearray):
            stream.handler(sender, data)

        await client.start_notify(tx_char.uuid, handler)

        async def send_command(name: str, cmd_id: int, payload: bytes = b"") -> None:
            packet = bytes([cmd_id]) + payload
            await client.write_gatt_char(rx_char.uuid, packet, response=False)
            command_log.append(
                {
                    "ts": _utc_now(),
                    "name": name,
                    "command_id": cmd_id,
                    "payload_hex": payload.hex(),
                }
            )

        for iteration in range(1, args.iterations + 1):
            stream.clear()
            await send_command("reset", args.reset_cmd)
            await asyncio.sleep(0.1)

            start_payload = bytearray()
            start_payload.append(args.payload_bytes & 0xFF)
            requested_packets = args.packet_count if args.mode == "start" else 1
            start_payload += struct.pack("<H", requested_packets)

            start_wall = _utc_now()
            start_mono = time.perf_counter()
            await send_command("start", args.start_cmd, bytes(start_payload))

            try:
                result = await stream.wait_for_notification(args.timeout_s)
            except asyncio.TimeoutError:
                samples.append(
                    LatencySample(
                        iteration=iteration,
                        mode=args.mode,
                        start_time=start_wall,
                        notification_time="timeout",
                        latency_s=args.timeout_s,
                        seq=-1,
                        dut_ts=-1,
                    )
                )
            else:
                latency = result["arrival_mono"] - start_mono
                samples.append(
                    LatencySample(
                        iteration=iteration,
                        mode=args.mode,
                        start_time=start_wall,
                        notification_time=result["arrival_time"],
                        latency_s=latency,
                        seq=result["seq"],
                        dut_ts=result["dut_ts"],
                    )
                )

            await send_command("stop", args.stop_cmd)
            await asyncio.sleep(args.inter_delay_s)

        await client.stop_notify(tx_char.uuid)

    metadata["command_log"] = command_log
    metadata["summary"] = _summarize(samples)
    metadata["records_file"] = {"csv": str(csv_path), "json": str(json_path)}

    fieldnames = ["iteration", "mode", "start_time", "notification_time", "latency_s", "seq", "dut_ts"]
    with csv_path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for sample in samples:
            writer.writerow(
                {
                    "iteration": sample.iteration,
                    "mode": sample.mode,
                    "start_time": sample.start_time,
                    "notification_time": sample.notification_time,
                    "latency_s": f"{sample.latency_s:.6f}",
                    "seq": sample.seq,
                    "dut_ts": sample.dut_ts,
                }
            )

    json_blob = {
        "metadata": metadata,
        "samples": [
            {
                "iteration": sample.iteration,
                "mode": sample.mode,
                "start_time": sample.start_time,
                "notification_time": sample.notification_time,
                "latency_s": sample.latency_s,
                "seq": sample.seq,
                "dut_ts": sample.dut_ts,
            }
            for sample in samples
        ],
    }
    with json_path.open("w") as json_file:
        json.dump(json_blob, json_file, indent=2)

    return metadata["summary"]


def _summarize(samples: List[LatencySample]) -> Dict[str, Any]:
    valid = [s.latency_s for s in samples if s.notification_time != "timeout"]
    summary = {"samples": len(samples), "timeouts": sum(1 for s in samples if s.notification_time == "timeout")}
    if valid:
        summary.update({"avg_latency_s": sum(valid) / len(valid), "min_latency_s": min(valid), "max_latency_s": max(valid)})
    else:
        summary.update({"avg_latency_s": None, "min_latency_s": None, "max_latency_s": None})
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BLE latency measurement harness for Smart Ring DUT.")
    parser.add_argument("--address", required=True, help="BLE address of the DUT (e.g., AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789ABCDEF0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789ABCDEF1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789ABCDEF2")
    parser.add_argument("--payload_bytes", type=int, default=20, help="Payload size hint for latency commands.")
    parser.add_argument("--packet_count", type=int, default=1, help="Packet count for start-mode latency (ignored in trigger mode).")
    parser.add_argument("--mode", choices=["start", "trigger"], default="start", help="Latency definition to use.")
    parser.add_argument("--iterations", type=int, default=5, help="Number of latency samples to collect.")
    parser.add_argument("--timeout_s", type=float, default=5.0, help="Timeout per iteration before marking a failure.")
    parser.add_argument("--inter_delay_s", type=float, default=1.0, help="Delay between iterations.")
    parser.add_argument("--out", default="logs/ble", help="Output directory for CSV/JSON logs.")
    parser.add_argument("--start_cmd", type=_int_value, default=0x01, help="Start command opcode.")
    parser.add_argument("--stop_cmd", type=_int_value, default=0x02, help="Stop command opcode.")
    parser.add_argument("--reset_cmd", type=_int_value, default=0x03, help="Reset command opcode.")
    parser.add_argument("--mtu", type=int, default=247, help="Requested MTU size.")
    parser.add_argument("--phy", choices=["auto", "1m", "2m", "coded"], default="auto", help="Preferred PHY request (best-effort).")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    if not 20 <= args.payload_bytes <= 244:
        parser.error("payload_bytes must be between 20 and 244.")
    try:
        summary = asyncio.run(run_latency_test(args))
    except KeyboardInterrupt:
        print("Interrupted by user; partial logs retained.")
        return
    print("Latency summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
