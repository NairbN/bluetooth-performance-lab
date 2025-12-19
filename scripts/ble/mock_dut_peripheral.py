#!/usr/bin/env python3
"""Mock Smart Ring BLE peripheral implemented on top of BlueZ D-Bus.

This utility advertises the placeholder Smart Ring test service so the
central-side scripts can be demonstrated before real hardware exists.
It relies on BlueZ's experimental GATT server support, which requires:
  * BlueZ 5.50 or newer
  * `bluetoothd --experimental`
  * Python 3.10+ with `dbus-next`

The peripheral exposes:
  Service UUID: 12345678-1234-5678-1234-56789ABCDEF0
  TX characteristic (Notify): ...DEF1
  RX characteristic (Write Without Response): ...DEF2

Command protocol (written to RX characteristic):
  Byte0: Command (0x01 start, 0x02 stop, 0x03 reset)
  Byte1: Optional payload size (overrides default if present)
  Byte2-3: Optional packet count (little-endian). 0 => run until stop.

Notifications transmit [SEQ_L][SEQ_H][TS_L][TS_H][DATA...], where DATA is
filled with 0xAA bytes to the requested payload length. Sequence numbers wrap
modulo 65536 and timestamps are derived from a monotonic millisecond tick.

The mock does *not* model RF channel effects; it only validates the central
tooling. Real DUTs should pace notifications based on TX-complete events. This
script approximates pacing with a configurable interval/Hz.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from dbus_next import Variant
from dbus_next.constants import BusType
from dbus_next.aio import MessageBus
from dbus_next.service import PropertyAccess, ServiceInterface, dbus_property, method

BLUEZ_SERVICE_NAME = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_AD_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MockLogger:
    """Optional file logger for peripheral events."""

    def __init__(self, path: Optional[Path]):
        self.path = path
        self._handle = None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a", encoding="utf-8")

    def write(self, message: str) -> None:
        if self._handle:
            self._handle.write(f"{utc_now()} {message}\n")
            self._handle.flush()
        logging.info(message)

    def close(self) -> None:
        if self._handle:
            self._handle.close()


class Service(ServiceInterface):
    def __init__(self, index: int, uuid: str, primary: bool = True):
        super().__init__(GATT_SERVICE_IFACE)
        self.path = f"/org/bluez/mockring/service{index}"
        self.uuid = uuid
        self.primary = primary
        self.characteristics: List["Characteristic"] = []

    def add_characteristic(self, characteristic: "Characteristic"):
        self.characteristics.append(characteristic)

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":  # type: ignore[override]
        return self.uuid

    @dbus_property(access=PropertyAccess.READ)
    def Primary(self) -> "b":  # type: ignore[override]
        return self.primary

    @dbus_property(access=PropertyAccess.READ)
    def Characteristics(self) -> "ao":  # type: ignore[override]
        return [char.path for char in self.characteristics]


class Characteristic(ServiceInterface):
    def __init__(self, service: Service, index: int, uuid: str, flags: List[str]):
        super().__init__(GATT_CHRC_IFACE)
        self.service = service
        self.uuid = uuid
        self.flags = flags
        self.path = f"{service.path}/char{index}"
        service.add_characteristic(self)

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":  # type: ignore[override]
        return self.uuid

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":  # type: ignore[override]
        return self.service.path

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":  # type: ignore[override]
        return self.flags


class TXCharacteristic(Characteristic):
    def __init__(self, service: Service, index: int, uuid: str):
        super().__init__(service, index, uuid, ["notify"])
        self.notifying = False

    @method()
    async def StartNotify(self):
        self.notifying = True

    @method()
    async def StopNotify(self):
        self.notifying = False

    async def send(self, payload: bytes):
        if not self.notifying:
            return
        value = [int(b) for b in payload]
        self.emit_properties_changed(GATT_CHRC_IFACE, {"Value": Variant("ay", value)}, [])


class RXCharacteristic(Characteristic):
    def __init__(self, service: Service, index: int, uuid: str, handler):
        super().__init__(service, index, uuid, ["write-without-response"])
        self._handler = handler

    @method()
    async def WriteValue(self, value: "ay", options: "a{sv}"):  # pylint: disable=unused-argument
        data = bytes(value)
        await self._handler(data)


class Advertisement(ServiceInterface):
    def __init__(self, index: int, service_uuid: str, name: str):
        super().__init__(LE_ADVERTISEMENT_IFACE)
        self.path = f"/org/bluez/mockring/advertisement{index}"
        self.service_uuid = service_uuid
        self.name = name

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":  # type: ignore[override]
        return "peripheral"

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> "as":  # type: ignore[override]
        return [self.service_uuid]

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> "s":  # type: ignore[override]
        return self.name

    @method()
    def Release(self):
        logging.info("Advertisement released by BlueZ")


class Application(ServiceInterface):
    """Implements org.freedesktop.DBus.ObjectManager for the mock app."""

    def __init__(self, services: List[Service]):
        super().__init__(DBUS_OM_IFACE)
        self.path = "/org/bluez/mockring"
        self.services = services

    @method()
    def GetManagedObjects(self) -> "a{oa{sa{sv}}}":
        managed: Dict[str, Dict[str, Dict[str, Variant]]] = {}
        for service in self.services:
            managed[service.path] = {
                GATT_SERVICE_IFACE: {
                    "UUID": Variant("s", service.uuid),
                    "Primary": Variant("b", service.primary),
                    "Includes": Variant("ao", []),
                }
            }
            for characteristic in service.characteristics:
                managed[characteristic.path] = {
                    GATT_CHRC_IFACE: {
                        "UUID": Variant("s", characteristic.uuid),
                        "Service": Variant("o", service.path),
                        "Flags": Variant("as", characteristic.flags),
                    }
                }
        return managed


class MockRingPeripheral:
    def __init__(
        self,
        args: argparse.Namespace,
        logger: MockLogger,
    ):
        self.args = args
        self.logger = logger
        self.bus: Optional[MessageBus] = None
        self.tx_char: Optional[TXCharacteristic] = None
        self.runner_task: Optional[asyncio.Task] = None
        self.sequence = 0
        self.running = False
        self.current_payload = args.payload_bytes
        self.target_packets = 0
        self.sent_packets = 0

    @property
    def notify_interval(self) -> float:
        if self.args.interval_ms:
            return max(self.args.interval_ms / 1000.0, 0.001)
        return 1.0 / max(self.args.notify_hz, 1.0)

    async def start(self):
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        adapter_path = f"/org/bluez/{self.args.adapter}"
        service = Service(0, self.args.service_uuid)
        self.tx_char = TXCharacteristic(service, 0, self.args.tx_uuid)
        RXCharacteristic(service, 1, self.args.rx_uuid, self.handle_command)
        application = Application([service])
        advertisement = Advertisement(0, self.args.service_uuid, self.args.advertise_name)

        self.bus.export(application.path, application)
        self.bus.export(service.path, service)
        for char in service.characteristics:
            self.bus.export(char.path, char)
        self.bus.export(advertisement.path, advertisement)

        gatt_manager = await self._get_interface(adapter_path, GATT_MANAGER_IFACE)
        ad_manager = await self._get_interface(adapter_path, LE_AD_MANAGER_IFACE)

        await gatt_manager.call_register_application(application.path, {})
        await ad_manager.call_register_advertisement(advertisement.path, {})
        self.logger.write("Mock DUT registered GATT service and started advertising.")

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        for signame in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signame, stop_event.set)

        await stop_event.wait()
        self.logger.write("Shutting down mock peripheral...")
        await ad_manager.call_unregister_advertisement(advertisement.path)
        await gatt_manager.call_unregister_application(application.path)
        self.logger.write("Cleanup complete.")
        self.logger.close()

    async def _get_interface(self, path: str, interface: str):
        assert self.bus
        introspection = await self.bus.introspect(BLUEZ_SERVICE_NAME, path)
        proxy = self.bus.get_proxy_object(BLUEZ_SERVICE_NAME, path, introspection)
        return proxy.get_interface(interface)

    async def handle_command(self, data: bytes):
        if not data:
            return
        cmd = data[0]
        payload_size = self.current_payload
        packet_count = self.target_packets
        if len(data) >= 2 and data[1] > 0:
            payload_size = max(4, min(244, data[1]))
        if len(data) >= 4:
            packet_count = int.from_bytes(data[2:4], byteorder="little")
        if cmd == self.args.start_cmd:
            await self.start_stream(payload_size, packet_count)
        elif cmd == self.args.stop_cmd:
            await self.stop_stream()
        elif cmd == self.args.reset_cmd:
            await self.reset_stream()

    async def start_stream(self, payload_size: int, packet_count: int):
        self.current_payload = payload_size
        self.target_packets = packet_count
        self.sent_packets = 0
        self.sequence = 0
        self.running = True
        self.logger.write(
            f"Start command received: payload={payload_size} bytes, packet_count={packet_count}"
        )
        if self.runner_task and not self.runner_task.done():
            self.runner_task.cancel()
        self.runner_task = asyncio.create_task(self._notify_loop())

    async def stop_stream(self):
        self.running = False
        if self.runner_task:
            self.runner_task.cancel()
        self.logger.write("Stop command received.")

    async def reset_stream(self):
        await self.stop_stream()
        self.sequence = 0
        self.logger.write("Reset command received.")

    async def _notify_loop(self):
        assert self.tx_char is not None
        try:
            while self.running:
                if not self.tx_char.notifying:
                    await asyncio.sleep(0.05)
                    continue
                if self.target_packets and self.sent_packets >= self.target_packets:
                    await self.stop_stream()
                    break
                seq = self.sequence & 0xFFFF
                ts = int(time.monotonic() * 1000) & 0xFFFF
                payload_len = max(4, self.current_payload)
                filler_len = max(0, payload_len - 4)
                packet = struct.pack("<HH", seq, ts) + bytes([0xAA] * filler_len)
                await self.tx_char.send(packet)
                self.sequence = (self.sequence + 1) & 0xFFFF
                self.sent_packets += 1
                await asyncio.sleep(self.notify_interval)
        except asyncio.CancelledError:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mock Smart Ring BLE peripheral (BlueZ).")
    parser.add_argument("--adapter", default="hci0", help="BlueZ adapter (default: hci0)")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789ABCDEF0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789ABCDEF1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789ABCDEF2")
    parser.add_argument("--payload_bytes", type=int, default=120, help="Default payload length.")
    parser.add_argument("--notify_hz", type=float, default=50.0, help="Notification rate (Hz).")
    parser.add_argument("--interval_ms", type=float, default=0.0, help="Notification interval override (ms).")
    parser.add_argument("--advertise_name", default="MockRingDUT", help="BLE advertisement local name.")
    parser.add_argument("--out", default="", help="Optional log file path.")
    parser.add_argument("--start_cmd", type=lambda x: int(x, 0), default=0x01)
    parser.add_argument("--stop_cmd", type=lambda x: int(x, 0), default=0x02)
    parser.add_argument("--reset_cmd", type=lambda x: int(x, 0), default=0x03)
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    if args.payload_bytes < 4 or args.payload_bytes > 244:
        raise SystemExit("payload_bytes must be between 4 and 244.")
    logger = MockLogger(Path(args.out).expanduser() if args.out else None)
    peripheral = MockRingPeripheral(args, logger)
    try:
        asyncio.run(peripheral.start())
    except KeyboardInterrupt:
        logger.write("Interrupted by user; exiting.")


if __name__ == "__main__":
    main()
