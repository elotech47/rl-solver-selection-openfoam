#!/bin/bash
# ============================================================
# macOS environment for PelePhysics / PeleLMeX local dev
# Usage: source setup_env_mac.sh
#
# Note: do NOT export PELE_PHYSICS_HOME / PELE_HOME before make.
# Each Exec GNUmakefile sets those relative paths itself.
# ============================================================

# Repo root (zsh/bash compatible when sourced)
if [[ -n "${BASH_VERSION:-}" && -n "${BASH_SOURCE[0]:-}" ]]; then
  _SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
elif [[ -n "${ZSH_VERSION:-}" ]]; then
  _SETUP_DIR="$(cd "$(dirname "${(%):-%x}")" && pwd)"
else
  _SETUP_DIR="$(cd "$(dirname "$0")" && pwd)"
fi

export SOLVER_SELECTION_HOME="${_SETUP_DIR}"
unset _SETUP_DIR

# Homebrew toolchain (Apple Silicon default prefix)
if [[ -d /opt/homebrew/bin ]]; then
  export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:${PATH}"
fi

# Pele recommends COMP=llvm on macOS
export COMP=llvm

# Optional: Homebrew GCC if you prefer COMP=gnu
# export CC=gcc-16
# export CXX=g++-16
# export COMP=gnu

# OpenMP (keg-only on Homebrew)
if [[ -d /opt/homebrew/opt/libomp ]]; then
  export LDFLAGS="-L/opt/homebrew/opt/libomp/lib ${LDFLAGS:-}"
  export CPPFLAGS="-I/opt/homebrew/opt/libomp/include ${CPPFLAGS:-}"
fi

echo "============================================"
echo " Pele macOS dev environment"
echo "============================================"
echo "  SOLVER_SELECTION = ${SOLVER_SELECTION_HOME}"
echo "  COMP             = ${COMP}"
echo "  clang++          = $(command -v clang++ || echo missing)"
echo "  cmake            = $(cmake --version 2>/dev/null | head -1 || echo missing)"
echo "  mpicxx           = $(command -v mpicxx || echo optional)"
echo "============================================"
echo "Quick test build:"
echo "  cd PelePhysics/Testing/Exec/ReactEval"
echo "  make TPL USE_MPI=FALSE && make -j4 USE_MPI=FALSE"
echo "  ./Pele2d.gnu.ex inputs.qss_smoke"
echo "============================================"
