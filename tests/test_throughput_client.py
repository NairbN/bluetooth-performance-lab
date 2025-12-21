"""Integration-style tests for the throughput client using a fake Bleak backend."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path

# Fake Bleak structures to satisfy throughput client expectations.
class FakeCharacteristic:
    def __init__(self, uuid: str):
        self.uuid = uuid


class FakeService:
    def __init__(self, uuid: str, tx_uuid: str, rx_uuid: str):
        self.uuid = uuid
        self.tx_char = FakeCharacteristic(tx_uuid)
        self.rx_char = FakeCharacteristic(rx_uuid)

    def get_characteristic(self, uuid: str):
        if uuid == self.tx_char.uuid:
            return self.tx_char
        if uuid == self.rx_char.uuid:
            return self.rx_char
        return None


class FakeServiceContainer:
    def __init__(self, service: FakeService):
        self._service = service

    def get_service(self, uuid: str):
        return self._service if uuid == self._service.uuid else None


class FakeBleakClient:
    def __init__(self, address, timeout=None):
        self.address = address
        self.timeout = timeout
        self.connected = False
        self.adapter = "hci0"
        self._service = FakeService("svc", "tx", "rx")
        self.services = FakeServiceContainer(self._service)

    async def connect(self, timeout=None):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def request_mtu(self, mtu: int):
        return mtu

    async def set_preferred_phy(self, tx_phys=None, rx_phys=None):
        return None

    async def start_notify(self, *_args, **_kwargs):
        return None

    async def stop_notify(self, *_args, **_kwargs):
        return None

    async def write_gatt_char(self, *_args, **_kwargs):
        return None


bleak_module = types.ModuleType("bleak")
bleak_module.BleakClient = FakeBleakClient
sys.modules["bleak"] = bleak_module

from scripts.ble.clients import throughput as throughput_mod  # noqa: E402

throughput_mod.BleakClient = FakeBleakClient  # type: ignore
ThroughputClient = throughput_mod.ThroughputClient  # type: ignore


class ThroughputClientTests(unittest.TestCase):
    def test_run_writes_outputs_and_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = types.SimpleNamespace(
                address="AA:BB:CC:DD:EE:FF",
                service_uuid="svc",
                tx_uuid="tx",
                rx_uuid="rx",
                payload_bytes=20,
                packet_count=0,
                duration_s=0.01,  # rely on duration guard to stop quickly
                out=tmpdir,
                start_cmd=1,
                stop_cmd=2,
                reset_cmd=3,
                mtu=247,
                phy="auto",
                connect_timeout_s=1.0,
                connect_attempts=1,
                connect_retry_delay_s=0.0,
            )
            client = ThroughputClient(args)
            summary = asyncio.run(client.run())
            self.assertIn("throughput_kbps", summary)
            self.assertTrue(Path(client.csv_path).exists())
            self.assertTrue(Path(client.json_path).exists())
            self.assertEqual(client.metadata["connection_retry"]["attempts_used"], 1)


if __name__ == "__main__":
    unittest.main()
