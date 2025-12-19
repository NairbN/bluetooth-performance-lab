"""High-level orchestration for the mock Smart Ring peripheral."""

from __future__ import annotations

import logging
from pathlib import Path

import dbus
import dbus.mainloop.glib

from gi.repository import GLib  # type: ignore

from .gatt import Advertisement, Application, MockRingService
from .state import MockRingState

BLUEZ_SERVICE_NAME = "org.bluez"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"


def find_adapter(bus, adapter_name: str | None):
    """Locate a BlueZ adapter path that supports LE advertising."""
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, "/"), "org.freedesktop.DBus.ObjectManager")
    objects = remote_om.GetManagedObjects()
    for path, props in objects.items():
        if LE_ADVERTISING_MANAGER_IFACE not in props:
            continue
        if adapter_name and not path.endswith(adapter_name):
            continue
        return path
    return None


def setup_logging(log_path: str | None, quiet: bool) -> None:
    """Configure console/file logging."""
    handlers = []
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING if quiet else logging.INFO)
    handlers.append(console)
    if log_path:
        path = Path(log_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path))
    logging.basicConfig(level=logging.INFO, handlers=handlers, format="%(asctime)s %(levelname)s %(message)s")


def run_mock(args) -> None:
    """Entry point used by mock_dut_peripheral.py."""
    setup_logging(args.log, args.quiet)

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter = find_adapter(bus, args.adapter)
    if not adapter:
        raise RuntimeError("LEAdvertisingManager1 interface not found")

    adapter_props = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter), DBUS_PROP_IFACE)
    adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))

    gatt_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter), GATT_MANAGER_IFACE)
    ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter), LE_ADVERTISING_MANAGER_IFACE)

    supported_includes = []
    try:
        supported_includes = adapter_props.Get(LE_ADVERTISING_MANAGER_IFACE, "SupportedIncludes")
    except dbus.DBusException:
        supported_includes = []
    if supported_includes is None:
        supported_includes = []

    rssi_uuid = args.rssi_uuid or None

    state = MockRingState(
        payload_bytes=args.payload_bytes,
        notify_hz=args.notify_hz,
        interval_ms=args.interval_ms,
        start_cmd=args.start_cmd,
        stop_cmd=args.stop_cmd,
        reset_cmd=args.reset_cmd,
        mock_rssi_base_dbm=args.mock_rssi_base_dbm,
        mock_rssi_variation=args.mock_rssi_variation,
    )

    app = Application(bus)
    app.add_service(
        MockRingService(
            bus,
            0,
            state,
            args.service_uuid,
            args.tx_uuid,
            args.rx_uuid,
            rssi_uuid,
        )
    )

    advertisement = Advertisement(bus, 0, "peripheral")
    advertisement.add_service_uuid(args.service_uuid)
    advertisement.add_local_name(args.advertise_name)
    desired_includes = ["local-name", "tx-power"]
    for include in desired_includes:
        if include in supported_includes:
            advertisement.add_include(include)

    mainloop = GLib.MainLoop()

    def register_cb():
        logging.info("GATT application registered")

    def register_error_cb(error):
        logging.error("Failed to register application: %s", error)
        mainloop.quit()

    def ad_cb():
        logging.info("Advertisement registered")

    def ad_error_cb(error):
        logging.error("Failed to register advertisement: %s", error)
        mainloop.quit()

    gatt_manager.RegisterApplication(app.get_path(), {}, reply_handler=register_cb, error_handler=register_error_cb)
    ad_manager.RegisterAdvertisement(advertisement.get_path(), {}, reply_handler=ad_cb, error_handler=ad_error_cb)

    adapter_iface = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter), DBUS_PROP_IFACE)
    mac = adapter_iface.Get("org.bluez.Adapter1", "Address")
    name = adapter_iface.Get("org.bluez.Adapter1", "Name")
    print(
        f"Mock ring advertising on {name} ({mac}) with service {args.service_uuid}. "
        "Share this MAC with the central host."
    )

    if args.timeout > 0:
        def _stop_after_timeout():
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
        except Exception:
            pass
        try:
            gatt_manager.UnregisterApplication(app.get_path())
        except Exception:
            pass
        logging.info("Cleanup complete")
