#!/usr/bin/env bash
# E17 remote bootstrap: Docker OF image + SUNDIALS/LibTorch + wmake user stack.
# Run from OPENFOAM_PATH on a linux/amd64 host.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export DOCKER_HOST="${DOCKER_HOST:-unix:///var/run/docker.sock}"
IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
PLATFORM="${OF_PLATFORM:-linux/amd64}"

echo "[e17 bootstrap] ROOT=$ROOT"
echo "[e17 bootstrap] pulling $IMAGE ($PLATFORM)"
docker pull --platform="$PLATFORM" "$IMAGE"

# Host Python deps for kernel IC + extract/preprocess (Cantera preferred for Z→Y)
echo "[e17 bootstrap] ensuring host Python deps (cantera, numpy, matplotlib)"
# Prefer pip: conda-forge cantera often conflicts with base env (python/mamba/fmt pins).
if command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1; then
  pip3 install --quiet 'cantera>=3.0' numpy matplotlib 2>/dev/null \
    || pip install --quiet 'cantera>=3.0' numpy matplotlib
elif command -v conda >/dev/null 2>&1; then
  conda create -y -n ofrl-e17 -c conda-forge python=3.11 cantera numpy matplotlib \
    && echo "INFO: activate with: conda activate ofrl-e17"
else
  echo "WARN: no pip/conda — install cantera manually for accurate hot-kernel Y"
fi
python3 -c "import cantera as ct; print('[e17 bootstrap] cantera', ct.__version__)" \
  || echo "WARN: cantera import failed — kernel will use mass-fraction fallback"

# Prefer building SUNDIALS inside a one-shot container into opt/sundials if missing
if [[ ! -f "$ROOT/opt/sundials/include/cvode/cvode.h" ]]; then
  echo "[e17 bootstrap] building SUNDIALS into opt/sundials (first time)"
  mkdir -p "$ROOT/opt"
  docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work \
    "$IMAGE" \
    -lc 'set -e
         apt-get update -qq && apt-get install -y -qq build-essential cmake wget ca-certificates >/dev/null
         cd /tmp
         wget -q https://github.com/LLNL/sundials/releases/download/v6.7.0/sundials-6.7.0.tar.gz
         tar xf sundials-6.7.0.tar.gz
         cmake -S sundials-6.7.0 -B build-sundials \
           -DCMAKE_INSTALL_PREFIX=/work/opt/sundials \
           -DBUILD_SHARED_LIBS=ON -DENABLE_OPENMP=OFF -DEXAMPLES_ENABLE_C=OFF
         cmake --build build-sundials -j"$(nproc)"
         cmake --install build-sundials
         '
fi

# LibTorch (needed for rlAdaptive; optional for cvodeOnly scout)
if [[ ! -f "$ROOT/opt/libtorch/include/torch/script.h" ]]; then
  if [[ -f "$ROOT/tools/install_libtorch.sh" ]]; then
    echo "[e17 bootstrap] installing LibTorch via tools/install_libtorch.sh"
    bash "$ROOT/tools/install_libtorch.sh" || echo "WARN: LibTorch install failed — cvodeOnly still OK"
  else
    echo "WARN: no LibTorch and no tools/install_libtorch.sh — rlAdaptive will not build"
  fi
fi

echo "[e17 bootstrap] wmake user libs + reactingFoamDebug"
docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  -e SUNDIALS_DIR=/work/opt/sundials \
  -e LIBTORCH_DIR=/work/opt/libtorch \
  "$IMAGE" \
  -lc 'set +eu; source /usr/lib/openfoam/openfoam2312/etc/bashrc; set +u; set -e
       export WM_PROJECT_USER_DIR=/work
       export FOAM_USER_LIBBIN=/work/platforms/${WM_OPTIONS}/lib
       export FOAM_USER_APPBIN=/work/platforms/${WM_OPTIONS}/bin
       export SUNDIALS_DIR=/work/opt/sundials
       export LIBTORCH_DIR=/work/opt/libtorch
       export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$SUNDIALS_DIR/lib:$LIBTORCH_DIR/lib:${LD_LIBRARY_PATH:-}
       bash /work/tools/build_libs.sh
       cd /work/applications/solvers/reactingFoam && wmake -j "$(nproc)"
       ls -la /work/platforms/*/bin/reactingFoamDebug
       ls -la /work/platforms/*/lib/lib{cvode,qss,rl,policy}* 2>/dev/null || true
       '

echo "[e17 bootstrap] DONE"
echo "Next: export NPROC=16; bash validation/zeroD/e17_remote/01_run_ignition_scout.sh"
