#!/usr/bin/env bash
# Queen Bee (LONI) — one command to load the full OF-RL stack.
#
# Usage (interactive or at top of every sbatch):
#   source /work/elo/solverRL2D/rl-solver-selection-openfoam/OPENFOAM_PATH/production/env.qb.sh
#
# Or from OPENFOAM_PATH:
#   source production/env.qb.sh
#
# One-time installs (OF, LibTorch, SUNDIALS, wmake) are separate — see
# production/cluster/INSTALL_OF2312.md

# Resolve OPENFOAM_PATH even when sourced
_ofrl_qb_src="${BASH_SOURCE[0]:-$0}"
_OFRL_PROD="$(cd "$(dirname "$_ofrl_qb_src")" && pwd)"
export ROOT="$(cd "$_OFRL_PROD/.." && pwd)"
unset _ofrl_qb_src _OFRL_PROD

# --- site defaults (override before sourcing if needed) ---
export OF_RUNTIME=native
export OF_BASHRC="${OF_BASHRC:-/work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc}"
export SLURM_ACCOUNT="${SLURM_ACCOUNT:-loni_pca_dns}"
export NPROC="${NPROC:-${SLURM_NTASKS:-32}}"
export E18_END_TIME="${E18_END_TIME:-0.009}"
export E18_WRITE_INTERVAL="${E18_WRITE_INTERVAL:-1e-05}"
export E18_MODES="${E18_MODES:-cvodeOnly}"
# Policy/manifest paths in chemistryProperties must be host paths on native
export E17_CONTAINER_ROOT="${E17_CONTAINER_ROOT:-$ROOT}"

# --- modules matching the OF-v2312 build ---
if command -v module >/dev/null 2>&1; then
  module purge 2>/dev/null || true
  module load gcc/13.2.0
  module load openmpi/4.0.3/intel-19.0.5
  module load cmake/3.27.7/gcc-8.5.0 2>/dev/null || true
fi

if [[ ! -f "$OF_BASHRC" ]]; then
  echo "FATAL: OF_BASHRC not found: $OF_BASHRC" >&2
  return 1 2>/dev/null || exit 1
fi

# OpenFOAM bashrc trips set -e / unset vars
set +eu
# shellcheck disable=SC1090
source "$OF_BASHRC"
set +u

# shellcheck disable=SC1091
source "$ROOT/tools/ofrl_container_env.sh"
set +u

# Ensure sundials lib → lib64 symlink (QB cmake layout)
if [[ -d "$ROOT/opt/sundials/lib64" && ! -e "$ROOT/opt/sundials/lib" ]]; then
  ln -sfn lib64 "$ROOT/opt/sundials/lib"
fi

export LIBTORCH_DIR="${LIBTORCH_DIR:-$ROOT/opt/libtorch}"
export SUNDIALS_DIR="${SUNDIALS_DIR:-$ROOT/opt/sundials}"

# Sanity (non-fatal for interactive)
if [[ ! -x "$(command -v reactingFoamDebug 2>/dev/null || true)" ]]; then
  if [[ -x "$ROOT/platforms/${WM_OPTIONS}/bin/reactingFoamDebug" ]]; then
    export PATH="$ROOT/platforms/${WM_OPTIONS}/bin:$PATH"
  else
    echo "WARN: reactingFoamDebug not on PATH — build: cd $ROOT/applications/solvers/reactingFoam && wmake -j8" >&2
  fi
fi

echo "env.qb.sh OK  ROOT=$ROOT  WM_OPTIONS=${WM_OPTIONS:-?}  NPROC=$NPROC  OF_RUNTIME=$OF_RUNTIME"
command -v reactingFoamDebug >/dev/null && echo "  reactingFoamDebug=$(command -v reactingFoamDebug)"
