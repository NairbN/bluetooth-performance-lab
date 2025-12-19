#!/usr/bin/python3
# SPDX-License-Identifier: LGPL-2.1-or-later

"""Mock Smart Ring DUT implemented as a BlueZ peripheral.

This script extends the stock BlueZ advertisement example with a vendor-neutral
GATT service so we can exercise the Python central harness without the actual
ring hardware.
"""

from __future__ import annotations

import argparse
import logging
import struct
import time
from pathlib import Path
from typing import List, Optional

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service

try:
    from gi.repository import GLib  # type: ignore
except ImportError:  # pragma: no cover - Python 2 fallback
    import glib as GLib  # type: ignore[attr-defined]

mainloop: Optional[GLib.MainLoop] = None

BLUEZ_SERVICE_NAME = "org.bluez"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"


class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.freedesktop.DBus.Error.InvalidArgs"


class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.NotSupported"


class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.NotPermitted"


class InvalidValueLengthException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.InvalidValueLength"


class FailedException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.Failed"


class Advertisement(dbus.service.Object):
    PATH_BASE = "/org/bluez/mockring/advertisement"

    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids = None
        self.manufacturer_data = None
        self.solicit_uuids = None
        self.service_data = None
        self.local_name = None
        self.include_tx_power = False
        self.data = None
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = dict()
        properties["Type"] = self.ad_type
        if self.service_uuids is not None:
            properties["ServiceUUIDs"] = dbus.Array(self.service_uuids, signature="s")
        if self.solicit_uuids is not None:
            properties["SolicitUUIDs"] = dbus.Array(self.solicit_uuids, signature="s")
        if self.manufacturer_data is not None:
            properties["ManufacturerData"] = dbus.Dictionary(
                self.manufacturer_data, signature="qv"
            )
        if self.service_data is not None:
            properties["ServiceData"] = dbus.Dictionary(self.service_data, signature="sv")
        if self.local_name is not None:
            properties["LocalName"] = dbus.String(self.local_name)
        if self.include_tx_power:
            properties["Includes"] = dbus.Array(["tx-power"], signature="s")

        if self.data is not None:
            properties["Data"] = dbus.Dictionary(self.data, signature="yv")
        return {LE_ADVERTISEMENT_IFACE: properties}

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service_uuid(self, uuid):
        if not self.service_uuids:
            self.service_uuids = []
        self.service_uuids.append(uuid)

    def add_local_name(self, name):
        self.local_name = dbus.String(name)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        logging.info("Advertisement released by BlueZ")


class Application(dbus.service.Object):
    """org.bluez.GattApplication1 implementation"""

    def __init__(self, bus):
        self.path = "/org/mockring"
        self.services: List[Service] = []  # type: ignore[name-defined]
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        logging.debug("GetManagedObjects called")
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.get_characteristics():
                response[chrc.get_path()] = chrc.get_properties()
                for desc in chrc.get_descriptors():
                    response[desc.get_path()] = desc.get_properties()
        return response


class Service(dbus.service.Object):
    PATH_BASE = "/org/bluez/mockring/service"

    def __init__(self, bus, index, uuid, primary):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics: List[Characteristic] = []  # type: ignore[name-defined]
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": dbus.Array(
                    self.get_characteristic_paths(), signature="o"
                ),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_characteristic_paths(self):
        return [chrc.get_path() for chrc in self.characteristics]

    def get_characteristics(self):
        return self.characteristics

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]


class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + "/char" + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.descriptors = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "Service": self.service.get_path(),
                "UUID": self.uuid,
                "Flags": self.flags,
                "Descriptors": dbus.Array(self.get_descriptor_paths(), signature="o"),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_descriptor_paths(self):
        return []

    def get_descriptors(self):
        return self.descriptors

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        raise NotSupportedException()

    @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


