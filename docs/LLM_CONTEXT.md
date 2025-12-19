# LLM Context — Smart Ring BLE Performance Lab

**Audience:** Coding assistants working on this repo  
**Purpose:** Provide canonical context so helpers avoid re-discovery, outdated assumptions, or fabricated data.

---

## 1. Project Snapshot

- This repository houses a **BLE-focused performance lab** for the Smart Ring test service. The goal is to gather throughput, latency, RSSI, and connection health metrics *before* real hardware ships.
- Core automation lives in `scripts/ble/run_full_matrix.py`, invoked via `scripts/tools/run_full_matrix.sh`. It sweeps payloads, PHYs, and scenarios, and now writes connection retry metadata so flaky runs are obvious.
- The mock peripheral (`scripts/tools/start_mock.sh`) emulates the Smart Ring GATT service. Force adapters into **LE-only mode** and clear caches via `scripts/tools/clear_bt_cache.sh` when switching firmware or after BR/EDR conflicts.
- Every client (throughput, latency, RSSI) shares the same retry CLI flags: `--connect_timeout_s`, `--connect_attempts`, `--connect_retry_delay_s`. Console logs show `[throughput] Connected …`, `[latency] Connection attempt … failed`, etc.
- Results: CSV/JSON logs in `logs/ble/`, aggregated tables under `results/tables/`, and plots under `results/plots/` with color-coded health markers.

---

## 2. Current State

- ✅ BLE clients + automation implemented and share retry controls.
- ✅ Mock peripheral + helper scripts verified.
- ✅ Documentation updated (this file, `docs/how_to_run_experiments.md`, `docs/test_coverage_plan.md`, etc.).
- ⚠️ Real Smart Ring hardware **not connected yet**. Never invent measured data.
- ⚠️ BlueZ may still get stuck in BR/EDR mode; enforce LE-only and clear caches before blaming the scripts.

---

## 3. Repository Structure (essentials)

```
bluetooth-performance-lab/
├── README.md
├── docs/                  # Lab how-to, coverage plan, architecture notes
├── notes/                 # Additional planning / troubleshooting detail
├── scripts/
│   ├── ble/               # Clients, mock, analysis helpers
│   └── tools/             # setup/run wrappers, cache cleaner, archiver
├── experiments/           # Legacy experiment notes (pan/rfcomm/etc.)
├── logs/                  # Raw outputs (ignored by git)
└── results/               # Derived tables/plots
```

---

## 4. Expectations for LLM Helpers

Allowed:

- Add or update scripts, docs, or analysis tooling.
- Modify configs/README/docs when explicitly asked (this file already grants permission).
- Improve logging, retry logic, plotting, or tooling reliability.

Not allowed:

- Invent throughput/latency/RSSI numbers. Use placeholders or describe procedures instead.
- Change hardware descriptions without instructions from the user.
- Commit destructive git actions (e.g., `reset --hard`) unless the user explicitly requests it.

When unsure, ask the user for clarification rather than guessing.
