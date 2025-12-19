## BLE Troubleshooting

- **Permissions / adapter busy:** If scripts fail with `Operation not permitted`, ensure the user belongs to the `bluetooth` group or temporarily run via sudo. Close GUI Bluetooth managers or other tools that keep the adapter busy.
- **Device not found / scan stalls:** Re-enable scanning with `bluetoothctl` (`power off/on`, `scan on`) and confirm the DUT is advertising at the expected address. Clear `rfkill` blocks when adapters appear soft-disabled.
- **Notifications not firing:** Double-check TX CCCD writes (scripts abort if the enable step fails). Provide the correct 128-bit UUIDs and clear OS caches (`sudo rm -r /var/lib/bluetooth/<adapter>/<device>`) after firmware updates.
- **Disconnects during high notify rate:** Lower the requested payload size or packet rate, and verify the DUT only queues the next notification after a TX-complete event to avoid controller buffer overruns. Capture `btmon` traces for debugging.
- **MTU negotiation never changes:** BlueZ often keeps the default MTU; scripts already log the negotiated size so treat this as informational unless the DUT requires a larger MTU.
- **RSSI unavailable via user space:** Some adapters expose RSSI only while scanning. The RSSI logger records null values plus a note so the limitation is obvious; use dedicated sniffers (nRF52840 DK, CC2642) when continuous RSSI is mandatory.
- **BR/EDR vs LE conflicts:** When both adapters share the same MAC, BlueZ may default to a BR/EDR connection (especially after a refactor or cache reset). Symptoms: `btmon` shows classic L2CAP/RFCOMM activity and Bleak reports `BleakDeviceNotFoundError`. Fix by forcing the adapters into LE-only mode before testing:
  ```bash
  sudo btmgmt -i hci0 power off
  sudo btmgmt -i hci0 le on
  sudo btmgmt -i hci0 bredr off
  sudo btmgmt -i hci0 power on
  ```
  Run that on **both** hosts, restart bluetoothd/mock, and re-run the throughput client. Restore BR/EDR later with `sudo btmgmt -i hci0 bredr on` + power cycle.
- **LE link drops immediately (Reason 0x3e)**: After forcing LE-only, a connection might still collapse right after `LE Read Remote Used Features`. Clear `/var/lib/bluetooth/<adapter>/` on both hosts, restart bluetoothd, and ensure the mock stays running—this removes stale bond info and the LE link stays up for the test.