class MockRingState:
    def __init__(
        self,
        payload_bytes: int,
        notify_hz: int,
        interval_ms: Optional[int],
        start_cmd: int,
        stop_cmd: int,
        reset_cmd: int,
    ):
        self.default_payload = max(4, payload_bytes)
        if interval_ms is not None:
            self.interval_ms = max(1, interval_ms)
        else:
            self.interval_ms = max(1, int(1000 / notify_hz) if notify_hz > 0 else 100)
        self.start_cmd = start_cmd
        self.stop_cmd = stop_cmd
        self.reset_cmd = reset_cmd
        self.seq = 0
        self.tx_char: Optional[MockRingTxCharacteristic] = None  # type: ignore[name-defined]
        self.timer_id: Optional[int] = None
        self.running = False
        self.packet_limit = 0
        self.sent_packets = 0
        self.active_payload = self.default_payload

    def attach_tx(self, characteristic: "MockRingTxCharacteristic"):
        self.tx_char = characteristic

    def handle_command(self, payload: bytes):
        if not payload:
            return
        cmd = payload[0]
        if cmd == self.start_cmd:
            length = payload[1] if len(payload) > 1 else self.default_payload
            pkt_count = int.from_bytes(payload[2:4], byteorder="little", signed=False)
            self.start(length, pkt_count)
        elif cmd == self.stop_cmd:
            logging.info("Stop command received")
            self.stop()
        elif cmd == self.reset_cmd:
            logging.info("Reset command received")
            self.reset()
        else:
            logging.warning("Unknown command: 0x%02X", cmd)

    def start(self, payload_bytes: int, packet_count: int):
        payload_bytes = max(4, min(244, payload_bytes))
        self.active_payload = payload_bytes
        self.packet_limit = packet_count
        self.sent_packets = 0
        self.running = True
        logging.info(
            "Start command: payload=%d, packet_count=%d", payload_bytes, packet_count
        )
        self._ensure_timer()

    def stop(self):
        self.running = False
        self.packet_limit = 0
        self._stop_timer()

    def reset(self):
        self.seq = 0
        self.sent_packets = 0
        self.running = False
        self.packet_limit = 0
        self._stop_timer()

    def on_notify_state_change(self, enabled: bool):
        if enabled:
            self._ensure_timer()
        else:
            self._stop_timer()

    def _ensure_timer(self):
        if self.timer_id is None and self.running and self.tx_char and self.tx_char.is_notifying:
            self.timer_id = GLib.timeout_add(self.interval_ms, self._notify_tick)

    def _stop_timer(self):
        if self.timer_id is not None:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

    def _notify_tick(self):
        if not (self.running and self.tx_char and self.tx_char.is_notifying):
            self._stop_timer()
            return False

        if self.packet_limit and self.sent_packets >= self.packet_limit:
            self.stop()
            return False

        payload = self._build_payload()
        self.tx_char.send(payload)
        self.seq = (self.seq + 1) & 0xFFFF
        self.sent_packets += 1

        if self.packet_limit and self.sent_packets >= self.packet_limit:
            self.stop()
            return False
        return True

    def _build_payload(self):
        timestamp = int(time.time() * 1000) & 0xFFFF
        packet = struct.pack("<HH", self.seq, timestamp)
        filler_len = max(0, self.active_payload - len(packet))
        if filler_len:
            packet += bytes([0xAA] * filler_len)
        return [dbus.Byte(b) for b in packet]


class MockRingService(Service):
    def __init__(self, bus, index, state: MockRingState, service_uuid: str, tx_uuid: str, rx_uuid: str):
        Service.__init__(self, bus, index, service_uuid, True)
        self.add_characteristic(MockRingTxCharacteristic(bus, 0, self, state, tx_uuid))
        self.add_characteristic(MockRingRxCharacteristic(bus, 1, self, state, rx_uuid))


class MockRingTxCharacteristic(Characteristic):
    def __init__(self, bus, index, service, state: MockRingState, uuid: str):
        Characteristic.__init__(self, bus, index, uuid, ["notify"], service)
        self.notifying = False
        self.state = state
        self.state.attach_tx(self)

    @property
    def is_notifying(self):
        return self.notifying

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True
        logging.info("Central enabled notifications")
        self.state.on_notify_state_change(True)

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        if not self.notifying:
            return
        self.notifying = False
        logging.info("Central disabled notifications")
        self.state.on_notify_state_change(False)

    def send(self, payload):
        if not self.notifying:
            return
        self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": payload}, [])


class MockRingRxCharacteristic(Characteristic):
    def __init__(self, bus, index, service, state: MockRingState, uuid: str):
        Characteristic.__init__(
            self,
            bus,
            index,
            uuid,
            ["write-without-response"],
            service,
        )
        self.state = state

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):  # pylint: disable=unused-argument
        data = bytes(value)
        logging.info("RX command: %s", data.hex())
        self.state.handle_command(data)


class MockRingAdvertisement(Advertisement):
    def __init__(self, bus, index, service_uuid: str, name: str):
        Advertisement.__init__(self, bus, index, "peripheral")
        self.add_service_uuid(service_uuid)
        self.add_local_name(name)
        self.include_tx_power = True


