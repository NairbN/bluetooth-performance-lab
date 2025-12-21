"""Unit tests for BLE client helpers (throughput/latency/RSSI/mock state)."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

# Stub bleak to avoid requiring the real dependency.
bleak_module = types.ModuleType("bleak")


class DummyBleakClient:
    def __init__(self, address, timeout=None):
        self.address = address
        self.timeout = timeout
        self.connected = False
        self.adapter = "hci0"
        self._backend = None

    async def connect(self, timeout=None):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def start_notify(self, *_args, **_kwargs):
        return None

    async def stop_notify(self, *_args, **_kwargs):
        return None

    async def write_gatt_char(self, *_args, **_kwargs):
        return None

    async def read_gatt_char(self, *_args, **_kwargs):
        # Default mock RSSI payload (-55dBm encoded as unsigned byte)
        return bytes([0xC9])


bleak_module.BleakClient = DummyBleakClient
sys.modules["bleak"] = bleak_module

# Stub gi.repository.GLib so mock state can be imported without GTK/GLib present.
glib_module = types.SimpleNamespace(
    timeout_add=lambda *_args, **_kwargs: 1,
    source_remove=lambda *_args, **_kwargs: None,
)
gi_repo = types.ModuleType("gi.repository")
gi_repo.GLib = glib_module
gi_module = types.ModuleType("gi")
gi_module.repository = gi_repo
sys.modules["gi"] = gi_module
sys.modules["gi.repository"] = gi_repo
sys.modules["gi.repository.GLib"] = glib_module

# Stub dbus for mock state RSSI helper.
class _DummyDBusInterface:
    def __init__(self, *_args, **_kwargs):
        pass

    def GetManagedObjects(self):
        return {}


dbus_module = types.ModuleType("dbus")
dbus_module.Interface = lambda *_args, **_kwargs: _DummyDBusInterface()
sys.modules["dbus"] = dbus_module

from scripts.ble.clients.throughput import NotificationCollector  # noqa: E402
from scripts.ble.clients.latency import LatencyClient, NotificationStream  # noqa: E402
from scripts.ble.clients.rssi import RssiClient  # noqa: E402
from scripts.ble.mock.state import MockRingState, apply_profile  # noqa: E402
from scripts.ble.clients.run_full_matrix import _discover_address as full_discover  # noqa: E402
from scripts.ble.clients.run_throughput_matrix import _discover_address as throughput_discover  # noqa: E402


class DummyArgs(types.SimpleNamespace):
    """Simple helper to provide attribute access for client constructors."""


class ClientUnitTests(unittest.TestCase):
    def test_notification_collector_summary(self):
        collector = NotificationCollector()
        collector.handle(0, b"\x01\x00\x00\x00ABCD")  # seq=1
        collector.handle(0, b"\x03\x00\x00\x00ABCD")  # seq=3 (gap -> loss)
        summary = collector.summary()
        self.assertEqual(summary["packets"], 2)
        self.assertEqual(summary["estimated_lost_packets"], 1)
        self.assertGreater(summary["throughput_kbps"], 0.0)

    def test_latency_summary_with_timeout(self):
        args = DummyArgs(
            address="addr",
            service_uuid="svc",
            tx_uuid="tx",
            rx_uuid="rx",
            mode="start",
            iterations=2,
            timeout_s=1.0,
            inter_delay_s=0.1,
            payload_bytes=20,
            packet_count=1,
            mtu=247,
            phy="auto",
            connect_timeout_s=1.0,
            connect_attempts=1,
            connect_retry_delay_s=0.0,
            out=".",
            start_cmd=1,
            stop_cmd=2,
            reset_cmd=3,
        )
        client = LatencyClient(args)
        client.samples = [
            types.SimpleNamespace(latency_s=0.2, notification_time="ok"),
            types.SimpleNamespace(latency_s=0.4, notification_time="ok"),
            types.SimpleNamespace(latency_s=1.0, notification_time="timeout"),
        ]
        summary = client._summarize()  # pylint: disable=protected-access
        self.assertEqual(summary["samples"], 3)
        self.assertEqual(summary["timeouts"], 1)
        self.assertAlmostEqual(summary["avg_latency_s"], 0.3)
        self.assertEqual(summary["min_latency_s"], 0.2)
        self.assertEqual(summary["max_latency_s"], 0.4)

    def test_notification_stream_queueing(self):
        stream = NotificationStream()
        stream.handler(0, b"\x05\x00\xAA\x00")  # seq=5, dut_ts=0x00AA
        record = asyncio.run(stream.wait_for_notification(0.1))
        self.assertEqual(record["seq"], 5)
        self.assertEqual(record["dut_ts"], 0x00AA)
        stream.clear()
        with self.assertRaises(asyncio.TimeoutError):
            asyncio.run(stream.wait_for_notification(0.05))

    def test_rssi_reads_backend_and_mock(self):
        args = DummyArgs(
            address="addr",
            samples=1,
            interval_s=0.0,
            out=".",
            connect_timeout_s=1.0,
            connect_attempts=1,
            connect_retry_delay_s=0.0,
            mock_rssi_uuid="uuid",
        )
        client = RssiClient(args)

        class Backend:
            def __init__(self):
                self.rssi = -42

        dummy = DummyBleakClient("addr", timeout=1.0)
        dummy._backend = Backend()
        rssi_value = asyncio.run(client._read_rssi(dummy))  # pylint: disable=protected-access
        self.assertEqual(rssi_value, -42)

        # Force backend read failure to exercise mock RSSI characteristic.
        dummy._backend = None
        value = asyncio.run(client._read_mock_rssi(dummy))  # pylint: disable=protected-access
        self.assertEqual(value, -55)  # default payload from DummyBleakClient.read_gatt_char
        self.assertIn("Mock RSSI characteristic used", client.metadata["notes"])

    def test_discover_address_helpers(self):
        class Dev:
            def __init__(self, address, name):
                self.address = address
                self.name = name

        def fake_bleak(devices):
            class FakeBleakScanner:
                @staticmethod
                async def discover(timeout=None, service_uuids=None):
                    return devices

            return types.SimpleNamespace(BleakScanner=FakeBleakScanner)

        devices = [Dev("AA:BB", "MockRingDemo"), Dev("CC:DD", "Other")]
        devices2 = [Dev("11:22", "")]

        with mock.patch.dict(sys.modules, {"bleak": fake_bleak(devices)}):
            addr = asyncio.run(full_discover("MockRingDemo", "svc", 1.0))
            self.assertEqual(addr, "AA:BB")
        with mock.patch.dict(sys.modules, {"bleak": fake_bleak(devices2)}):
            addr = asyncio.run(throughput_discover("", "svc", 1.0))
            self.assertEqual(addr, "11:22")

    def test_mock_ring_state_handles_commands(self):
        state = MockRingState(
            payload_bytes=10,
            notify_hz=10,
            interval_ms=None,
            start_cmd=0x01,
            stop_cmd=0x02,
            reset_cmd=0x03,
            mock_rssi_base_dbm=-55,
            mock_rssi_variation=5,
        )
        sent_payloads = []

        class Tx:
            def send(self, payload):
                sent_payloads.append(bytes(payload))

        state.attach_tx(Tx())
        state.handle_command(bytes([0x01, 8, 0x00, 0x00]))  # start with payload 8
        self.assertTrue(state.running)
        state._notify_tick()  # pylint: disable=protected-access
        self.assertTrue(sent_payloads)
        state.handle_command(bytes([0x02]))
        self.assertFalse(state.running)
        state.handle_command(bytes([0x03]))
        self.assertEqual(state.sent_packets, 0)

    def test_rssi_client_writes_outputs(self):
        args = DummyArgs(
            address="addr",
            samples=2,
            interval_s=0.0,
            out=tempfile.mkdtemp(),
            connect_timeout_s=1.0,
            connect_attempts=1,
            connect_retry_delay_s=0.0,
            mock_rssi_uuid=None,
        )

        class FakeRssiClient(RssiClient):
            async def _connect_with_retries(self):  # pylint: disable=protected-access
                return DummyBleakClient("addr", timeout=1.0)

            async def _read_rssi(self, _client):  # pylint: disable=protected-access
                return -60

        client = FakeRssiClient(args)
        summary = asyncio.run(client.run())
        self.assertTrue(summary["rssi_available"])
        self.assertEqual(summary["samples_collected"], 2)
        self.assertTrue(Path(client.csv_path).exists())
        self.assertTrue(Path(client.json_path).exists())

    def test_apply_profile_sets_expected_fields(self):
        state = MockRingState(
            payload_bytes=20,
            notify_hz=10,
            interval_ms=None,
            start_cmd=1,
            stop_cmd=2,
            reset_cmd=3,
            mock_rssi_base_dbm=-60,
            mock_rssi_variation=2,
        )
        apply_profile(state, "body_block")
        self.assertGreaterEqual(state.drop_chance, 0.0)
        self.assertGreater(state.interval_jitter_ms, 0)
        self.assertGreater(state.rssi_wave_amplitude, 0)

    def test_command_ignore_and_drop_profile(self):
        state = MockRingState(
            payload_bytes=20,
            notify_hz=10,
            interval_ms=None,
            start_cmd=1,
            stop_cmd=2,
            reset_cmd=3,
            mock_rssi_base_dbm=-90,
            mock_rssi_variation=0,
            drop_percent=0,
            drop_burst_percent=0,
            drop_burst_len=0,
            command_ignore_chance=100,
            rssi_drop_threshold=-80,
            rssi_drop_extra_percent=100,
        )
        sent_payloads = []

        class Tx:
            def send(self, payload):
                sent_payloads.append(payload)

        state.attach_tx(Tx())
        state.handle_command(bytes([1, 10, 0, 0]))  # should be ignored
        self.assertFalse(state.running)

        # Now force a drop due to RSSI threshold and drop profile.
        state.command_ignore_chance = 0
        state.start(10, 1)
        state.rssi_profile = [-90]
        state.drop_profile = [0.0]
        with mock.patch("random.random", return_value=0.0):
            state._notify_tick()  # pylint: disable=protected-access
        self.assertEqual(len(sent_payloads), 0)  # dropped

    def test_backpressure_and_interval_profile(self):
        state = MockRingState(
            payload_bytes=20,
            notify_hz=10,
            interval_ms=5,
            start_cmd=1,
            stop_cmd=2,
            reset_cmd=3,
            mock_rssi_base_dbm=-60,
            mock_rssi_variation=0,
            backlog_limit=1,
        )
        state.interval_profile = [5, 10]
        state.attach_tx(types.SimpleNamespace(send=lambda _p: None))
        with mock.patch("time.sleep") as patched_sleep:
            packet = state._build_payload()  # pylint: disable=protected-access
        self.assertIsNotNone(packet)
        patched_sleep.assert_called()  # backpressure triggered
        # Interval profile rotates
        state.start(20, 2)
        state._notify_tick()  # pylint: disable=protected-access
        self.assertEqual(state.interval_profile[0], 10)


if __name__ == "__main__":
    unittest.main()
