#!/bin/bash
# Remove or archive BLE log/results so a new campaign starts clean.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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
EXISTING=()
for path in "${TARGETS[@]}"; do
  if [[ -d "$path" && "$(ls -A "$path" 2>/dev/null)" ]]; then
    EXISTING+=("$path")
  fi
done

if [[ ${#EXISTING[@]} -eq 0 ]]; then
  echo "[cleanup] No logs/ble or results/* contents to remove."
  exit 0
fi

echo "[cleanup] The following directories will be cleared:"
for path in "${EXISTING[@]}"; do
  echo "  - $path"
done

if [[ $ARCHIVE -eq 1 ]]; then
  ts="$(date +%Y%m%d_%H%M%S)"
  archive_dir="archives"
  mkdir -p "$archive_dir"
  archive_path="$archive_dir/ble_cleanup_${ts}.tar.gz"
  echo "[cleanup] Archiving contents to $archive_path"
  tar -czf "$archive_path" "${EXISTING[@]}"
fi

if [[ $FORCE -eq 0 ]]; then
  read -r -p "Proceed with deletion? [y/N] " answer
  case "$answer" in
    y|Y|yes|YES) ;;
    *) echo "[cleanup] Aborted."; exit 1 ;;
  esac
fi

shopt -s dotglob nullglob
for path in "${EXISTING[@]}"; do
  echo "[cleanup] Removing contents of $path"
  rm -rf "$path"/*
  mkdir -p "$path"
done
shopt -u dotglob nullglob

echo "[cleanup] Done."