def find_adapter(bus, adapter_name: Optional[str] = None):
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()
    for path, props in objects.items():
        if LE_ADVERTISING_MANAGER_IFACE not in props:
            continue
        if adapter_name and not path.endswith(adapter_name):
            continue
        return path
    return None


def register_app_cb():
    logging.info("GATT application registered")


def register_app_error_cb(error):
    logging.error("Failed to register application: %s", error)
    if mainloop:
        mainloop.quit()


def register_ad_cb():
    logging.info("Advertisement registered")


def register_ad_error_cb(error):
    logging.error("Failed to register advertisement: %s", error)
    if mainloop:
        mainloop.quit()


def parse_args():
    parser = argparse.ArgumentParser(description="Mock Smart Ring BLE peripheral")
    parser.add_argument("--adapter", default=None, help="Adapter name (e.g., hci0)")
    parser.add_argument("--timeout", type=int, default=0, help="Auto-stop after N seconds")
    parser.add_argument("--advertise_name", default="MockRingDemo")
    parser.add_argument("--service_uuid", default="12345678-1234-5678-1234-56789abcdef0")
    parser.add_argument("--tx_uuid", default="12345678-1234-5678-1234-56789abcdef1")
    parser.add_argument("--rx_uuid", default="12345678-1234-5678-1234-56789abcdef2")
    parser.add_argument("--payload_bytes", type=int, default=120)
    parser.add_argument("--notify_hz", type=int, default=40)
    parser.add_argument("--interval_ms", type=int, default=None, help="Override notify interval")
    parser.add_argument("--start_cmd", type=lambda x: int(x, 0), default=0x01)
    parser.add_argument("--stop_cmd", type=lambda x: int(x, 0), default=0x02)
    parser.add_argument("--reset_cmd", type=lambda x: int(x, 0), default=0x03)
    parser.add_argument("--log", default=None, help="Optional log file path")
    return parser.parse_args()


def main():
    global mainloop  # pylint: disable=global-statement
    args = parse_args()

    handlers = [logging.StreamHandler()]
    log_target = "stdout"
    if args.log:
        log_path = Path(args.log).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path))
        log_target = str(log_path)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )
    logging.info("Logging to %s", log_target)

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter = find_adapter(bus, args.adapter)
    if not adapter:
        raise RuntimeError("LEAdvertisingManager1 interface not found")

    adapter_props = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter), DBUS_PROP_IFACE)
    adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))

    gatt_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter), GATT_MANAGER_IFACE)
    ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter), LE_ADVERTISING_MANAGER_IFACE)

    state = MockRingState(
        payload_bytes=args.payload_bytes,
        notify_hz=args.notify_hz,
        interval_ms=args.interval_ms,
        start_cmd=args.start_cmd,
        stop_cmd=args.stop_cmd,
        reset_cmd=args.reset_cmd,
    )

    app = Application(bus)
    service = MockRingService(bus, 0, state, args.service_uuid, args.tx_uuid, args.rx_uuid)
    app.add_service(service)

    advertisement = MockRingAdvertisement(bus, 0, args.service_uuid, args.advertise_name)

    mainloop = GLib.MainLoop()

    gatt_manager.RegisterApplication(app.get_path(), {}, reply_handler=register_app_cb, error_handler=register_app_error_cb)
    ad_manager.RegisterAdvertisement(
        advertisement.get_path(), {}, reply_handler=register_ad_cb, error_handler=register_ad_error_cb
    )

    controller = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter), DBUS_PROP_IFACE)
    adapter_props_dict = {
        "Address": controller.Get("org.bluez.Adapter1", "Address"),
        "Name": controller.Get("org.bluez.Adapter1", "Name"),
    }
    logging.info(
        "Mock ring advertising on %s (%s) with service %s. Share this MAC with the central host.",
        adapter_props_dict["Name"],
        adapter_props_dict["Address"],
        args.service_uuid,
    )

    if args.timeout > 0:
        def _stop_after_timeout():
            if mainloop:
                mainloop.quit()
            return False
        GLib.timeout_add_seconds(args.timeout, _stop_after_timeout)

    try:
        mainloop.run()
    except KeyboardInterrupt:
        logging.info("Ctrl-C received, stopping advertisement...")
    finally:
        state.stop()
        try:
            ad_manager.UnregisterAdvertisement(advertisement.get_path())
        except Exception:  # pragma: no cover - best effort cleanup
            pass
        try:
            gatt_manager.UnregisterApplication(app.get_path())
        except Exception:
            pass
        logging.info("Cleanup complete")


if __name__ == "__main__":
    main()
