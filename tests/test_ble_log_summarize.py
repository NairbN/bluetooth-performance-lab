"""Tests for BLE log summarization helper."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.analysis import ble_log_summarize


class BleLogSummarizeTests(unittest.TestCase):
    def test_summarize_with_loss_and_jitter(self):
        records = [
            {"seq": 1, "raw_len": 10, "arrival_epoch": 0.0},
            {"seq": 3, "raw_len": 10, "arrival_epoch": 0.1},  # gap -> loss
            {"seq": 4, "raw_len": 10, "arrival_epoch": 0.2},
        ]
        summary = ble_log_summarize.summarize(records)
        self.assertEqual(summary["packets_received"], 3)
        self.assertEqual(summary["estimated_packets_lost"], 1)
        self.assertGreater(summary["throughput_kbps"], 0.0)
        self.assertGreaterEqual(summary["jitter_ms"], 0.0)

    def test_load_and_collect_inputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            json_path = tmp_path / "sample_ble.json"
            csv_path = tmp_path / "sample_ble.csv"

            payload = {"metadata": {"payload_bytes_requested": 42}, "packets": [{"seq": 1, "raw_len": 8, "arrival_epoch": 0.0}]}
            json_path.write_text(json.dumps(payload))
            csv_path.write_text("seq,raw_len,arrival_epoch\n1,8,0.0\n")

            collected = ble_log_summarize.collect_inputs(tmp_path)
            self.assertIn(json_path, collected)
            self.assertIn(csv_path, collected)

            records, metadata = ble_log_summarize.load_records(json_path)
            self.assertEqual(len(records), 1)
            self.assertEqual(metadata["payload_bytes_requested"], 42)


if __name__ == "__main__":
    unittest.main()
