# Bluetooth Architecture Overview

This document provides the protocol-level background needed to interpret the results of the Bluetooth Performance Testing Lab. It explains **how data moves through the Bluetooth stack**, why different profiles behave differently, and which layers are responsible for throughput, latency, and stability.

---

## 1. Bluetooth Stack Overview

Bluetooth is a layered protocol stack. Performance characteristics are determined primarily by **which layers are used** and **how they are configured**, not just by radio speed.

### High-Level Stack (Bluetooth Classic)

```
Application / Profile (PAN, RFCOMM, A2DP, HID)
L2CAP
ACL (Asynchronous Connection-Less)
Baseband / Link Controller
Radio (2.4 GHz ISM)
```

### High-Level Stack (Bluetooth Low Energy)

```
Application / Profile (GATT-based)
GATT / ATT
L2CAP (LE)
Link Layer (connection events)
Radio (2.4 GHz ISM)
```

---

## 2. ACL (Asynchronous Connection-Less)

### What ACL Is

* The **primary data transport** for Bluetooth Classic
* Used by PAN, RFCOMM, A2DP, HID, OBEX
* Packet-switched, reliable (retransmissions supported)

### Why ACL Matters for Performance

* All Classic profiles **share the same ACL link**
* Bandwidth is time-sliced between logical channels
* Retransmissions reduce effective throughput

### Key Properties

* Symmetric uplink/downlink
* Adaptive packet scheduling
* Supports multiple packet sizes (DM/DH types)

---

## 3. L2CAP (Logical Link Control and Adaptation Protocol)

### Purpose

L2CAP sits on top of ACL and provides:

* Multiplexing of multiple logical channels
* Segmentation and reassembly of packets
* Flow control and MTU enforcement

### Why L2CAP Dominates Profile Behavior

* Profiles differ mainly in **how they use L2CAP**
* MTU size directly impacts throughput
* Channel scheduling impacts latency

### Examples

* PAN uses large MTUs and continuous streams
* RFCOMM uses small frames with heavy control overhead
* BLE GATT uses short packets tied to connection intervals

---

## 4. Profile-Level Behavior

### PAN (Personal Area Network)

* Runs IP over BNEP over L2CAP
* Optimized for bulk data transfer
* Best proxy for raw ACL throughput

### RFCOMM / SPP

* Emulates serial ports
* Adds framing, flow control, and credit-based scheduling
* Significantly lower throughput than PAN

### A2DP

* Continuous media streaming
* Fixed bitrate determined by codec
* Prioritizes smooth playback over throughput

### HID / HOGP

* Very small packets
* High polling frequency
* Optimized for latency, not bandwidth

### BLE GATT

* Attribute-based data model
* Throughput limited by connection interval, MTU, and PHY
* Highly power-efficient

---

## 5. Bluetooth Low Energy (BLE) Constraints

### Connection Interval

* Determines how often data can be exchanged
* Shorter intervals = lower latency, higher power usage

### MTU Size

* Default MTU is small
* Increasing MTU improves throughput but not latency

### PHY

* 1M, 2M, and Coded PHYs trade speed for range

---

## 6. Firmware and Controller Effects

Bluetooth performance is influenced by:

* Controller generation (e.g., Bluetooth 4.2 vs 5.3)
* Firmware scheduling decisions
* Host-controller interface efficiency

These effects are often visible in **btmon traces** as:

* Retransmissions
* Delayed acknowledgments
* Channel congestion

---

## 7. Why This Matters for the Lab

Understanding this architecture allows lab results to be explained in terms of:

* Protocol overhead
* Scheduling behavior
* Hardware capability differences

Rather than treating Bluetooth as a black box, this lab correlates **measured performance** with **stack-level behavior**.

---

## 8. Key Takeaway

> Bluetooth performance differences are primarily a result of **protocol design choices**, not radio speed alone.
