# Bluetooth Performance Testing Lab

A hands-on, systems-level laboratory for **Bluetooth performance testing** across **Bluetooth Classic (BR/EDR)** and **Bluetooth Low Energy (BLE)** profiles.
This project focuses on understanding how **profiles, protocols, and hardware constraints** affect real-world Bluetooth throughput, latency, and stability.

> This repository is structured to mirror how Bluetooth validation and embedded connectivity labs document, run, and analyze experiments.

---

## 📌 Project Goals

* Measure **Bluetooth Classic ACL throughput** using PAN (baseline)
* Compare PAN against **RFCOMM/SPP** to understand protocol overhead
* Measure **BLE GATT throughput and latency**
* Observe protocol behavior using **btmon (HCI/L2CAP tracing)**
* Correlate performance results with Bluetooth architecture decisions

---

## 🧠 Bluetooth Concepts Covered

* Bluetooth Classic vs BLE
* ACL (Asynchronous Connection-Less) transport
* L2CAP multiplexing and MTU behavior
* Profile-level tradeoffs (PAN, RFCOMM, HID, A2DP, GATT)
* Firmware, controller, and OS stack interactions

---

## 🧪 Test Topology

```
+----------------------+        Bluetooth Classic / BLE        +----------------------+
|      Linux A         | <----------------------------------> |       Linux B         |
| Desktop PC           |                                      | Laptop               |
| PAN NAP / Server     |                                      | PANU / Client         |
| BT 5.3 (Intel)       |                                      | BT 4.2 (Intel)        |
+----------------------+                                      +----------------------+
```

* **Linux A** acts as the Bluetooth PAN Network Access Point (NAP) and server
* **Linux B** acts as the PAN User (PANU) and client
* Direct device-to-device Bluetooth connection (no routing infrastructure)

---

## 🖥️ Test Environment

### Linux A — Desktop PC (Server / NAP)

* OS: Ubuntu 24.04.3 LTS (x86_64)
* CPU: Intel Core i9-10920X (12C / 24T)
* RAM: 32 GB
* Bluetooth Adapter: Intel USB controller
* Bluetooth Version: 5.3
* BlueZ: 5.72
* Role: PAN NAP, iperf server

### Linux B — Laptop (Client / PANU)

* OS: Ubuntu 24.04.3 LTS (x86_64)
* CPU: Intel Core i7-7600U (2C / 4T)
* RAM: 16 GB
* Bluetooth Adapter: Intel USB controller
* Bluetooth Version: 4.2
* BlueZ: 5.72
* Role: PANU, traffic generator

---

## 📂 Repository Structure

```
bluetooth-performance-lab/
├── README.md
├── docs/
│   ├── lab_report.md
│   ├── bluetooth_architecture.md
│   └── test_topology.md
├── experiments/
│   ├── pan/
│   │   ├── pan_setup.md
│   │   ├── pan_results.md
│   │   └── pan_notes.md
│   ├── rfcomm/
│   │   ├── rfcomm_setup.md
│   │   ├── rfcomm_results.md
│   │   └── rfcomm_notes.md
│   ├── ble_gatt/
│   │   ├── ble_setup.md
│   │   ├── ble_results.md
│   │   └── ble_notes.md
│   └── interference/
│       ├── distance_tests.md
│       └── coexistence_tests.md
├── scripts/
│   ├── pan/
│   │   └── pan_iperf.sh
│   ├── rfcomm/
│   │   └── rfcomm_transfer.sh
│   └── ble/
│       ├── gatt_server.py
│       └── gatt_client.py
├── logs/
│   ├── btmon/
│   ├── iperf/
│   └── rfcomm/
├── results/
│   ├── tables/
│   └── plots/
└── notes/
    ├── troubleshooting.md
    └── observations.md
```

---

## 🧰 Tooling

* **BlueZ** — Linux Bluetooth stack
* **bt-network / bluetoothctl** — PAN setup and pairing
* **iperf3** — throughput and jitter
* **btmon** — HCI / L2CAP tracing
* **rfcomm** — SPP testing
* **Python + bleak** — BLE GATT testing

---

## 🧪 Experiments Overview

| Experiment        | Profile  | Transport   | Metrics           |
| ----------------- | -------- | ----------- | ----------------- |
| PAN baseline      | PAN      | ACL + L2CAP | Mbps, retransmits |
| Serial comparison | RFCOMM   | ACL + L2CAP | Effective Mbps    |
| BLE throughput    | GATT     | LE          | KB/s, latency     |
| HID behavior      | HID/HOGP | ACL / LE    | Latency           |
| Interference      | Multiple | ACL / LE    | Stability         |

---

## 🚦 Experiment Status

* [ ] PAN baseline throughput
* [ ] RFCOMM throughput comparison
* [ ] BLE GATT throughput & latency
* [ ] Distance/orientation sweep
* [ ] Interference testing (Wi-Fi / USB 3.0)

---

## 📎 Notes

* No kernel, firmware, or BlueZ versions are modified during experiments
* Results are hardware- and environment-dependent
* This repository prioritizes **repeatability and traceability** over synthetic benchmarks

---

## 📘 References

* Bluetooth Core Specification
* BlueZ Documentation
* Linux Kernel Bluetooth Subsystem

---

## ⚠️ Disclaimer

This project is for educational and experimental purposes. Performance results may vary significantly depending on hardware, firmware, and RF environment.
