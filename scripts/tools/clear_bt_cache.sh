#!/bin/bash
# Helper to clear BlueZ device caches safely.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
cd "$repo_root"

usage() {
  cat <<'HELP'
Usage: scripts/tools/clear_bt_cache.sh --adapter <MAC> [--device <MAC>|--all] [--yes]

Clears cached data under /var/lib/bluetooth/<adapter>/<device>. Run this on a host
when BLE connections keep failing after firmware/GATT changes.

Options:
  --adapter <MAC>   Adapter address (AA:BB:CC:DD:EE:FF). Required.
  --device <MAC>    Device/DUT address to clear. Required unless --all is used.
  --all             Remove every cached device directory for the adapter.
  --yes             Skip confirmation prompt.
  -h | --help       Show this help.

Examples:
  scripts/tools/clear_bt_cache.sh --adapter AA:BB:CC:DD:EE:FF --device 11:22:33:44:55:66
  scripts/tools/clear_bt_cache.sh --adapter AA:BB:CC:DD:EE:FF --all --yes
HELP
}

adapter=""
device=""
all_flag=false
force=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --adapter)
      adapter="${2:-}"
      shift 2 || true
      ;;
    --device)
      device="${2:-}"
      shift 2 || true
      ;;
    --all)
      all_flag=true
      shift
      ;;
    --yes)
      force=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[clear_bt_cache] Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$adapter" ]]; then
  echo "[clear_bt_cache] --adapter is required." >&2
  usage >&2
  exit 1
fi

normalise_mac() {
  echo "$1" | tr '[:lower:]' '[:upper:]'
}

adapter_dir="/var/lib/bluetooth/$(normalise_mac "$adapter")"

if [[ ! -d "$adapter_dir" ]]; then
  echo "[clear_bt_cache] Adapter directory $adapter_dir not found." >&2
  exit 1
fi

if $all_flag && [[ -n "$device" ]]; then
  echo "[clear_bt_cache] Use either --device or --all, not both." >&2
  exit 1
fi

if ! $all_flag && [[ -z "$device" ]]; then
  echo "[clear_bt_cache] Provide --device <MAC> or use --all." >&2
  exit 1
fi

target_desc=""
target_path=""
if $all_flag; then
  target_desc="all cached devices under ${adapter_dir}"
  target_path="$adapter_dir"  # remove subdirectories only
else
  device_dir="$(normalise_mac "$device")"
  target_path="${adapter_dir}/${device_dir}"
  target_desc="device cache ${device_dir}"
fi

if [[ ! -d "$target_path" ]]; then
  echo "[clear_bt_cache] Target ${target_desc} not found at ${target_path}."
  exit 0
fi

echo "[clear_bt_cache] This will delete ${target_desc}."
if ! $force; then
  read -r -p "Proceed? [y/N] " reply
  case "$reply" in
    [Yy]*) ;;
    *) echo "[clear_bt_cache] Aborted."; exit 0 ;;
  esac
fi

echo "[clear_bt_cache] Stopping bluetooth service..."
sudo systemctl stop bluetooth

if $all_flag; then
  echo "[clear_bt_cache] Removing cached device directories under ${adapter_dir}"
  sudo find "$adapter_dir" -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} +
else
  echo "[clear_bt_cache] Removing ${target_path}"
  sudo rm -rf "$target_path"
fi

echo "[clear_bt_cache] Starting bluetooth service..."
sudo systemctl start bluetooth

echo "[clear_bt_cache] Done. Power-cycle adapters or reboot devices if issues remain."
