# Bluetooth Test Topology

This document defines the **logical and physical topology** used in the Bluetooth Performance Testing Lab. It formalizes device roles, traffic direction, and assumptions so that all experiments are **repeatable, interpretable, and comparable**.

---

## 1. Topology Overview

The lab uses a **direct, two-node Bluetooth topology** with no intermediate routing or infrastructure devices.

```
+----------------------+        Bluetooth Classic / BLE        +----------------------+
|      Linux A         | <----------------------------------> |       Linux B         |
| Desktop PC           |                                      | Laptop                |
| PAN NAP / Server     |                                      | PANU / Client         |
| BT 5.3 (Intel)       |                                      | BT 4.2 (Intel)        |
+----------------------+                                      +----------------------+
```

Key characteristics:

* Point-to-point Bluetooth link
* Single ACL connection under test
* No access points, routers, or gateways involved

This topology isolates Bluetooth performance from external network variables.

---

## 2. Device Roles

### 2.1 Linux A — Server / Network Access Point (NAP)

* Acts as the **Bluetooth PAN Network Access Point**
* Runs throughput and latency servers (e.g., `iperf3 -s`)
* Captures protocol traces (`btmon`) during experiments
* Selected for higher CPU capacity and newer Bluetooth controller

Linux A represents a **capable host device** such as a desktop PC, laptop, or embedded gateway.

---

### 2.2 Linux B — Client / PAN User (PANU)

* Acts as the **Bluetooth PAN User**
* Generates test traffic (e.g., `iperf3 -c`)
* Initiates RFCOMM and BLE GATT transactions
* Selected to represent a **lower-power consumer client**

Linux B represents devices such as laptops, tablets, or mobile clients commonly used with Bluetooth peripherals.

---

## 3. Traffic Direction Conventions

To ensure consistency across experiments, the following conventions are used unless otherwise stated:

* **Primary throughput direction**: Linux B → Linux A
* **Reverse direction tests**: Linux A → Linux B (validation only)
* **Control and signaling traffic**: Bidirectional

This convention simplifies result comparison across profiles.

---

## 4. Profile-Specific Topologies

### 4.1 PAN (Personal Area Network)

* Logical topology: IP network over Bluetooth
* Transport path:

  ```
  IP → BNEP → L2CAP → ACL → Radio
  ```
* Linux A: NAP + IP endpoint
* Linux B: PANU + IP endpoint

This configuration enables standard IP-based tools (e.g., `ping`, `iperf3`) to be used for measurement.

---

### 4.2 RFCOMM / SPP

* Logical topology: Point-to-point serial link
* Transport path:

  ```
  Serial Stream → RFCOMM → L2CAP → ACL → Radio
  ```
* Linux A: RFCOMM server / reader
* Linux B: RFCOMM client / sender

This topology emulates legacy serial cable behavior.

---

### 4.3 BLE GATT

* Logical topology: Attribute-based client/server
* Transport path:

  ```
  GATT → ATT → L2CAP (LE) → Link Layer → Radio
  ```
* Linux A: GATT server (peripheral)
* Linux B: GATT client (central)

This topology reflects common BLE sensor and IoT deployments.

---

## 5. Physical Environment Assumptions

Unless explicitly varied during testing:

* Devices are placed within line-of-sight
* Initial separation distance: ~1 meter
* No intentional RF shielding
* Typical indoor environment

Environmental variables (distance, orientation, interference) are only modified during dedicated experiments.

---

## 6. Network Isolation Assumptions

* Ethernet and Wi-Fi interfaces are not used for test traffic
* Bluetooth PAN interfaces (`bnep0`) are verified before each test
* No IP routing or NAT is enabled between interfaces

This ensures that all measured traffic traverses the Bluetooth link under test.

---

## 7. Repeatability Guidelines

To reproduce experiments:

1. Use the same device roles and topology
2. Verify Bluetooth firmware and BlueZ versions
3. Maintain consistent physical placement
4. Reset Bluetooth connections between tests

Any deviations are documented in experiment notes.

---

## 8. Key Takeaway

> Clear role definition and topology control are essential for meaningful Bluetooth performance measurements.
