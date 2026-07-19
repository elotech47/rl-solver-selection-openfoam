#!/usr/bin/env bash
# Host: rebuild RL libs if needed, run E16.3 OF MidT+NTC modes, then gate script.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export DOCKER_HOST="${DOCKER_HOST:-unix:///Users/el0tech/.colima/default/docker.sock}"

ENDT="${E16_3_ENDT:-0.002}"
SMOKE="${E16_3_SMOKE:-0}"  # if 1, endTime=2e-4

if [[ "$SMOKE" == "1" ]]; then
  ENDT="0.0002"
fi

echo "[e16.3 host] ENDT=$ENDT rebuilding libs..."
docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work --memory=7g \
  opencfd/openfoam-default:2312 \
  -lc 'set +eu; source /usr/lib/openfoam/openfoam2312/etc/bashrc; set -e; set +u
       export WM_PROJECT_USER_DIR=/work FOAM_USER_LIBBIN=/work/platforms/${WM_OPTIONS}/lib
       export FOAM_USER_APPBIN=/work/platforms/${WM_OPTIONS}/bin
       export LIBTORCH_DIR=/work/opt/libtorch SUNDIALS_DIR=/work/opt/sundials-arm64
       export LD_LIBRARY_PATH=$LIBTORCH_DIR/lib:$SUNDIALS_DIR/lib:${LD_LIBRARY_PATH:-}
       cd /work/src/rlChemistryModel && wmake libso
       '

run_pair() {
  local label="$1" T0="$2" patm="$3" phi="$4"
  for mode in rlAdaptive cvodeOnly qssOnly; do
    echo "===== OF $label $mode ====="
    docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
      -v "$ROOT:/work" -w /work --memory=7g \
      opencfd/openfoam-default:2312 \
      -lc "bash /work/validation/zeroD/e16_3_run_one.sh $label $T0 $patm $phi $ENDT $mode"
  done
}

run_pair MidT 800 10 1.0
run_pair NTC 700 10 1.0

echo "[e16.3 host] Python reference..."
PY="${PY:-/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python}"
export KMP_DUPLICATE_LIB_OK=TRUE
"$PY" validation/zeroD/e16_3_python_ref.py --t-end "$ENDT"

echo "[e16.3 host] Gate..."
"$PY" validation/zeroD/e16_3_gate.py
echo "E16.3 host done."
