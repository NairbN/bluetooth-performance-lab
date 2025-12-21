"""Unit tests for BLE matrix orchestration helpers."""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

# Provide lightweight matplotlib stubs so matrix_runner can be imported without optional deps.
import types as _types

matplotlib_stub = _types.ModuleType("matplotlib")
matplotlib_stub.use = lambda *_args, **_kwargs: None
pyplot_stub = _types.ModuleType("matplotlib.pyplot")

def _noop(*_args, **_kwargs):
    return None

for name in [
    "figure",
    "plot",
    "scatter",
    "title",
    "xlabel",
    "ylabel",
    "grid",
    "legend",
    "xticks",
    "bar",
    "savefig",
    "close",
    "tight_layout",
]:
    setattr(pyplot_stub, name, _noop)

patches_stub = _types.ModuleType("matplotlib.patches")

class _DummyPatch:
    def __init__(self, *args, **kwargs):
        pass

patches_stub.Patch = _DummyPatch

sys.modules["matplotlib"] = matplotlib_stub
sys.modules["matplotlib.pyplot"] = pyplot_stub
sys.modules["matplotlib.patches"] = patches_stub
matplotlib_stub.pyplot = pyplot_stub
matplotlib_stub.patches = patches_stub

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.ble.clients.matrix_runner import (  # noqa: E402
    FullMatrixRunner,
    summarize_throughput,
    _acquire_lock,
    _release_lock,
)


class DummyThroughputRunner:
    def __init__(self):
        self.calls = []

    def run(self, payload, trial, *, scenario, phy):
        self.calls.append((scenario, phy, payload, trial))
        return {
            "scenario": scenario,
            "phy": phy,
            "payload_bytes": payload,
            "trial": trial,
            "packets": 10,
            "estimated_lost_packets": 1,
            "duration_s": 1.0,
            "throughput_kbps": 123.0,
            "connection_attempts_used": 1,
            "command_errors": 0,
            "log_json": "log.json",
        }


class DummyLatencyRunner:
    def __init__(self):
        self.calls = []

    def run(self, *, scenario, phy, trial):
        self.calls.append((scenario, phy, trial))
        return {
            "scenario": scenario,
            "phy": phy,
            "trial": trial,
            "mode": "start",
            "avg_latency_s": 0.5,
            "min_latency_s": 0.3,
            "max_latency_s": 0.7,
            "samples": 1,
            "timeouts": 0,
            "log_json": "latency.json",
        }


class DummyRssiRunner:
    def __init__(self):
        self.calls = []

    def run(self, *, scenario, phy, trial):
        self.calls.append((scenario, phy, trial))
        return {
            "scenario": scenario,
            "phy": phy,
            "trial": trial,
            "samples_collected": 1,
            "rssi_available": True,
            "log_json": "rssi.json",
        }


class DummyPlotter:
    def __init__(self):
        self.scenario_calls = []
        self.latency_calls = []
        self.rssi_calls = []

    def plot_scenario(self, rows, scenario, phy):
        self.scenario_calls.append((scenario, phy, len(rows)))

    def plot_latency(self, rows, scenario, phy):
        self.latency_calls.append((scenario, phy, len(rows)))

    def plot_rssi(self, rows, scenario, phy):
        self.rssi_calls.append((scenario, phy, len(rows)))

    def plot_comparison_throughput(self, summaries):
        pass

    def plot_comparison_latency(self, latency_rows):
        pass

    def plot_comparison_rssi(self, rssi_rows):
        pass


