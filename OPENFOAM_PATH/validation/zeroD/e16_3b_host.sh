#!/usr/bin/env bash
# E16.3b host orchestrator.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export DOCKER_HOST="${DOCKER_HOST:-unix:///Users/el0tech/.colima/default/docker.sock}"
PY="${PY:-/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python}"
export KMP_DUPLICATE_LIB_OK=TRUE
OUT="$ROOT/validation/e16_parity/e16_3b_runs"
mkdir -p "$OUT"

echo "[e16.3b] rebuild"
chmod +x tools/build_e16_3b_teacher_forced.sh validation/zeroD/e16_3b_*.sh
bash tools/build_e16_3b_teacher_forced.sh
docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work --memory=7g \
  opencfd/openfoam-default:2312 \
  -lc 'set +eu; source /usr/lib/openfoam/openfoam2312/etc/bashrc; set +u; set -e
       export WM_PROJECT_USER_DIR=/work FOAM_USER_LIBBIN=/work/platforms/${WM_OPTIONS}/lib
       export LIBTORCH_DIR=/work/opt/libtorch SUNDIALS_DIR=/work/opt/sundials-arm64
       export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$LIBTORCH_DIR/lib:$SUNDIALS_DIR/lib
       cd /work/src/rlChemistryModel && wmake libso
       '

echo "[e16.3b] Python extended refs + tapes"
"$PY" validation/zeroD/e16_3b_python_ref.py --label both

echo "[e16.3b] Teacher-forced"
bash validation/zeroD/e16_3b_teacher_forced_run.sh

echo "[e16.3b] OF free-run (MidT 3.4 ms, NTC 8 ms)"
for spec in "MidT 800 10 1.0 0.0034" "NTC 700 10 1.0 0.008"; do
  # shellcheck disable=SC2086
  set -- $spec
  for mode in rlAdaptive cvodeOnly; do
    echo "===== OF $1 $mode ====="
    docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
      -v "$ROOT:/work" -w /work --memory=7g \
      opencfd/openfoam-default:2312 \
      -lc "bash /work/validation/zeroD/e16_3_run_one.sh $1 $2 $3 $4 $5 $mode"
    src="$ROOT/validation/e16_parity/e16_3_runs/${1}_${mode}"
    dst="$OUT/${1}_${mode}"
    rm -rf "$dst"
    if [[ -d "$src" ]]; then mv "$src" "$dst"; fi
  done
done

echo "[e16.3b] plots + gate"
"$PY" validation/zeroD/e16_3b_plot_progress.py
"$PY" validation/zeroD/e16_3b_gate.py
echo "E16.3b host done."
