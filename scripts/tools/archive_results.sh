#!/bin/bash
# Archive the latest BLE logs/results into a timestamped folder for historical reference.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/tools/archive_results.sh [--tag LABEL] [--cleanup]

Copies the current BLE logs (logs/ble/, logs/mock_dut.log) and analysis outputs
(results/tables/, results/plots/) into archives/<timestamp>[_LABEL]/ so you can
keep a history of every run. Use --cleanup to clear logs/ble and results/* after
archiving (calls cleanup_outputs.sh).
EOF
}

TAG=""
CLEANUP=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      shift
      [[ $# -gt 0 ]] || { echo "--tag requires a value" >&2; exit 1; }
      TAG="$1"
      ;;
    --cleanup)
      CLEANUP=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

timestamp="$(date +%Y%m%d_%H%M%S)"
run_id="$timestamp"
if [[ -n "$TAG" ]]; then
  safe_tag="$(echo "$TAG" | tr ' ' '_' )"
  run_id="${run_id}_${safe_tag}"
fi

archive_dir="$REPO_ROOT/archives/$run_id"
mkdir -p "$archive_dir"

copy_dir_if_exists() {
  local src="$1"
  local dest="$2"
  if [[ -d "$src" ]]; then
    mkdir -p "$(dirname "$dest")"
    rsync -a "$src/" "$dest/"
  fi
}

copy_file_if_exists() {
  local src="$1"
  local dest="$2"
  if [[ -f "$src" ]]; then
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
  fi
}

echo "[archive] Saving logs/ble -> archives/$run_id/logs/ble"
copy_dir_if_exists "$REPO_ROOT/logs/ble" "$archive_dir/logs/ble"

echo "[archive] Saving logs/mock_dut.log -> archives/$run_id/logs/mock_dut.log"
copy_file_if_exists "$REPO_ROOT/logs/mock_dut.log" "$archive_dir/logs/mock_dut.log"

echo "[archive] Saving results/tables -> archives/$run_id/results/tables"
copy_dir_if_exists "$REPO_ROOT/results/tables" "$archive_dir/results/tables"

echo "[archive] Saving results/plots -> archives/$run_id/results/plots"
copy_dir_if_exists "$REPO_ROOT/results/plots" "$archive_dir/results/plots"

cat > "$archive_dir/metadata.txt" <<EOF
run_id: $run_id
archived_at: $(date --iso-8601=seconds)
tag: ${TAG:-<none>}
git_commit: $(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
EOF

echo "[archive] Created $archive_dir"

if $CLEANUP; then
  echo "[archive] Cleaning logs/ble and results/* via cleanup_outputs.sh"
  ./scripts/tools/cleanup_outputs.sh --yes
fi
