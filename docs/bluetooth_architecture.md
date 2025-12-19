# BLE Architecture Notes for the Smart Ring Lab

This lab is now **BLE-only**, so this document focuses on the parts of the stack that matter for throughput, latency, and reliability when exercising the Smart Ring test service.

---

## 1. Stack Layers in Play

```
Application (Smart Ring test service)
└─ GATT (service + characteristics)
   └─ ATT
      └─ L2CAP (LE)
         └─ Link Layer (connection events)
            └─ PHY / Radio (LE 1M, 2M, Coded)
```

- **Service UUID:** `12345678-1234-5678-1234-56789ABCDEF0`
- **TX characteristic (DUT → central, Notify):** `...DEF1`
- **RX characteristic (central → DUT, Write Without Response):** `...DEF2`

The lab never touches BR/EDR profiles (PAN, RFCOMM, etc.) anymore; forcing adapters into LE-only mode prevents them from interfering.

---

## 2. Why MTU & Payload Matter

- The Smart Ring payload embeds `[SEQ][TS][DATA…]`. The scripts let you sweep `payload_bytes` to see how MTU headroom affects throughput.
- BlueZ defaults to MTU 23. The clients call `request_mtu()` and log the negotiated value in case the controller refuses.
- Throughput plots encode payload size on the x-axis, so you can correlate MTU behavior with packet loss.

---

## 3. PHY Selection

- `auto` leaves the adapter default (usually LE 1M).
- `2m` (or `1m` / `coded` when enabled) uses `set_preferred_phy`.
- Results are captured as `phy_request`/`phy_result` in each JSON log so you know whether the OS actually honored the request.

---

## 4. Connection Interval & Retries

- User space cannot directly force a connection interval, so the lab logs whatever the DUT negotiates (when exposed) and uses **connection retry metadata** as a proxy for link stability.
- Every client now records:
  - `connection_retry.timeout_s`
  - Number of attempts requested/used
  - `command_errors` when stop/reset writes fail during teardown
- Plots color markers orange/red when retries or command failures occur to highlight unstable runs even if throughput numbers look fine.

---

## 5. Command Flow (RX characteristic)

```
Reset (0x03) → short delay
Start (0x01, payload size + optional packet count)
   \→ DUT streams notifications on TX
Stop (0x02) → Stop Notify
```

- All commands are Write Without Response. If the DUT disconnects mid-teardown, the clients log the failure and move on so logs are still written.
- Latency runs reuse the same command flow but gate on individual notifications to measure Start-to-first-notification or trigger-mode latency.

---

## 6. Traceability in Logs

Each JSON metadata block includes:

- Adapter name + timestamp
- Requested/negotiated MTU & PHY
- Command log (with timestamps + payloads)
- Link health data:
  - `connection_attempts_used`
  - `command_errors`
  - Duration, packet counts, estimated loss

These fields make it possible to correlate BLE stack behavior (e.g., repeated retries) with environment notes or btmon traces.

---

## 7. Takeaway

Performance in this lab is dictated by **connection event scheduling + MTU/PHY configuration**, not radio marketing numbers. Capturing retries, MTU negotiation, and command failures alongside throughput/latency results gives enough context to explain anomalies once the real Smart Ring hardware arrives.
