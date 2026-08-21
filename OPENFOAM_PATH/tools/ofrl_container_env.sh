#!/usr/bin/env bash
# Shared env for Docker (/work) and native HPC after OpenFOAM bashrc.
# Do NOT use set -u here (LibTorch / OF unset vars).
#
# Usage:
#   export ROOT=/path/to/OPENFOAM_PATH   # optional; auto-detected if sourced
#   source tools/ofrl_container_env.sh
#
if [[ -z "${ROOT:-}" ]]; then
  # When sourced: BASH_SOURCE[0] is this file → OPENFOAM_PATH = parent of tools/
  _ofrl_src="${BASH_SOURCE[0]:-$0}"
  ROOT="$(cd "$(dirname "$_ofrl_src")/.." && pwd)"
  export ROOT
  unset _ofrl_src
fi

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

# RHEL/QB cmake often installs shared libs to lib64; Make/options uses -L$SUNDIALS_DIR/lib
if [[ -d "${SUNDIALS_DIR}/lib64" && ! -e "${SUNDIALS_DIR}/lib" ]]; then
  ln -sfn lib64 "${SUNDIALS_DIR}/lib"
elif [[ -d "${SUNDIALS_DIR}/lib64" && -d "${SUNDIALS_DIR}/lib" ]]; then
  # lib exists but may be empty — ensure cvode is visible
  if [[ ! -e "${SUNDIALS_DIR}/lib/libsundials_cvode.so" && -e "${SUNDIALS_DIR}/lib64/libsundials_cvode.so" ]]; then
    ln -sfn ../lib64/libsundials_*.so* "${SUNDIALS_DIR}/lib/" 2>/dev/null || true
  fi
fi

export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${SUNDIALS_DIR}/lib:${LIBTORCH_DIR}/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export TORCH_MKLDNN_ENABLED=0
export ATEN_NUM_THREADS=1

# Torch preload is required for reactingFoamDebug + rlAdaptive, but it often
# Aborts bare Foam utilities (checkMesh, decomposePar, reconstructPar, blockMesh).
# Keep the string in OFRL_TORCH_LD_PRELOAD; apply to LD_PRELOAD only when needed.
if [[ -f "${LIBTORCH_DIR}/lib/libtorch_cpu.so" ]]; then
  OFRL_TORCH_LD_PRELOAD="${LIBTORCH_DIR}/lib/libtorch_cpu.so:${LIBTORCH_DIR}/lib/libc10.so"
  OMPLIB="$(ls "${LIBTORCH_DIR}"/lib/libomp*.so 2>/dev/null | head -1 || true)"
  [[ -n "${OMPLIB}" ]] && OFRL_TORCH_LD_PRELOAD="${OFRL_TORCH_LD_PRELOAD}:${OMPLIB}"
  export OFRL_TORCH_LD_PRELOAD
  if [[ "${OFRL_TORCH_PRELOAD:-1}" == "1" ]]; then
    export LD_PRELOAD="${OFRL_TORCH_LD_PRELOAD}${LD_PRELOAD:+:$LD_PRELOAD}"
  fi
fi

export OFRL_PROP_SANITY=1
echo "ofrl env: ROOT=$ROOT SUNDIALS_DIR=$SUNDIALS_DIR LIBTORCH_DIR=$LIBTORCH_DIR"

# Parallel launch: LONI Slurm OpenMPI (Spack) stubs out mpirun — use srun in jobs.
ofrl_run_parallel() {
  local np="$1"
  shift
  if [[ -n "${SLURM_JOB_ID:-}" ]] && command -v srun >/dev/null 2>&1; then
    echo "ofrl_mpi: srun -n ${np} $*"
    # Prefer TCP/shared-memory on-node; mlx5 OpenFabrics often warns/fails on QB
    OMPI_MCA_btl="${OMPI_MCA_btl:-self,vader,tcp}" \
    OMPI_MCA_pml="${OMPI_MCA_pml:-ob1}" \
    srun -n "${np}" "$@"
  elif [[ "${OF_RUNTIME:-}" == "docker" ]]; then
    mpirun --allow-run-as-root -np "${np}" --map-by core --bind-to core "$@"
  else
    # Prefer real mpirun; fail loudly on Spack stub
    if command -v mpirun >/dev/null 2>&1; then
      local _help
      _help="$(mpirun --help 2>&1 | head -5 || true)"
      if printf '%s' "$_help" | grep -q 'without the mpiexec/mpirun'; then
        echo "FATAL: mpirun is a Spack/Slurm stub — run under sbatch/srun or load a full OpenMPI module" >&2
        return 127
      fi
      mpirun -np "${np}" "$@"
    else
      echo "FATAL: neither srun nor mpirun found" >&2
      return 127
    fi
  fi
}
export -f ofrl_run_parallel
