#!/usr/bin/env bash
# Detached E16.4 batch runner (setsid-safe). Resume-friendly via run_meta.json.
set -eo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export DOCKER_HOST="${DOCKER_HOST:-unix:///Users/el0tech/.colima/default/docker.sock}"
export KMP_DUPLICATE_LIB_OK=TRUE
export TQDM_DISABLE=1
PY="${PY:-/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python}"
LOGDIR="$ROOT/validation/e16_parity/e16_4_runs"
mkdir -p "$LOGDIR"
exec > >(tee -a "$LOGDIR/log_batch.txt") 2>&1

echo "[batch] start $(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$PY" validation/zeroD/e16_4_write_ics.py --all

run_of() {
  local cid=$1 label=$2 T0=$3 p=$4 Z=$5 dt=$6 tend=$7 mode=$8
  local meta="$LOGDIR/${cid}_${mode}/run_meta.json"
  if [[ -f "$meta" ]]; then
    echo "[batch] skip OF $cid $mode"
    return 0
  fi
  echo "[batch] OF $cid $mode $(date -u +%H:%M:%S)"
  docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work --memory=7g \
    opencfd/openfoam-default:2312 \
    -lc "bash /work/validation/zeroD/e16_4_run_one.sh $cid $label $T0 $p $Z $dt $tend $mode"
}

run_py() {
  local cid=$1
  if [[ -f "$LOGDIR/${cid}_python/summary.json" ]]; then
    echo "[batch] skip PY $cid"
    return 0
  fi
  echo "[batch] PY $cid $(date -u +%H:%M:%S)"
  "$PY" -u validation/zeroD/e16_4_python.py --id "$cid"
}

# Order: shorter first; C1 last
for cid in C2 C3 C4 C1; do
  run_py "$cid" || echo "[batch] PY $cid FAILED (continue)"
done

# OF conditions
run_of C2 MidT_MidP 800 10 0.062 1e-6 0.0035 cvodeOnly
run_of C2 MidT_MidP 800 10 0.062 1e-6 0.0035 qssOnly
run_of C2 MidT_MidP 800 10 0.062 1e-6 0.0035 rlAdaptive

run_of C3 HighT_HighP 1000 30 0.042 1e-6 0.003 cvodeOnly
run_of C3 HighT_HighP 1000 30 0.042 1e-6 0.003 qssOnly
run_of C3 HighT_HighP 1000 30 0.042 1e-6 0.003 rlAdaptive

run_of C4 LowT_VeryHighP 750 60 0.042 1e-6 0.0025 cvodeOnly
run_of C4 LowT_VeryHighP 750 60 0.042 1e-6 0.0025 qssOnly
run_of C4 LowT_VeryHighP 750 60 0.042 1e-6 0.0025 rlAdaptive

run_of C1 LowT_LowP 650 1 0.062 1e-5 0.12 cvodeOnly
run_of C1 LowT_LowP 650 1 0.062 1e-5 0.12 qssOnly
run_of C1 LowT_LowP 650 1 0.062 1e-5 0.12 rlAdaptive

echo "[batch] figures+gate $(date -u +%H:%M:%S)"
"$PY" analysis/e16_4_figures.py || true
"$PY" validation/zeroD/e16_4_gate.py || true
echo "[batch] ALL_DONE $(date -u +%Y-%m-%dT%H:%M:%SZ)"
