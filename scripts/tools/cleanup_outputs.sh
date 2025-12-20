#!/bin/bash
# Remove or archive BLE log/results so a new campaign starts clean.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

ARCHIVE=0
FORCE=0

usage() {
  cat <<'EOF'
Usage: scripts/cleanup_outputs.sh [--archive] [--yes]

  --archive   Create archives/ble_cleanup_<ts>.tar.gz containing logs/ble and results/* before deletion.
  --yes       Skip the interactive confirmation prompt.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --archive) ARCHIVE=1 ;;
    --yes|-y) FORCE=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

TARGETS=(logs/ble results/tables results/plots)
MOCK_LOG="logs/mock_dut.log"
EXISTING=()
for path in "${TARGETS[@]}"; do
  mkdir -p "$path"
  EXISTING+=("$path")
done
# Ensure mock log parent exists for optional cleanup
mkdir -p "$(dirname "$MOCK_LOG")"

echo "[cleanup] The following directories will be cleared (empty directories are reset):"
for path in "${EXISTING[@]}"; do
  echo "  - $path"
done

if [[ $ARCHIVE -eq 1 ]]; then
  ts="$(date +%Y%m%d_%H%M%S)"
  archive_dir="archives"
  mkdir -p "$archive_dir"
  archive_path="$archive_dir/ble_cleanup_${ts}.tar.gz"
  echo "[cleanup] Archiving contents to $archive_path"
  tar -czf "$archive_path" "${EXISTING[@]}" "$MOCK_LOG"
fi

if [[ $FORCE -eq 0 ]]; then
  read -r -p "Proceed with deletion? [y/N] " answer
  case "$answer" in
    y|Y|yes|YES) ;;
    *) echo "[cleanup] Aborted."; exit 1 ;;
  esac
fi

for path in "${EXISTING[@]}"; do
  echo "[cleanup] Removing contents of $path"
  rm -rf "$path"
  mkdir -p "$path"
done

if [[ -f "$MOCK_LOG" ]]; then
  echo "[cleanup] Removing $MOCK_LOG"
  rm -f "$MOCK_LOG"
fi

echo "[cleanup] Done."
