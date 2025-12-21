"""Notification pacing and command handling for the mock peripheral."""

from __future__ import annotations

import logging
import random
import struct
import time
from pathlib import Path
from typing import Optional

import dbus

from gi.repository import GLib  # type: ignore


class MockRingState:
    """Encapsulates Start/Stop/Reset commands and notification pacing."""

    def __init__(
        self,
        payload_bytes: int,
        notify_hz: int,
        interval_ms: Optional[int],
        start_cmd: int,
        stop_cmd: int,
        reset_cmd: int,
        mock_rssi_base_dbm: int,
        mock_rssi_variation: int,
        bus=None,
        adapter_path: Optional[str] = None,
        drop_percent: int = 0,
        interval_jitter_ms: int = 0,
        rssi_drift_dbm: int = 0,
        phy_profile: str = "fixed",
        drop_burst_percent: int = 0,
        drop_burst_len: int = 0,
        malformed_chance: int = 0,
        latency_spike_ms: int = 0,
        latency_spike_chance: int = 0,
        rssi_wave_amplitude: int = 0,
        rssi_wave_period: int = 0,
        disconnect_chance: int = 0,
        rssi_profile_file: Optional[str] = None,
        interval_profile_file: Optional[str] = None,
        drop_profile_file: Optional[str] = None,
        command_ignore_chance: int = 0,
        rssi_drop_threshold: int = -80,
        rssi_drop_extra_percent: int = 5,
        backlog_limit: int = 0,
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
        self.tx_char = None
        self.timer_id: Optional[int] = None
        self.running = False
        self.packet_limit = 0
        self.sent_packets = 0
        self.active_payload = self.default_payload
        self.mock_rssi_base = mock_rssi_base_dbm
        self.mock_rssi_variation = max(0, mock_rssi_variation)
        self.bus = bus
        self.adapter_path = adapter_path
        self.drop_chance = max(0.0, min(100.0, float(drop_percent))) / 100.0
        self.interval_jitter_ms = max(0, interval_jitter_ms)
        self.rssi_drift_dbm = int(rssi_drift_dbm)
        self.phy_profile = phy_profile
        self._phy_tick = 0
        self.drop_burst_chance = max(0.0, min(100.0, float(drop_burst_percent))) / 100.0
        self.drop_burst_len = max(0, drop_burst_len)
        self._current_burst = 0
        self.malformed_chance = max(0.0, min(100.0, float(malformed_chance))) / 100.0
        self.latency_spike_ms = max(0, latency_spike_ms)
        self.latency_spike_chance = max(0.0, min(100.0, float(latency_spike_chance))) / 100.0
        self.rssi_wave_amplitude = max(0, rssi_wave_amplitude)
        self.rssi_wave_period = max(1, rssi_wave_period) if rssi_wave_period else 0
        self.disconnect_chance = max(0.0, min(100.0, float(disconnect_chance))) / 100.0
        self.rssi_profile: list[int] = []
        if rssi_profile_file:
            try:
                import json

                path = Path(rssi_profile_file).expanduser()
                data = json.loads(path.read_text())
                if isinstance(data, list):
                    self.rssi_profile = [int(x) for x in data if isinstance(x, (int, float))]
            except Exception:
                logging.warning("Failed to load RSSI profile file %s", rssi_profile_file)
        self.interval_profile: list[int] = []
        if interval_profile_file:
            try:
                import json

                path = Path(interval_profile_file).expanduser()
                data = json.loads(path.read_text())
                if isinstance(data, list):
                    self.interval_profile = [max(1, int(x)) for x in data if isinstance(x, (int, float))]
            except Exception:
                logging.warning("Failed to load interval profile file %s", interval_profile_file)
        self.drop_profile: list[float] = []
        if drop_profile_file:
            try:
                import json

                path = Path(drop_profile_file).expanduser()
                data = json.loads(path.read_text())
                if isinstance(data, list):
                    self.drop_profile = [
                        max(0.0, min(1.0, float(x))) for x in data if isinstance(x, (int, float))
                    ]
            except Exception:
                logging.warning("Failed to load drop profile file %s", drop_profile_file)
        self.command_ignore_chance = max(0.0, min(100.0, float(command_ignore_chance))) / 100.0
        self.rssi_drop_threshold = rssi_drop_threshold
        self.rssi_drop_extra = max(0.0, min(100.0, float(rssi_drop_extra_percent))) / 100.0
        self.backlog_limit = max(0, backlog_limit)
        self.backlog_depth = 0

    def attach_tx(self, characteristic) -> None:
        self.tx_char = characteristic

    def handle_command(self, payload: bytes) -> None:
        if not payload:
            return
        cmd = payload[0]
        if random.random() < self.command_ignore_chance:
            logging.info("Mock: intentionally ignoring command 0x%02X", cmd)
            return
        if cmd == self.start_cmd:
            length = payload[1] if len(payload) > 1 else self.default_payload
            pkt_count = int.from_bytes(payload[2:4], "little", signed=False)
            self.start(length, pkt_count)
        elif cmd == self.stop_cmd:
            logging.info("Stop command received")
            self.stop()
        elif cmd == self.reset_cmd:
            logging.info("Reset command received")
            self.reset()
        else:
            logging.warning("Unknown command: 0x%02X", cmd)

    def start(self, payload_bytes: int, packet_count: int) -> None:
        payload_bytes = max(4, min(244, payload_bytes))
        self.active_payload = payload_bytes
        self.packet_limit = packet_count
        self.sent_packets = 0
        self.running = True
        logging.info("Start command: payload=%d packet_count=%d", payload_bytes, packet_count)
        self._ensure_timer()

    def stop(self) -> None:
        self.running = False
        self.packet_limit = 0
        self._stop_timer()

    def reset(self) -> None:
        self.seq = 0
        self.sent_packets = 0
        self.running = False
        self.packet_limit = 0
        self._stop_timer()

    def on_notify_state_change(self, enabled: bool) -> None:
        if enabled:
            self._ensure_timer()
        else:
            self._stop_timer()

    def _ensure_timer(self) -> None:
        if self.running and self.tx_char:
            if self.timer_id is None:
                self.timer_id = GLib.timeout_add(self.interval_ms, self._notify_tick)

    def _stop_timer(self) -> None:
        if self.timer_id is not None:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

    def _notify_tick(self) -> bool:
        if not (self.running and self.tx_char):
            self._stop_timer()
            return False

        if self.packet_limit and self.sent_packets >= self.packet_limit:
            self.stop()
            return False

        # Simulate channel loss if configured.
        if self._current_burst > 0:
            drop = True
            self._current_burst -= 1
        else:
            drop_prob = self.drop_chance
            if self.drop_profile:
                drop_prob = self.drop_profile.pop(0)
                self.drop_profile.append(drop_prob)
            current_rssi = self.read_mock_rssi()
            if current_rssi is not None and current_rssi < self.rssi_drop_threshold:
                drop_prob += self.rssi_drop_extra
            drop = random.random() < drop_prob
            if not drop and self.drop_burst_len and random.random() < self.drop_burst_chance:
                self._current_burst = self.drop_burst_len
                drop = True

        if random.random() < self.disconnect_chance:
            logging.info("Mock: simulating disconnect")
            self.stop()
            return False

        extra_delay = 0
        if self.latency_spike_ms and random.random() < self.latency_spike_chance:
            extra_delay = self.latency_spike_ms

        if not drop:
            payload = self._build_payload()
            if random.random() < self.malformed_chance:
                payload = payload[: max(2, len(payload) // 2)]
            self.tx_char.send(payload)
        self.seq = (self.seq + 1) & 0xFFFF
        self.sent_packets += 1

        if self.packet_limit and self.sent_packets >= self.packet_limit:
            self.stop()
            return False

        # Re-arm timer with optional jitter to mimic interval drift.
        if self.interval_profile:
            delay = self.interval_profile.pop(0)
            self.interval_profile.append(delay)
        else:
            delay = self.interval_ms + extra_delay
        if self.interval_jitter_ms > 0:
            jitter = random.randint(-self.interval_jitter_ms, self.interval_jitter_ms)
            delay = max(1, delay + jitter)
        if self.phy_profile == "varying":
            self._phy_tick = (self._phy_tick + 1) % 100
            if self._phy_tick == 0:
                # Simulate a PHY drop by slowing interval briefly.
                delay = int(delay * 1.5)
            elif self._phy_tick % 10 == 0:
                delay = max(1, int(delay * 0.8))

        self._stop_timer()
        self.timer_id = GLib.timeout_add(delay, self._notify_tick)
        return False

    def _build_payload(self) -> bytes:
        timestamp = int(time.time() * 1000) & 0xFFFF
        packet = struct.pack("<HH", self.seq, timestamp)
        filler_len = max(0, self.active_payload - len(packet))
        if filler_len:
            packet += bytes([0xAA] * filler_len)
        self.backlog_depth += len(packet)
        if self.backlog_limit and self.backlog_depth > self.backlog_limit:
            logging.info("Mock: simulated buffer full, pausing notifications for %d ms", self.interval_ms)
            time.sleep(self.interval_ms / 1000.0)
            self.backlog_depth = 0
        return packet

    def read_mock_rssi(self) -> int:
        live = self._read_adapter_connected_rssi()
        if live is None:
            value = self._next_profile_rssi()
        else:
            value = live
        if self.rssi_drift_dbm:
            self.mock_rssi_base += self.rssi_drift_dbm
        return max(-127, min(-1, value))

    def _read_adapter_connected_rssi(self) -> Optional[int]:
        """Best-effort read of connected central RSSI via BlueZ Device1 objects."""
        if not self.bus or not self.adapter_path:
            return None
        try:
            om = dbus.Interface(self.bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
            objects = om.GetManagedObjects()
        except Exception:
            return None
        candidates = []
        for path, props in objects.items():
            if not isinstance(path, str) or not path.startswith(self.adapter_path):
                continue
            dev = props.get("org.bluez.Device1")
            if not dev or not dev.get("Connected"):
                continue
            rssi = dev.get("RSSI")
            try:
                if rssi is not None:
                    candidates.append(int(rssi))
            except Exception:
                continue
        if not candidates:
            return None
        return int(sum(candidates) / len(candidates))

    def _next_profile_rssi(self) -> int:
        if self.rssi_profile:
            value = self.rssi_profile.pop(0)
            self.rssi_profile.append(value)
            return value
        jitter = random.randint(-self.mock_rssi_variation, self.mock_rssi_variation)
        base = self.mock_rssi_base + jitter
        if self.rssi_wave_amplitude and self.rssi_wave_period:
            phase = (self.seq % self.rssi_wave_period) / self.rssi_wave_period
            wave = int(self.rssi_wave_amplitude * (2 * phase - 1))
            base += wave
        return base


def apply_profile(state: "MockRingState", profile: str) -> None:
    """Apply a prebaked realism profile to the mock state."""
    presets = {
        "best": {
            "drop_chance": 0.0,
            "drop_burst_chance": 0.0,
            "drop_burst_len": 0,
            "interval_jitter_ms": 0,
            "latency_spike_ms": 0,
            "latency_spike_chance": 0,
        },
        "typical": {
            "drop_chance": 0.01,
            "drop_burst_chance": 0.01,
            "drop_burst_len": 2,
            "interval_jitter_ms": 3,
            "latency_spike_ms": 10,
            "latency_spike_chance": 0.02,
            "rssi_wave_amplitude": 3,
            "rssi_wave_period": 50,
        },
        "body_block": {
            "drop_chance": 0.03,
            "drop_burst_chance": 0.05,
            "drop_burst_len": 3,
            "interval_jitter_ms": 5,
            "latency_spike_ms": 15,
            "latency_spike_chance": 0.05,
            "rssi_wave_amplitude": 6,
            "rssi_wave_period": 40,
        },
        "pocket": {
            "drop_chance": 0.02,
            "drop_burst_chance": 0.03,
            "drop_burst_len": 2,
            "interval_jitter_ms": 4,
            "latency_spike_ms": 12,
            "latency_spike_chance": 0.03,
            "rssi_wave_amplitude": 4,
            "rssi_wave_period": 60,
        },
        "worst": {
            "drop_chance": 0.05,
            "drop_burst_chance": 0.1,
            "drop_burst_len": 4,
            "interval_jitter_ms": 8,
            "latency_spike_ms": 25,
            "latency_spike_chance": 0.08,
            "rssi_wave_amplitude": 8,
            "rssi_wave_period": 30,
            "disconnect_chance": 0.005,
        },
    }
    cfg = presets.get(profile, {})
    for key, value in cfg.items():
        setattr(state, key, value)
