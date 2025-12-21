# BLE Lab Command Cheatsheet (Copy/Paste Friendly)

Quick commands for the Smart Ring BLE lab. Adjust adapter/device addresses as needed. Paths assume the repo lives at `~/Workspace/bluetooth-performance-lab`.

## 0) One-Time Setup (per host)
```bash
cd ~/Workspace/bluetooth-performance-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
# Central host (Linux A)
./scripts/tools/setup_linux_a.sh
# Mock host (Linux B)
./scripts/tools/setup_linux_b.sh
```

## 1) Prep Radios (both hosts, each reboot)
```bash
sudo btmgmt -i hci0 power off
sudo btmgmt -i hci0 le on
sudo btmgmt -i hci0 bredr off
sudo btmgmt -i hci0 power on
nmcli radio wifi off   # optional but recommended during measurements
```

## 2) Start Mock Peripheral (Linux B)
```bash
cd ~/Workspace/bluetooth-performance-lab
source .venv/bin/activate
./scripts/tools/start_mock.sh \
  --adapter hci0 \
  --scenario_profile typical \
  --log logs/mock_dut.log
# Copy the advertised MAC address for use below.
```

## 3) Health Check (Central / Linux A)
```bash
cd ~/Workspace/bluetooth-performance-lab
source .venv/bin/activate
python scripts/ble/clients/health_check.py --adapter hci0 --json
```

## 4) Full Matrix Run (Central / Linux A)
```bash
cd ~/Workspace/bluetooth-performance-lab
source .venv/bin/activate
./scripts/tools/run_full_matrix.sh \
  --address <MOCK_MAC> \
  --note "Pixel8+MockRing" \
  --connect_timeout_s 30 \
  --connect_attempts 5 \
  --connect_retry_delay_s 10 \
  --resume
```

## 5) Throughput-Only Sweep (Central / Linux A)
```bash
cd ~/Workspace/bluetooth-performance-lab
source .venv/bin/activate
./scripts/tools/run_throughput_matrix.sh \
  --address <MOCK_MAC> \
  --phy coded \
  --payloads 60 120 244 \
  --repeats 1
```

## 6) Single-Client Debug Runs (Central)
```bash
# Throughput sanity check
python scripts/ble/clients/ble_throughput_client.py \
  --address <MOCK_MAC> \
  --duration_s 20 \
  --connect_attempts 5 --connect_timeout_s 30

# Latency probe
python scripts/ble/clients/ble_latency_client.py \
  --address <MOCK_MAC> \
  --mode trigger --iterations 10 \
  --connect_attempts 5 --connect_timeout_s 30

# RSSI sampler
python scripts/ble/clients/ble_rssi_logger.py \
  --address <MOCK_MAC> \
  --samples 30 --interval_s 1.0 \
  --connect_attempts 5 --connect_timeout_s 30
```

## 7) Cache Clear (if discovery/pairing misbehaves, both hosts)
```bash
cd ~/Workspace/bluetooth-performance-lab
scripts/tools/clear_bt_cache.sh \
  --adapter <ADAPTER_MAC> \
  --device <PEER_MAC> \
  --yes
```

## 8) Cleanup & Archive (Central)
```bash
# Optional: archive current outputs
./scripts/tools/archive_results.sh --tag "pre-clean-$(date +%Y%m%d_%H%M)"
# Optional: wipe working dirs
./scripts/tools/cleanup_outputs.sh --yes
```

## 9) Outputs (where to look)
- Raw logs: `logs/ble/`
- Aggregated tables: `results/tables/`
- Plots: `results/plots/`
- Manifests: `results/manifests/`

## 10) Reference
- Spec/UUIDs and service details: `docs/test_sw_requirements.md`
- End-to-end guide: `docs/software_guide.md`
- Experiment walkthrough + stability checklist: `docs/how_to_run_experiments.md`
