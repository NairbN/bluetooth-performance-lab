# Smart Ring BLE Test Spec (Shared)

This folder captures the BLE test service contract and output schemas so platform-native runners (Android/iOS/macOS/Windows/Linux) can stay consistent with the Python clients/mock.

## GATT Service
- **Service UUID:** `12345678-1234-5678-1234-56789ABCDEF0`
- **TX characteristic (Notify):** `12345678-1234-5678-1234-56789ABCDEF1`
- **RX characteristic (Write Without Response):** `12345678-1234-5678-1234-56789ABCDEF2`
- **Optional RSSI characteristic:** `12345678-1234-5678-1234-56789ABCDEF3` (used by the mock)

### TX Payload (Notify)
```
[SEQ_L][SEQ_H][TS_L][TS_H][DATA...]
```
- `SEQ`: 16-bit little-endian sequence number (increments per packet)
- `TS`: 16-bit little-endian DUT timestamp (units up to firmware; used for jitter/latency)
- `DATA`: payload bytes (configurable by Start command)

### RX Commands (Write Without Response)
- `0x01` Start: optional payload config follows
- `0x02` Stop
- `0x03` Reset

## Default Test Parameters
- Payload sweep: 20, 60, 120, 180, 244 bytes
- PHYs: `auto`, `coded` (expandable to `1m`, `2m`)
- MTU request: 247 (best effort; log negotiated MTU)
- Connection retry policy: `connect_timeout_s`, `connect_attempts`, `connect_retry_delay_s`

## Output Schemas (CSV/JSON)

### Throughput CSV Columns
- `payload_bytes`, `trial`, `packets`, `estimated_lost_packets`, `duration_s`, `throughput_kbps`, `notification_rate_per_s`, `connection_attempts_used`, `command_errors`, `log_json`, `log_csv`

### Latency CSV Columns
- `scenario`, `phy`, `trial`, `mode`, `avg_latency_s`, `min_latency_s`, `max_latency_s`, `samples`, `timeouts`, `log_json`, `log_csv`

### RSSI CSV Columns
- `scenario`, `phy`, `trial`, `samples_collected`, `rssi_available`, `log_json`, `log_csv`

### Manifest (JSON)
Keys produced by the Python runners:
- `run_id`: timestamp-based ID
- `type`: `full_matrix` or `throughput_matrix`
- `address`: target identifier (MAC on Linux/Windows/Android; CoreBluetooth ID on Apple)
- `scenarios`, `phys`, `payloads`, `repeats`
- `started_at`, `ended_at`
- `status`: `completed` or `completed_with_errors`
- `errors`: list of string errors
- `outputs`: paths to CSVs/plots
- `summary`: per-scenario summary (keyed `scenario|phy`)
- `args`: note/mtu/connect_timeout_s/connect_attempts/connect_retry_delay_s

## Usage in Other Repos
- Import or vendor this `shared/` folder to align UUIDs, commands, and schemas.
- Emit the same CSV/JSON shapes so results are comparable across platforms.
- Use the advertised name `MockRingDemo` and service UUID filter to discover the mock/dut; on Apple platforms use the CoreBluetooth identifier returned by scan instead of MAC.
