# Bluetooth Performance Testing Lab Report

## 1. Objective

The objective of this lab is to systematically evaluate **Bluetooth performance characteristics** across multiple Bluetooth Classic (BR/EDR) and Bluetooth Low Energy (BLE) profiles. The lab focuses on measuring **throughput, latency, jitter, and stability**, and correlating observed performance with Bluetooth protocol behavior.

This document serves as the **formal experiment record**. It is written *before* data collection and intentionally contains **no results or conclusions**. All measurements will be added during experimentation.

---

## 2. Scope of Testing

Profiles covered in this lab include:

* Bluetooth Classic

  * PAN (Personal Area Network)
  * RFCOMM / SPP (Serial Port Profile)
  * HID (latency behavior)
  * A2DP / AVRCP (stability behavior)

* Bluetooth Low Energy

  * GATT-based data transfer
  * BLE notification throughput
  * BLE latency (request/response)

The lab evaluates both **application-level performance** and **protocol-level behavior**.

---

## 3. Test Environment

### 3.1 Linux A — Desktop PC (Server / NAP)

* Role: Bluetooth PAN Network Access Point (NAP), primary server
* Operating System: Ubuntu 24.04.3 LTS (x86_64)
* CPU: Intel Core i9-10920X (12 cores / 24 threads)
* Memory: 32 GB RAM
* Bluetooth Adapter:

  * Vendor: Intel Corporation
  * Bus: USB
  * Bluetooth Version: 5.3
  * BlueZ Version: 5.72
* Power: AC-powered

Linux A is selected to ensure that measured Bluetooth performance is not limited by host CPU or memory constraints.

---

### 3.2 Linux B — Laptop (Client / PANU)

* Role: Bluetooth PAN User (PANU), primary client
* Operating System: Ubuntu 24.04.3 LTS (x86_64)
* CPU: Intel Core i7-7600U (2 cores / 4 threads)
* Memory: 16 GB RAM
* Bluetooth Adapter:

  * Vendor: Intel Corporation
  * Bus: USB
  * Bluetooth Version: 4.2
  * BlueZ Version: 5.72
* Power: AC-powered unless otherwise stated

Linux B represents a lower-power client device, reflecting realistic consumer Bluetooth usage.

---

## 4. Test Topology

The lab uses a **direct, two-node Bluetooth topology** with no intermediate routing infrastructure.

```
Linux A (NAP / Server)  <---- Bluetooth ---->  Linux B (PANU / Client)
```

* Single ACL connection under test
* No Ethernet or Wi-Fi traffic involved in measurements
* All traffic traverses the Bluetooth stack exclusively

Detailed topology assumptions are defined in `docs/test_topology.md`.

---

## 5. Tools and Instrumentation

* `bluetoothctl` — pairing and device control
* `bt-network` / BlueZ PAN utilities — PAN setup
* `iperf3` — throughput, jitter, packet loss
* `ping` — basic latency validation
* `rfcomm` — serial profile testing
* `btmon` — HCI, L2CAP, ACL tracing
* Python + `bleak` — BLE GATT testing

All tools are executed on unmodified Ubuntu systems using default kernel and BlueZ configurations.

---

## 6. Experimental Procedures

### 6.1 PAN (Bluetooth Classic) — Throughput Baseline

**Purpose:** Establish baseline Classic Bluetooth throughput using IP over PAN.

**Transport Path:**

```
IP → BNEP → L2CAP → ACL → Radio
```

**Procedure:**

1. Pair Linux A and Linux B
2. Establish PAN connection (NAP ↔ PANU)
3. Verify `bnep0` interface on both devices
4. Assign IP addresses if necessary
5. Validate connectivity using `ping`
6. Run `iperf3` TCP and UDP tests
7. Capture `btmon` logs during transfer

**Metrics to Record:**

* Average throughput (Mbps)
* Jitter (UDP)
* Packet loss
* Retransmissions (from iperf and btmon)

---

### 6.2 RFCOMM / SPP — Serial Throughput

**Purpose:** Quantify overhead and throughput limitations of serial emulation.

**Transport Path:**

```
RFCOMM → L2CAP → ACL → Radio
```

**Procedure:**

1. Bind RFCOMM device
2. Send fixed-size data blocks
3. Measure transfer time
4. Record effective throughput

**Metrics to Record:**

* Effective throughput (Mbps)
* Transfer latency
* Stability over repeated trials

---

### 6.3 BLE GATT — Throughput and Latency

**Purpose:** Measure BLE data performance and scheduling effects.

**Transport Path:**

```
GATT → ATT → L2CAP (LE) → Link Layer → Radio
```

**Procedure:**

1. Configure GATT server on Linux A
2. Connect from Linux B using BLE client
3. Test notification throughput
4. Perform request/response latency measurements

**Metrics to Record:**

* Notifications per second
* Effective throughput (KB/s)
* Average and tail latency

---

## 7. Data Collection

All raw data is stored under:

* `logs/` — unmodified tool output (`btmon`, `iperf3`, RFCOMM logs)
* `results/tables/` — summarized numeric results
* `results/plots/` — generated charts

Each experiment is repeated multiple times to reduce variance.

---

## 8. Analysis (To Be Completed After Testing)

This section will analyze:

* Differences between PAN and RFCOMM throughput
* BLE throughput limitations relative to Classic Bluetooth
* Correlation between protocol behavior and measured results

---

## 9. Conclusions (Intentionally Blank)

Conclusions will be written **only after all experiments are completed**.

---

## 10. Change Control

* Kernel version: unchanged during experiments
* BlueZ version: unchanged during experiments
* Firmware: unchanged during experiments

Any deviations will be explicitly documented.
