#!/usr/bin/env bash
# E16.5 host: rebuild rlChemistryModel, run fixed/synth MidT, gate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export DOCKER_HOST="${DOCKER_HOST:-unix:///Users/el0tech/.colima/default/docker.sock}"
PY="${PY:-/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python}"
export KMP_DUPLICATE_LIB_OK=TRUE

chmod +x validation/zeroD/e16_5_*.sh validation/zeroD/e16_5_*.py 2>/dev/null || true

# Ensure MidT IC exists
if [[ ! -f validation/e16_parity/e16_4_ics/C2_MidT_MidP_initialConditions ]]; then
  echo "[e16.5] writing ICs"
  "$PY" validation/zeroD/e16_4_write_ics.py --all
fi

echo "[e16.5] rebuild policyRuntime + rlChemistryModel"
docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work --memory=7g \
  opencfd/openfoam-default:2312 \
  -lc 'set +eu; source /usr/lib/openfoam/openfoam2312/etc/bashrc; set +u; set -e
       export WM_PROJECT_USER_DIR=/work FOAM_USER_LIBBIN=/work/platforms/${WM_OPTIONS}/lib
       export LIBTORCH_DIR=/work/opt/libtorch SUNDIALS_DIR=/work/opt/sundials-arm64
       export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$LIBTORCH_DIR/lib:$SUNDIALS_DIR/lib
       cd /work/src/policyRuntime && wmake libso
       cd /work/src/rlChemistryModel && wmake libso
       '

run_one() {
  local tag="$1" mode="$2"
  echo "===== E16.5 OF $tag ($mode) ====="
  docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work --memory=7g \
    opencfd/openfoam-default:2312 \
    -lc "bash /work/validation/zeroD/e16_5_run_one.sh $tag $mode"
}

run_one fixed_ref fixed
run_one fixed_ref_b fixed
run_one synth_irregular synth_irregular

echo "[e16.5] gate"
"$PY" validation/zeroD/e16_5_gate.py
echo "E16.5 host done."
