# Mock DUT BLE Setup

These steps describe how to bring up the mock Smart Ring peripheral and drive it with the existing BLE central scripts. This allows dry runs of the tooling without real hardware.

## 1. Roles and Machines

- **Central (recommended Linux A):** Runs the bleak-based clients (`scripts/ble/clients/ble_throughput_client.py`, etc.) to mimic the phone or lab host.
- **Peripheral (recommended Linux B):** Runs `scripts/ble/mock/cli.py` to expose the placeholder Smart Ring test service.
- You can swap roles if necessary, but isolate the processes so one adapter handles the advertisement and the other acts as central.

## 2. Requirements

On both machines:

- Python 3.10+ with `pip`.
- BlueZ 5.50 or newer with experimental features enabled (`sudo bluetoothd --experimental` or the corresponding systemd override).
- User in the `bluetooth` group (or run with `sudo` as a last resort).

Peripheral-specific dependencies:

```bash
python -m pip install dbus-next
```

(Optional) Configure systemd to start `bluetoothd` with `--experimental`. Verify with `bluetoothctl show` that the adapter is powered and advertising is allowed.

## 3. Start the Mock Peripheral

On Linux B:

```bash
sudo bluetoothctl -- experimental features must be enabled --
python scripts/ble/mock/cli.py \
  --adapter hci0 \
  --advertise_name MockRingDemo \
  --payload_bytes 160 \
  --notify_hz 40 \
  --scenario_profile typical \
  --log logs/mock_dut.log
```

- The script registers the GATT service (UUID `12345678-1234-5678-1234-56789ABCDEF0`) and begins advertising as `MockRingDemo`.
- Leave the process running; it will log Start/Stop/Reset events to `logs/mock_dut.log` if `--out` is provided.

## 4. Verify Advertisement and UUIDs

On Linux A (central side):

```bash
bluetoothctl scan on
```

Wait for the advertisement with the configured name (`MockRingDemo`). Note the MAC address it displays (e.g., `AA:BB:CC:DD:EE:FF`). You can also run:

```bash
bluetoothctl info AA:BB:CC:DD:EE:FF
```

after connecting once to confirm the service UUID appears in the GATT table.

## 5. Run the Central Scripts

Example throughput run:

```bash
python scripts/ble/clients/ble_throughput_client.py \
  --address AA:BB:CC:DD:EE:FF \
  --payload_bytes 160 \
  --duration_s 60 \
  --packet_count 0
```

For latency validation:

```bash
python scripts/ble/clients/ble_latency_client.py \
  --address AA:BB:CC:DD:EE:FF \
  --mode trigger \
  --iterations 5
```

RSSI logging (useful for range test rehearsals even though RF is idealized):

```bash
python scripts/ble/clients/ble_rssi_logger.py \
  --address AA:BB:CC:DD:EE:FF \
  --samples 20

### Mock Realism Flags

- Use `--scenario_profile best|typical|body_block|pocket|worst` to set drop/jitter/RSSI waves.
- Override specifics as needed: `--mock_drop_percent`, `--drop_burst_percent/len`, `--interval_jitter_ms`, `--latency_spike_ms/chance`, `--malformed_chance`, `--disconnect_chance`, `--rssi_wave_amplitude/period`, `--rssi_profile_file`, `--interval_profile_file`, `--drop_profile_file`, `--backlog_limit`.
- The mock will read adapter RSSI if BlueZ exposes it; otherwise it uses synthetic RSSI shaped by the chosen profile.
```

All logs are written under `logs/ble/` with timestamped names. Move them into scenario-specific folders once the run completes.

## 6. Common Errors & Fixes

- **`Operation not permitted` or `AdapterNotReady`:** Ensure the user belongs to the `bluetooth` group and that no other application is using the adapter. Restart `bluetoothd` with `--experimental`.
- **`org.bluez.Error.NotSupported` during registration:** Advertising/GATT managers are only exposed when experimental mode is enabled. Confirm with `busctl tree org.bluez`.
- **Mock peripheral not visible:** Verify the adapter is powered (`bluetoothctl power on`) and advertising (`advertising on`). Some laptops have rfkill switches—check with `rfkill list`.
- **Central cannot connect:** Make sure only one host is trying to connect. Stop `bluetoothctl connect` sessions before running the Python client.
- **Notifications not flowing:** Confirm the central enabled notifications (scripts exit if CCCD fails). On the peripheral console, look for "Start command received" logs; if absent, the RX UUID or Write Without Response command likely failed.
- **Missing D-Bus dependencies:** Install `dbus-next` and restart the script. DBus errors typically cite missing interfaces when the module is absent.

## 7. Tear-Down

- Stop the central script with Ctrl+C.
- Press Ctrl+C on the peripheral to unregister the service and advertisement cleanly.
- Collect the stored logs (`logs/ble/` and optional `logs/mock_dut.log`) for later analysis with the new summary/plot utilities.
