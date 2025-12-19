"""GATT-related helper classes for the mock Smart Ring peripheral."""

from __future__ import annotations

from typing import List

import dbus
import dbus.exceptions
import dbus.service

from .state import MockRingState

GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"


class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.freedesktop.DBus.Error.InvalidArgs"


class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.NotSupported"


class Advertisement(dbus.service.Object):
    """LE advertisement wrapper used to announce the mock service."""

    PATH_BASE = "/org/bluez/mockring/advertisement"

    def __init__(self, bus, index: int, advertising_type: str):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids: List[str] | None = None
        self.local_name: str | None = None
        dbus.service.Object.__init__(self, bus, self.path)

    def add_service_uuid(self, uuid: str) -> None:
        self.service_uuids = (self.service_uuids or []) + [uuid]

    def add_local_name(self, name: str) -> None:
        self.local_name = name

    def get_properties(self):
        props = {"Type": self.ad_type}
        if self.service_uuids is not None:
            props["ServiceUUIDs"] = dbus.Array(self.service_uuids, signature="s")
        if self.local_name is not None:
            props["LocalName"] = dbus.String(self.local_name)
        return {LE_ADVERTISEMENT_IFACE: props}

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        pass


class Application(dbus.service.Object):
    """Implements org.bluez.GattApplication1 to expose managed objects."""

    def __init__(self, bus):
        self.path = "/org/mockring"
        self.services: List[Service] = []  # type: ignore[name-defined]
        dbus.service.Object.__init__(self, bus, self.path)

    def add_service(self, service: "Service") -> None:
        self.services.append(service)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method("org.freedesktop.DBus.ObjectManager", out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.get_characteristics():
                response[chrc.get_path()] = chrc.get_properties()
        return response


class Service(dbus.service.Object):
    """Base class for org.bluez.GattService1 objects."""

    PATH_BASE = "/org/bluez/mockring/service"

    def __init__(self, bus, index: int, uuid: str, primary: bool):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics: List[Characteristic] = []  # type: ignore[name-defined]
        dbus.service.Object.__init__(self, bus, self.path)

    def add_characteristic(self, characteristic: "Characteristic") -> None:
        self.characteristics.append(characteristic)

    def get_characteristics(self):
        return self.characteristics

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": dbus.Array(
                    [chrc.get_path() for chrc in self.characteristics], signature="o"
                ),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]


class Characteristic(dbus.service.Object):
    """Base characteristic wrapper shared by TX and RX characteristics."""

    def __init__(self, bus, index: int, uuid: str, flags: List[str], service: Service):
        self.path = service.path + "/char" + str(index)
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.service = service
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "Service": self.service.get_path(),
                "UUID": self.uuid,
                "Flags": self.flags,
                "Descriptors": dbus.Array([], signature="o"),
            }
        }

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


class MockRingTxCharacteristic(Characteristic):
    """Notification characteristic streaming `[SEQ][TS][DATA]` payloads."""

    def __init__(self, bus, index: int, service: Service, state: MockRingState, uuid: str):
        super().__init__(bus, index, uuid, ["notify"], service)
        self.state = state
        self.notifying = False
        self.state.attach_tx(self)

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True
        self.state.on_notify_state_change(True)

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        if not self.notifying:
            return
        self.notifying = False
        self.state.on_notify_state_change(False)

    def send(self, payload):
        if not self.notifying:
            return
        value = [dbus.Byte(b) for b in payload]
        self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": value}, [])


class MockRingRxCharacteristic(Characteristic):
    """RX characteristic handling Start/Stop/Reset commands."""

    def __init__(self, bus, index: int, service: Service, state: MockRingState, uuid: str):
        super().__init__(bus, index, uuid, ["write-without-response"], service)
        self.state = state

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        data = bytes(value)
        self.state.handle_command(data)


class MockRingService(Service):
    """Service container bundling TX/RX characteristics."""

    def __init__(self, bus, index: int, state: MockRingState, service_uuid: str, tx_uuid: str, rx_uuid: str):
        super().__init__(bus, index, service_uuid, True)
        self.add_characteristic(MockRingTxCharacteristic(bus, 0, self, state, tx_uuid))
        self.add_characteristic(MockRingRxCharacteristic(bus, 1, self, state, rx_uuid))
