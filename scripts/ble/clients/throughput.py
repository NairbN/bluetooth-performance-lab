"""Modular throughput client for the Smart Ring BLE test service."""

from __future__ import annotations

import asyncio
import csv
import json
import time
import struct
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bleak import BleakClient


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        seq = int.from_bytes(data[0:2], "little", signed=False) if raw_len >= 2 else -1
        dut_ts = int.from_bytes(data[2:4], "little", signed=False) if raw_len >= 4 else -1

        if seq >= 0 and self.prev_seq is not None:
            gap = (seq - self.prev_seq) & 0xFFFF
            if gap > 1:
                self.lost_packets += gap - 1
        if seq >= 0:
            self.prev_seq = seq

        self.total_bytes += raw_len
        self.records.append(
            NotificationRecord(
                seq=seq,
                dut_ts=dut_ts,
                arrival_time=utc_now(),
                arrival_epoch=now,
                payload_len=payload_len,
                raw_len=raw_len,
            )
        )

    @property
    def packet_count(self) -> int:
        return len(self.records)

    def summary(self) -> Dict[str, Any]:
        duration = 0.0
        if self.first_epoch and self.last_epoch and self.last_epoch > self.first_epoch:
            duration = self.last_epoch - self.first_epoch
        throughput_kbps = 0.0
        notification_rate = 0.0
        interarrival_ms: List[float] = []
        for idx in range(1, len(self.records)):
            delta = self.records[idx].arrival_epoch - self.records[idx - 1].arrival_epoch
            if delta >= 0:
                interarrival_ms.append(delta * 1000.0)
        if duration > 0:
            throughput_kbps = (self.total_bytes * 8 / 1000.0) / duration
            notification_rate = self.packet_count / duration
        median_ia = statistics.median(interarrival_ms) if interarrival_ms else None
        p95_ia = (
            sorted(interarrival_ms)[int(len(interarrival_ms) * 0.95) - 1]
            if interarrival_ms and len(interarrival_ms) > 1
            else None
        )
        return {
            "packets": self.packet_count,
            "estimated_lost_packets": self.lost_packets,
            "duration_s": duration,
            "throughput_kbps": throughput_kbps,
            "notification_rate_per_s": notification_rate,
            "bytes_recorded": self.total_bytes,
            "interarrival_ms_median": median_ia,
            "interarrival_ms_p95": p95_ia,
        }