class MatrixRunnerTests(unittest.TestCase):
    def test_summarize_throughput(self):
        rows = [
            {"throughput_kbps": 100.0, "estimated_lost_packets": 2, "packets": 50, "connection_attempts_used": 1},
            {"throughput_kbps": 50.0, "estimated_lost_packets": 1, "packets": 40, "connection_attempts_used": 2},
        ]
        summary = summarize_throughput(rows)
        self.assertAlmostEqual(summary["avg_throughput_kbps"], 75.0)
        self.assertEqual(summary["total_loss"], 3)
        self.assertEqual(summary["total_packets"], 90)
        self.assertEqual(summary["retry_trials"], 1)
        self.assertEqual(summary["total_trials"], 2)

    def test_full_matrix_runner_collects_and_writes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            args = types.SimpleNamespace(
                address="AA:BB:CC:DD:EE:FF",
                scenarios=["baseline"],
                phys=["auto"],
                payloads=[20],
                repeats=1,
                duration_s=1.0,
                latency_iterations=1,
                latency_mode="start",
                rssi_samples=1,
                rssi_interval_s=0.1,
                out=str(tmp_path / "logs"),
                results_dir=str(tmp_path / "results"),
                plots_dir=str(tmp_path / "plots"),
                manifest_dir=str(tmp_path / "manifests"),
                lock_dir=str(tmp_path / "locks"),
                note="",
                prompt=False,
                skip_throughput=False,
                skip_latency=False,
                skip_rssi=False,
                service_uuid="12345678-1234-1234-1234-1234567890ab",
                tx_uuid="12345678-1234-1234-1234-1234567890ac",
                rx_uuid="12345678-1234-1234-1234-1234567890ad",
                start_cmd=1,
                stop_cmd=2,
                reset_cmd=3,
                throughput_script="unused",
                latency_script="unused",
                rssi_script="unused",
                mtu=247,
                connect_timeout_s=1.0,
                connect_attempts=1,
                connect_retry_delay_s=0.0,
                validate_paths=False,
            )
            runner = FullMatrixRunner(args)
            runner.throughput_runner = DummyThroughputRunner()
            runner.latency_runner = DummyLatencyRunner()
            runner.rssi_runner = DummyRssiRunner()
            runner.plotter = DummyPlotter()

            results = runner.run()
            self.assertEqual(len(results.throughput_rows), 1)
            self.assertEqual(len(results.latency_rows), 1)
            self.assertEqual(len(results.rssi_rows), 1)
            self.assertIn(("baseline", "auto"), results.scenario_summaries)

            runner.write_outputs(results)
            self.assertTrue((tmp_path / "results" / "full_matrix_throughput.csv").exists())
            self.assertTrue((tmp_path / "results" / "full_matrix_latency.csv").exists())
            self.assertTrue((tmp_path / "results" / "full_matrix_rssi.csv").exists())
            manifests = list((tmp_path / "manifests").glob("*_manifest.json"))
            self.assertTrue(manifests)

    def test_lock_prevents_overlap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            args = types.SimpleNamespace(
                address="AA:BB:CC:DD:EE:FF",
                scenarios=["baseline"],
                phys=["auto"],
                payloads=[20],
                repeats=1,
                duration_s=1.0,
                latency_iterations=1,
                latency_mode="start",
                rssi_samples=1,
                rssi_interval_s=0.1,
                out=str(tmp_path / "logs"),
                results_dir=str(tmp_path / "results"),
                plots_dir=str(tmp_path / "plots"),
                manifest_dir=str(tmp_path / "manifests"),
                lock_dir=str(tmp_path / "locks"),
                note="",
                prompt=False,
                skip_throughput=False,
                skip_latency=False,
                skip_rssi=False,
                service_uuid="12345678-1234-1234-1234-1234567890ab",
                tx_uuid="12345678-1234-1234-1234-1234567890ac",
                rx_uuid="12345678-1234-1234-1234-1234567890ad",
                start_cmd=1,
                stop_cmd=2,
                reset_cmd=3,
                throughput_script="unused",
                latency_script="unused",
                rssi_script="unused",
                mtu=247,
                connect_timeout_s=1.0,
                connect_attempts=1,
                connect_retry_delay_s=0.0,
                validate_paths=False,
                resume=False,
            )
            runner = FullMatrixRunner(args)
            runner.throughput_runner = DummyThroughputRunner()
            runner.latency_runner = DummyLatencyRunner()
            runner.rssi_runner = DummyRssiRunner()
            runner.plotter = DummyPlotter()
            runner.run()

            # Second runner should fail to acquire the lock if another process holds it.
            lock = _acquire_lock(Path(args.lock_dir), args.address)
            runner2 = FullMatrixRunner(args)
            runner2.throughput_runner = DummyThroughputRunner()
            runner2.latency_runner = DummyLatencyRunner()
            runner2.rssi_runner = DummyRssiRunner()
            runner2.plotter = DummyPlotter()
            try:
                with self.assertRaises(RuntimeError):
                    runner2.run()
            finally:
                _release_lock(lock)


if __name__ == "__main__":
    unittest.main()
