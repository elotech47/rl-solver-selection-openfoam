#!/usr/bin/env bash
# Kill leftovers, run qssOnly+rlAdaptive to endTime=0.000107, then preprocess+viz.
# Smoke already runs per-mode post/preprocess; this adds campaign-level maps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
# Always pin short horizon unless E17_END_TIME_FORCE is set (ignore stale E17_END_TIME).
export E17_END_TIME="${E17_END_TIME_FORCE:-0.000107}"
export E17_MODES="${E17_MODES:-qssOnly rlAdaptive}"
export E17_SKIP_KERNEL="${E17_SKIP_KERNEL:-1}"
export NPROC="${NPROC:-16}"

# Prefer a dedicated short-horizon folder (do not clobber the aborted 2e-4 run)
STAMP="$(date +%Y%m%d_%H%M%S)"
export E17_SMOKE_OUT_FORCE="${E17_SMOKE_OUT_FORCE:-$ROOT/validation/zeroD/e17_remote_runs/e17_2_t107_${STAMP}}"

echo "=== E17.2 short run endTime=$E17_END_TIME → $E17_SMOKE_OUT_FORCE ==="
BASE="$E17_SMOKE_OUT_FORCE"
bash "$ROOT/validation/zeroD/e17_2/e17_2_guarded_rerun.sh"

if [[ ! -d "$BASE" ]]; then
  BASE="$(cat "$ROOT/validation/zeroD/e17_remote_runs/.e17_2_last_out" 2>/dev/null || true)"
fi
if [[ ! -d "$BASE" ]]; then
  BASE="$(ls -dt "$ROOT"/validation/zeroD/e17_remote_runs/e17_2_t107_* 2>/dev/null | head -1)"
fi

echo "=== campaign viz → $BASE/viz ==="
python3 "$ROOT/validation/zeroD/e17_2/e17_2_viz_campaign.py" --base "$BASE" || true
echo "DONE base=$BASE"
