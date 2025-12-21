"""Latency measurement client for the Smart Ring BLE test service."""

from __future__ import annotations

import asyncio
import csv
import json
import struct
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from bleak import BleakClient


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LatencySample:
    iteration: int
    mode: str
    start_time: str
    notification_time: str
    latency_s: float
    seq: int
    dut_ts: int


class LatencyClient:
    """Encapsulates the latency test workflow."""

    def __init__(self, args):
        self.args = args
        self.samples: List[LatencySample] = []
        self.connect_timeout_s = float(getattr(args, "connect_timeout_s", 20.0))
        self.connect_attempts = max(1, int(getattr(args, "connect_attempts", 1)))
        self.connect_retry_delay_s = max(0.0, float(getattr(args, "connect_retry_delay_s", 0.0)))
        self.command_log: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {
            "created": utc_now(),
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
        }

    async def run(self) -> Dict[str, Any]:
        output_dir = Path(self.args.out).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base_name = f"{timestamp_tag}_ble_latency"
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

            stream = NotificationStream()
            await client.start_notify(tx_char.uuid, stream.handler)

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
                    print(f"[latency] Command '{name}' failed but continuing: {exc}", flush=True)
                    return
                entry["status"] = "sent"
                self.command_log.append(entry)

            for iteration in range(1, self.args.iterations + 1):
                stream.clear()
                await send_command("reset", self.args.reset_cmd)
                await asyncio.sleep(0.1)

                start_payload = bytearray()
                start_payload.append(self.args.payload_bytes & 0xFF)
                requested_packets = self.args.packet_count if self.args.mode == "start" else 1
                start_payload += struct.pack("<H", requested_packets)

                start_wall = utc_now()
                start_mono = time.perf_counter()
                await send_command("start", self.args.start_cmd, bytes(start_payload))

                try:
                    result = await stream.wait_for_notification(self.args.timeout_s)
                except asyncio.TimeoutError:
                    self.samples.append(
                        LatencySample(
                            iteration=iteration,
                            mode=self.args.mode,
                            start_time=start_wall,
                            notification_time="timeout",
                            latency_s=self.args.timeout_s,
                            seq=-1,
                            dut_ts=-1,
                        )
                    )
                else:
                    latency = result["arrival_mono"] - start_mono
                    self.samples.append(
                        LatencySample(
                            iteration=iteration,
                            mode=self.args.mode,
                            start_time=start_wall,
                            notification_time=result["arrival_time"],
                            latency_s=latency,
                            seq=result["seq"],
                            dut_ts=result["dut_ts"],
                        )
                    )
                await send_command("stop", self.args.stop_cmd)
                await asyncio.sleep(self.args.inter_delay_s)

            try:
                await client.stop_notify(tx_char.uuid)
            except Exception as exc:  # pylint: disable=broad-except
                print(f"[latency] stop_notify failed but continuing: {exc}", flush=True)
        finally:
            await self._safe_disconnect(client)

        self.metadata["command_log"] = self.command_log
        self.metadata["summary"] = self._summarize()
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
                raise RuntimeError("Bleak client services not available yet.") from exc
        raise RuntimeError("Bleak client services not available yet.")

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
                try:
                    await request_fn(tx_phys="auto", rx_phys="auto")
                    info["fallback"] = "auto_requested"
                except Exception:
                    pass
        else:
            info["status"] = "unsupported_by_bleak"
        return info

    def _summarize(self) -> Dict[str, Any]:
        valid = [s.latency_s for s in self.samples if s.notification_time != "timeout"]
        summary = {"samples": len(self.samples), "timeouts": sum(1 for s in self.samples if s.notification_time == "timeout")}
        if valid:
            summary.update(
                {
                    "avg_latency_s": sum(valid) / len(valid),
                    "min_latency_s": min(valid),
                    "max_latency_s": max(valid),
                }
            )
        else:
            summary.update({"avg_latency_s": None, "min_latency_s": None, "max_latency_s": None})
        return summary

    def _write_outputs(self) -> None:
        fieldnames = ["iteration", "mode", "start_time", "notification_time", "latency_s", "seq", "dut_ts"]
        with self.csv_path.open("w", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for sample in self.samples:
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
            "metadata": self.metadata,
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
                for sample in self.samples
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
                self.metadata["connection_retry"] = {
                    "timeout_s": self.connect_timeout_s,
                    "attempts": attempts,
                    "retry_delay_s": delay,
                    "attempts_used": attempt,
                }
                print(
                    f"[latency] Connected to {self.args.address} on attempt {attempt}/{attempts}",
                    flush=True,
                )
                return client
            except asyncio.CancelledError:
                await self._safe_disconnect(client)
                raise
            except Exception as exc:  # pylint: disable=broad-except
                await self._safe_disconnect(client)
                print(
                    f"[latency] Connection attempt {attempt}/{attempts} failed: {exc}",
                    flush=True,
                )
                if attempt < attempts:
                    await asyncio.sleep(delay)
                else:
                    raise RuntimeError(
                        f"Latency client could not reach {self.args.address} after {attempts} attempts ({exc})."
                    ) from exc
        raise RuntimeError(f"Latency client failed to connect to {self.args.address}.")

    async def _safe_disconnect(self, client: BleakClient) -> None:
        try:
            await client.disconnect()
        except Exception:
            pass


class NotificationStream:
    """Queues notifications so latency measurements can await the next event."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue | None = None
        self._queue_loop: asyncio.AbstractEventLoop | None = None
        self._backlog = deque()

    def handler(self, _: int, data: bytearray) -> None:
        now = time.perf_counter()
        record = {
            "arrival_mono": now,
            "arrival_time": utc_now(),
            "seq": int.from_bytes(data[0:2], "little") if len(data) >= 2 else -1,
            "dut_ts": int.from_bytes(data[2:4], "little") if len(data) >= 4 else -1,
        }
        # Handlers may fire before the asyncio loop that waits is running; buffer safely.
        self._backlog.append(record)
        if self._queue and self._queue_loop:
            try:
                # Schedule put on the owning loop to avoid cross-loop futures.
                if self._queue_loop.is_running():
                    self._queue_loop.call_soon_threadsafe(self._queue.put_nowait, record)
            except Exception:
                # If scheduling fails, backlog will be drained later.
                pass

    def clear(self) -> None:
        # Drain queue to discard pending notifications.
        if self._queue:
            try:
                while True:
                    self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._backlog.clear()

    def _ensure_queue(self) -> None:
        loop = asyncio.get_running_loop()
        if self._queue is None or self._queue_loop is not loop:
            # Move any items from an existing queue back to backlog so we can rebind.
            if self._queue:
                try:
                    while True:
                        self._backlog.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    pass
            self._queue = asyncio.Queue()
            self._queue_loop = loop
            # Drain buffered notifications into the new queue.
            while self._backlog:
                try:
                    self._queue.put_nowait(self._backlog.popleft())
                except Exception:
                    break

    async def wait_for_notification(self, timeout: float) -> Dict[str, Any]:
        self._ensure_queue()
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)
