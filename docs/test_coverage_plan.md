# Smart Ring BLE Test Coverage Plan

This plan scopes Bluetooth validation activities for the Smart Ring DUT. It focuses on BLE performance, coexistence behavior, and coverage across host device categories so testing can be repeated once hardware is available. All metrics and thresholds below are placeholders until real data is collected.

## 1. BLE Throughput Testing

**Objective:** Validate sustained Notify throughput from the DUT to the central while issuing Write Without Response commands in parallel when required.

- **Packet sizes:** Sweep 20, 60, 120, 180, 244 bytes to capture MTU-dependent behavior. Allow payload bytes to be configured per run.
- **Test modes:**
  - *Duration-based:* Run continuous notifications for configurable durations (e.g., 30–180 s) to observe steady state.
  - *Packet-count-based:* Command the DUT to transmit a precise packet count (e.g., 1 000–10 000) to simplify packet loss math.
- **Metrics:**
  - Effective throughput in kbps derived from bytes received over wall-clock time.
  - Notification rate (packets/s) using arrival timestamps.
  - Packet loss percentage computed from sequence number gaps.
  - Jitter using inter-arrival deltas and DUT-provided timestamps (TS fields).
- **Procedure notes:**
  - Use Notify (not Indicate) for throughput to avoid per-packet acknowledgments.
  - Send the next Start TX command only after Stop/Reset are acknowledged via state change to prevent overlapping sessions.

## 2. BLE Latency Testing

**Definition for this DUT:** Latency is the elapsed time between a host action and the corresponding notification emitted by the DUT. Two complementary measurements will be executed:

1. **Start-to-first-notification:** Measure time from issuing the Start TX command (0x01) to receiving the first notification. Captures setup latency.
2. **Write-to-notification proxy:** Issue short writes (e.g., packet size ≤20 bytes) and measure the delay until the next notification arrives. Serves as an application-layer proxy for round-trip latency without firmware changes.

Log per-sample latency, along with connection parameters (interval, PHY, MTU attempts) so future DUT firmware updates can be correlated with latency shifts.

## 3. RSSI & Range Testing

- Move the DUT and phone apart in 0.5–1 m increments from 0.5 m to the disconnect point.
- At each distance, log RSSI (or closest available metric exposed by the host), notification success rate, and note whether reconnects were required.
- Identify the **disconnect distance** and record reconnect time measurements (time from disconnect event to successful data transfer after reconnect).
- Capture environmental notes (indoor, outdoor, obstacles) per run.

## 4. Body-Shadow Testing

Run throughput and latency tests under common wear scenarios:

1. Ring worn normally, hand in open air (baseline).
2. Hand behind body while phone remains in front pocket.
3. Phone in back pocket or backpack to induce shadowing.
4. Optional: arm crossed over torso to introduce human-body absorption.

Log RSSI changes, throughput deltas, and dropouts for each orientation.

## 5. Packet Error Rate (PER) Testing

- Use the sequence numbers embedded in the TX notification payloads to detect lost packets.
- Compute PER = lost packets / sent packets (per run and cumulatively). Sent packets come from DUT packet count or max observed sequence number.
- Establish placeholder thresholds (e.g., PER placeholder: `< TBD %`) until empirical limits are known.
- Document retransmission or recovery behavior when PER exceeds the placeholder threshold.

## 6. Coexistence (Coex) Tests

Stress BLE throughput while intentionally adding 2.4 GHz interference:

- **Wi-Fi load:** Run sustained Wi-Fi traffic on the phone (e.g., 2.4 GHz video streaming or iperf Wi-Fi client) while BLE throughput test runs.
- **Bluetooth audio:** Stream A2DP audio from the phone to earbuds concurrently with Notify traffic to observe scheduler contention.
- **Crowded spectrum:** Execute tests in locations with dense 2.4 GHz usage (office, conference) and capture qualitative interference notes.

For each scenario, record BLE throughput, PER, latency, and observed Wi-Fi/audio quality impacts.

## 7. Cross-Device Matrix

Ensure coverage for multiple phone families to catch stack differences.

- **Example device list:** iPhone 15 Pro (iOS 17), iPhone SE (iOS 17), Pixel 8 (Android 14), Samsung Galaxy S23 (Android 14). Update as actual hardware becomes available.
- **Matrix template:**

| Phone | OS Version | PHY Attempted | Max Payload Tested | Throughput Notes | Issues Observed |
| --- | --- | --- | --- | --- | --- |
| `<device>` | `<OS>` | 1M/2M/Coded | `<bytes>` | `<placeholder>` | `<placeholder>` |

Populate the table per run and include links to log files for traceability.

## 8. Equipment List

Required:

- Smart Ring DUT (test service UUID `12345678-1234-5678-1234-56789ABCDEF0`)
- BLE central host (Linux laptop/desktop running Python + bleak)
- iOS phone
- Android phone

Optional / recommended:

- nRF52840 DK or TI CC2642 board for sniffer captures
- RF shield box or quiet room for baseline noise measurements
- Tripod or fixture to maintain consistent DUT/phone positioning

## 9. Pass/Fail Criteria (Placeholders)

Define acceptance thresholds once baseline data is available. Until then, use placeholders clearly labeled as TBD:

- Throughput minimum placeholder: `>= TBD kbps`
- Latency maximum placeholder: `<= TBD ms`
- PER maximum placeholder: `<= TBD %`
- Maximum reconnect time placeholder: `<= TBD s`

Document any deviations from these placeholders along with rationale when actual metrics are established.

## 10. Traceability & Reporting

- Store raw logs in `logs/ble/<date>_<testname>/`.
- Summaries and derived metrics should reference log filenames, host device, and distance/orientation metadata.
- Capture configuration used for each test (CLI args, MTU negotiation results, PHY selections) inside the CSV/JSON outputs generated by the Python harness.

## 11. Mock DUT Validation (Pre-hardware)

Before the Smart Ring hardware arrives, connect the BLE clients to `scripts/ble/mock_dut_peripheral.py` to validate toolchains, logging outputs, and analysis steps. This mock stage is strictly for software rehearsal and does **not** characterize RF performance, antenna efficiency, or coexistence behavior. Use it to:

- Verify Start/Stop/Reset command sequencing, payload negotiation, and CSV/JSON log integrity between Linux A/B.
- Confirm the throughput, latency, and RSSI scripts create traceable files that can be consumed by downstream analysis (`ble_log_summarize.py`, `ble_plot.py`).
- Rehearse experiment documentation updates (naming conventions, log cataloging) so the workflows are smooth once physical measurements begin.

Capture any limitations specific to the mock (ideal RF channel, deterministic timing) so they are not mistaken for DUT behavior.
