# Smart Ring BLE Test Software Access Requirements

This document defines what the central-side test software must support in order to access and characterize the Smart Ring DUT. It can be shared with vendors or internal teams so independently developed tooling stays interoperable.

## 1. Required GATT Interface

- **Dedicated test service UUID:** `12345678-1234-5678-1234-56789ABCDEF0`
- **TX characteristic (DUT → Central):**
  - UUID `12345678-1234-5678-1234-56789ABCDEF1`
  - Properties: Notify (no Indicate requirement)
- **RX characteristic (Central → DUT):**
  - UUID `12345678-1234-5678-1234-56789ABCDEF2`
  - Properties: Write Without Response
- Characteristics must be discoverable over 128-bit UUIDs to avoid OS-level caching conflicts. The DUT must pace notifications per TX-complete events to prevent queue overruns.

## 2. Central Capabilities

The test software (initially Linux + Python + bleak) must:

- Initiate BLE connections and cleanly disconnect on exit.
- Discover the service/characteristics and validate UUIDs before testing.
- Enable notifications by writing the Client Characteristic Configuration Descriptor (CCCD) for the TX characteristic.
- Issue Write Without Response commands on the RX characteristic for Start/Stop/Reset control and payload configuration.

## 3. Logging Requirements

- Produce timestamped logs for every event: connection start/stop, commands sent, notifications received.
- Track 16-bit sequence numbers and timestamps provided in the TX payloads to compute packet loss and jitter.
- Mark calculated packet loss events in the log for downstream parsing.
- Capture reconnect attempts with timestamps to correlate with RSSI or interference observations.
- Sample RSSI when the platform exposes it; include placeholders when unavailable.
- Export both CSV and JSON formats per run with consistent schema (e.g., `logs/ble/<timestamp>_<test>.csv` + `.json`).
- Retain raw outputs under `logs/ble/` without alteration to preserve traceability.

## 4. Configurability

Provide CLI arguments (or equivalent UI fields) for:

- Device address
- Service/characteristic UUID overrides
- Payload size (bytes) and packet count
- Test duration (seconds)
- Output directory
- Command IDs for Start/Stop/Reset (defaults to 0x01/0x02/0x03)

All parameters must be overridable so the same tooling can target future firmware revisions.

## 5. BLE Parameter Control & Limitations

- **MTU negotiation:** Attempt to request the maximum MTU supported by the stack, log the result, and warn if the negotiated MTU is below the requested value.
- **PHY selection:** Expose an option to request 1M, 2M, or Coded PHY when the adapter supports `bleak`/BlueZ APIs for PHY updates. Log the outcome (success/failure or not supported).
- **Connection interval:** Document that user-space clients typically cannot enforce a specific interval on commodity OS stacks. If unsupported, log the default interval reported by the stack (when exposed) and note the limitation in test reports.

## 6. Platform Guidance

- **Primary platform:** Linux host running Python 3.10+ with bleak. Tested against BlueZ 5.72.
- **Future extension:** Architecture should allow replacing the Python CLI with companion mobile apps (iOS or Android) if field testing requires on-device tooling. The BLE protocol must remain identical so results stay comparable.

## 7. Security & Access Assumptions

- Specify whether the DUT requires pairing or bonding. If yes, the software must trigger pairing flows and store keys securely (placeholder until DUT policy is finalized).
- If encryption is required, log the pairing/bonding status and note when encrypted connections are established.
- Access control assumptions (placeholders):
  - Pairing requirement: `<TBD: Just Works / Passkey / None>`
  - Bond retention behavior: `<TBD>`

Document any additional authentication or provisioning steps once the DUT firmware is available.