class ThroughputClient:
    """Encapsulates the throughput test workflow."""

    def __init__(self, args):
        self.args = args
        self.connect_timeout_s = float(getattr(args, "connect_timeout_s", 20.0))
        self.connect_attempts = max(1, int(getattr(args, "connect_attempts", 1)))
        self.connect_retry_delay_s = max(0.0, float(getattr(args, "connect_retry_delay_s", 0.0)))
        self.collector = NotificationCollector()
        self.metadata: Dict[str, Any] = {
            "created": utc_now(),
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
            "connection_retry": {
                "timeout_s": self.connect_timeout_s,
                "attempts": self.connect_attempts,
                "retry_delay_s": self.connect_retry_delay_s,
            },
        }
        self.command_log: List[Dict[str, Any]] = []

    async def run(self) -> Dict[str, Any]:
        output_dir = Path(self.args.out).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base_name = f"{timestamp_tag}_ble_throughput"
        self.csv_path = output_dir / f"{base_name}.csv"
        self.json_path = output_dir / f"{base_name}.json"

        client = await self._connect_with_retries()
        try:
            self.metadata["adapter"] = getattr(client, "adapter", "unknown")
            self.metadata["connected_at"] = utc_now()
            services = await self._resolve_services(client)
            tx_char, rx_char = self._validate_characteristics(services)
            self.metadata["mtu_result"] = await self._attempt_mtu_request(client)
            self.metadata["phy_result"] = await self._attempt_phy_request(client)
            self._log_link_observations(client)

            def notification_handler(sender: int, data: bytearray):
                self.collector.handle(sender, data)

            await client.start_notify(tx_char.uuid, notification_handler)

            async def send_command(
                name: str,
                cmd_id: int,
                payload: bytes = b"",
                *,
                strict: bool = True,
            ) -> None:
                packet = bytes([cmd_id]) + payload
                entry = {
                    "ts": utc_now(),
                    "name": name,
                    "command_id": cmd_id,
                    "payload_hex": payload.hex(),
                }
                try:
                    await client.write_gatt_char(rx_char.uuid, packet, response=False)
                except Exception as exc:  # pylint: disable=broad-except
                    entry["status"] = "error"
                    entry["error"] = str(exc)
                    self.command_log.append(entry)
                    if strict:
                        raise
                    print(f"[throughput] Command '{name}' failed but continuing: {exc}", flush=True)
                    return
                entry["status"] = "sent"
                self.command_log.append(entry)

            await send_command("reset", self.args.reset_cmd)
            await asyncio.sleep(0.1)
            start_payload = bytearray()
            start_payload.append(self.args.payload_bytes & 0xFF)
            start_payload += struct.pack(
                "<H", self.args.packet_count if self.args.packet_count else 0
            )
            await send_command("start", self.args.start_cmd, bytes(start_payload))

            stop_event = asyncio.Event()
            duration_task = None
            if self.args.duration_s > 0:
                duration_task = asyncio.create_task(self._run_duration_guard(stop_event))

            try:
                while not stop_event.is_set():
                    await asyncio.sleep(0.1)
                    if (
                        self.args.packet_count
                        and self.collector.packet_count >= self.args.packet_count
                    ):
                        stop_event.set()
            finally:
                await send_command("stop", self.args.stop_cmd, strict=False)
                await asyncio.sleep(0.2)
                try:
                    await client.stop_notify(tx_char.uuid)
                except Exception as exc:  # pylint: disable=broad-except
                    print(f"[throughput] stop_notify failed but continuing: {exc}", flush=True)
                if duration_task:
                    duration_task.cancel()
                self.metadata["test_end"] = utc_now()
        finally:
            await self._safe_disconnect(client)

        self.metadata["command_log"] = self.command_log
        self._log_link_observations(client)
        summary = self.collector.summary()
        summary["connection_attempts_used"] = self.metadata["connection_retry"].get("attempts_used", 1)
        summary["command_errors"] = self._command_error_count()
        self.metadata["summary"] = summary
        self.metadata["records_file"] = {"csv": str(self.csv_path), "json": str(self.json_path)}
        self._write_outputs()
        return self.metadata["summary"]

    async def _resolve_services(self, client):
        services = getattr(client, "services", None)
        if services and getattr(services, "get_service", None):
            return services
        get_services = getattr(client, "get_services", None)
        if callable(get_services):
            try:
                return await get_services()
            except Exception as exc:  # pylint: disable=broad-except
                raise RuntimeError("Bleak client service discovery failed.") from exc
        raise RuntimeError("Bleak client has not performed service discovery yet.")

    def _validate_characteristics(self, services):
        service = services.get_service(self.args.service_uuid)
        if service is None:
            raise RuntimeError(f"Service {self.args.service_uuid} not found on device")
        tx_char = service.get_characteristic(self.args.tx_uuid)
        rx_char = service.get_characteristic(self.args.rx_uuid)
        if tx_char is None or rx_char is None:
            raise RuntimeError("TX/RX characteristics not found in service")
        return tx_char, rx_char

    async def _attempt_mtu_request(self, client: BleakClient) -> Dict[str, Any]:
        info: Dict[str, Any] = {"requested": self.args.mtu}
        request_fn = getattr(client, "request_mtu", None)
        if callable(request_fn):
            try:
                negotiated = await request_fn(self.args.mtu)
                info["status"] = "success"
                info["negotiated"] = negotiated
            except Exception as exc:
                info["status"] = "failed"
                info["error"] = str(exc)
        else:
            info["status"] = "unsupported_by_bleak"
        return info

    async def _attempt_phy_request(self, client: BleakClient) -> Dict[str, Any]:
        info: Dict[str, Any] = {"requested": self.args.phy}
        if self.args.phy == "auto":
            info["status"] = "skipped"
            return info
        request_fn = getattr(client, "set_preferred_phy", None)
        if callable(request_fn):
            for attempt in range(1, 4):
                try:
                    await request_fn(tx_phys=self.args.phy, rx_phys=self.args.phy)
                    info["status"] = "success"
                    info["attempts_used"] = attempt
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    info["status"] = "failed"
                    info["error"] = str(exc)
                    info["attempts_used"] = attempt
            if info.get("status") != "success" and self.args.phy != "auto":
                # Fall back to auto if explicit PHY failed.
                try:
                    await request_fn(tx_phys="auto", rx_phys="auto")
                    info["fallback"] = "auto_requested"
                except Exception:
                    pass
        else:
            info["status"] = "unsupported_by_bleak"
        return info

    async def _run_duration_guard(self, stop_event: asyncio.Event) -> None:
        await asyncio.sleep(self.args.duration_s)
        stop_event.set()

    def _log_link_observations(self, client: BleakClient) -> None:
        info: Dict[str, Any] = {}
        for attr in ["mtu_size", "_mtu_size"]:
            value = getattr(client, attr, None)
            if isinstance(value, (int, float)):
                info["mtu_size_reported"] = int(value)
                break
        for attr in ["preferred_phys", "active_phys", "phy"]:
            value = getattr(client, attr, None)
            if value:
                info["phy_reported"] = str(value)
                break
        backend = getattr(client, "_backend", None)
        if backend is not None:
            backend_mtu = getattr(backend, "_mtu_size", None) or getattr(backend, "mtu_size", None)
            if isinstance(backend_mtu, (int, float)):
                info["backend_mtu"] = int(backend_mtu)
            backend_phy = getattr(backend, "phy", None)
            if backend_phy:
                info["backend_phy"] = str(backend_phy)
        if info:
            self.metadata["link_observations"] = info

    def _write_outputs(self) -> None:
        fieldnames = ["seq", "dut_ts", "arrival_time", "payload_len", "raw_len", "arrival_epoch"]
        with self.csv_path.open("w", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for rec in self.collector.records:
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
            "metadata": self.metadata,
            "packets": [
                {
                    "seq": rec.seq,
                    "dut_ts": rec.dut_ts,
                    "arrival_time": rec.arrival_time,
                    "arrival_epoch": rec.arrival_epoch,
                    "payload_len": rec.payload_len,
                    "raw_len": rec.raw_len,
                }
                for rec in self.collector.records
            ],
        }
        with self.json_path.open("w") as json_file:
            json.dump(json_blob, json_file, indent=2)

    async def _connect_with_retries(self) -> BleakClient:
        attempts = self.connect_attempts
        delay = self.connect_retry_delay_s
        for attempt in range(1, attempts + 1):
            client = BleakClient(self.args.address, timeout=self.connect_timeout_s)
            try:
                await client.connect(timeout=self.connect_timeout_s)
                self.metadata["connection_retry"]["attempts_used"] = attempt
                print(
                    f"[throughput] Connected to {self.args.address} on attempt {attempt}/{attempts}",
                    flush=True,
                )
                return client
            except asyncio.CancelledError:
                await self._safe_disconnect(client)
                raise
            except Exception as exc:  # pylint: disable=broad-except
                await self._safe_disconnect(client)
                print(
                    f"[throughput] Connection attempt {attempt}/{attempts} failed: {exc}",
                    flush=True,
                )
                if attempt < attempts:
                    await asyncio.sleep(delay)
                else:
                    message = (
                        f"Failed to connect to {self.args.address} after "
                        f"{attempts} attempts ({exc})."
                    )
                    raise RuntimeError(message) from exc
        raise RuntimeError(f"Failed to connect to {self.args.address}; retries exhausted.")

    async def _safe_disconnect(self, client: BleakClient) -> None:
        try:
            await client.disconnect()
        except Exception:
            pass

    def _command_error_count(self) -> int:
        return sum(1 for cmd in self.command_log if cmd.get("status") == "error")
