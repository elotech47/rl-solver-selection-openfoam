#!/usr/bin/env bash
# One-liner checklist for the remote host after git clone.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
chmod +x validation/zeroD/e17_remote/*.sh validation/zeroD/e17_*.sh tools/*.sh 2>/dev/null || true

echo "=== 1) bootstrap (build) ==="
bash validation/zeroD/e17_remote/00_bootstrap.sh

echo "=== 2) run (edit NPROC) ==="
export NPROC="${NPROC:-8}"
export E17_MODE="${E17_MODE:-cvodeOnly}"
export E17_END_TIME="${E17_END_TIME:-0.001}"
export E17_OUT="${E17_OUT:-validation/zeroD/e17_remote_runs/quickstart_${E17_MODE}}"
bash validation/zeroD/e17_remote/01_run_ignition_scout.sh

echo "=== 3) extract ==="
bash validation/zeroD/e17_remote/02_extract_results.sh

echo "=== 4) preprocess ==="
python3 validation/zeroD/e17_remote/03_preprocess.py --run-dir "$E17_OUT"

echo "DONE. Bundle: $E17_OUT/extract/bundle.tgz"
