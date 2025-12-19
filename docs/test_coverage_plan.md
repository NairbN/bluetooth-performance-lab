# Smart Ring BLE Test Coverage Plan (Current)

This plan reflects the **BLE-only lab** implemented in this repository. It describes what the automation (`run_full_matrix.py`) captures today and how those results roll up into the final report once real hardware arrives.

---

## 1. Goals

1. **Throughput & Packet-Loss Baseline** in representative body scenarios.
2. **Latency Envelope** for Start-triggered and trigger-mode commands.
3. **RSSI & Connection Reliability Signals** (did the connection require retries, did commands fail, were RSSI samples available).
4. **Traceability** – every data point links to raw logs (`logs/ble/*.json`) and records connection metadata (`connection_attempts_used`, `command_errors`).

---

## 2. Scenario Matrix

| Dimension | Default Values | Notes |
| --- | --- | --- |
| Scenarios | `baseline`, `hand_behind_body`, `phone_in_pocket`, `phone_in_backpack` | `--prompt` lets the operator reposition hardware between scenarios. |
| PHYs | `auto`, `2m` | Expand to `1m` / `coded` once DUT supports them reliably. |
| Payload bytes | `20, 60, 120, 180, 244` | Maps to ATT MTU headroom; feel free to trim for quick runs. |
| Repeats | `2` | Increase to `3+` when collecting statistically significant data. |
| Duration per throughput run | `30 s` | Tunable via `--duration_s`. |
| Latency iterations | `5` | Configure with `--latency_iterations`. |
| RSSI samples | `20` (`--rssi_samples`) | Interval defaults to `1 s`. |

The runner iterates scenarios × PHYs and executes throughput, latency, and RSSI unless `--skip_*` flags are set. Every trial inherits identical connection retry settings.

---

## 3. Metrics Collected

### Throughput
- Effective kbps, notification rate, duration.
- Packet counts + estimated loss via sequence gaps.
- `connection_attempts_used` and `command_errors` so we know whether the data was gathered on a “clean” link.

### Latency
- Per-iteration latency samples (start-to-first-notification and trigger proxy).
- Timeout counts.
- Connection retry metadata per run.

### RSSI
- Timestamped RSSI values (or `null` when the adapter refuses), plus notes about mock fallback usage.

### Plots
- Per scenario/payload throughput plot with color coding:
  - Green: clean runs.
  - Orange: required connection retries.
  - Red: command/teardown errors.
- Scenario comparison bars for throughput, latency, and RSSI availability.

---

## 4. Reporting Artifacts

| File | Purpose |
| --- | --- |
| `results/tables/full_matrix_throughput.csv` | Master table – scenario, PHY, payload, trial, packets, loss, duration, throughput, retry/error counts, log paths. |
| `results/tables/full_matrix_latency.csv` | Scenario-level latency summary with sample counts, timeouts, log references. |
| `results/tables/full_matrix_rssi.csv` | RSSI availability plus log pointers. |
| `results/plots/*.png` | Visual summaries for the lab report. |

Archive everything with `scripts/tools/archive_results.sh --tag "<notes>"` after each test campaign.

---

## 5. Future Extensions (Track Pending Work)

1. **PHY Expansion** – add coded PHY once adapters + DUT support it.
2. **Interference Profiles** – integrate Wi-Fi busy channels or Bluetooth audio streaming into scripted scenarios.
3. **Mobile Hosts** – port central tooling to Android/iOS so the same log formats can be collected in the field.
4. **Hardware Loopback** – replace the mock with real DUT hardware; update this document with acceptance thresholds derived from first-article measurements.

For now, this plan ensures every lab run captures the metrics needed for the Smart Ring BLE readiness review, without referencing the legacy Classic PAN/RFCOMM flows.
