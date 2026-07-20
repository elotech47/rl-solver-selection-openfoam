#!/usr/bin/env bash
# Shared container env for E16/E17 x86_64 (auto-detect SUNDIALS + LibTorch preload).
# Source from inside-container scripts after bashrc. Do NOT use set -u here.
: "${ROOT:?ROOT must be set}"

export WM_PROJECT_USER_DIR="${ROOT}"
export FOAM_USER_LIBBIN="${ROOT}/platforms/${WM_OPTIONS}/lib"
export FOAM_USER_APPBIN="${ROOT}/platforms/${WM_OPTIONS}/bin"
export LIBTORCH_DIR="${LIBTORCH_DIR:-${ROOT}/opt/libtorch}"

if [[ -f "${ROOT}/opt/sundials/include/cvode/cvode.h" ]]; then
  export SUNDIALS_DIR="${ROOT}/opt/sundials"
elif [[ -f "${ROOT}/opt/sundials-arm64/include/cvode/cvode.h" ]]; then
  export SUNDIALS_DIR="${ROOT}/opt/sundials-arm64"
else
  export SUNDIALS_DIR="${SUNDIALS_DIR:-${ROOT}/opt/sundials}"
fi

export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${SUNDIALS_DIR}/lib:${LIBTORCH_DIR}/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export TORCH_MKLDNN_ENABLED=0
export ATEN_NUM_THREADS=1

if [[ -f "${LIBTORCH_DIR}/lib/libtorch_cpu.so" ]]; then
  export LD_PRELOAD="${LIBTORCH_DIR}/lib/libtorch_cpu.so:${LIBTORCH_DIR}/lib/libc10.so"
  OMPLIB="$(ls "${LIBTORCH_DIR}"/lib/libomp*.so 2>/dev/null | head -1 || true)"
  [[ -n "${OMPLIB}" ]] && export LD_PRELOAD="${LD_PRELOAD}:${OMPLIB}"
fi

export OFRL_PROP_SANITY=1
