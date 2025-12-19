"""Notification pacing and command handling for the mock peripheral."""

from __future__ import annotations

import logging
import random
import struct
import time
from typing import Optional

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

    def attach_tx(self, characteristic) -> None:
        self.tx_char = characteristic

    def handle_command(self, payload: bytes) -> None:
        if not payload:
            return
        cmd = payload[0]
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
        if self.timer_id is None and self.running and self.tx_char:
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

        payload = self._build_payload()
        self.tx_char.send(payload)
        self.seq = (self.seq + 1) & 0xFFFF
        self.sent_packets += 1

        if self.packet_limit and self.sent_packets >= self.packet_limit:
            self.stop()
            return False
        return True

    def _build_payload(self) -> bytes:
        timestamp = int(time.time() * 1000) & 0xFFFF
        packet = struct.pack("<HH", self.seq, timestamp)
        filler_len = max(0, self.active_payload - len(packet))
        if filler_len:
            packet += bytes([0xAA] * filler_len)
        return packet

    def read_mock_rssi(self) -> int:
        jitter = random.randint(-self.mock_rssi_variation, self.mock_rssi_variation)
        value = self.mock_rssi_base + jitter
        return max(-127, min(-1, value))
