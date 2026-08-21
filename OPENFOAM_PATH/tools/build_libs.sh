#!/usr/bin/env bash
# Build custom chemistry libraries (run inside ESI OpenFOAM shell).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# WM_OPTIONS is linux64GccDPInt32Opt (x86_64) or linuxARM64GccDPInt32Opt (arm64)
PLAT="${WM_OPTIONS:-linux64GccDPInt32Opt}"
# Force bind-mount platforms/ (bashrc defaults to $HOME/OpenFOAM/user-*)
export WM_PROJECT_USER_DIR="$ROOT"
export FOAM_USER_LIBBIN="$ROOT/platforms/$PLAT/lib"
export FOAM_USER_APPBIN="$ROOT/platforms/$PLAT/bin"
if [[ "$PLAT" == linuxARM64* ]]; then
  export SUNDIALS_DIR="${SUNDIALS_DIR:-$ROOT/opt/sundials-arm64}"
else
  export SUNDIALS_DIR="${SUNDIALS_DIR:-$ROOT/opt/sundials}"
fi
mkdir -p "$FOAM_USER_LIBBIN" "$FOAM_USER_APPBIN"

echo "FOAM_USER_LIBBIN=$FOAM_USER_LIBBIN"
echo "SUNDIALS_DIR=$SUNDIALS_DIR"

(cd "$ROOT/src/ofRlInvariants" && wmake libso)
(cd "$ROOT/src/qssChemistrySolver" && wmake libso)

if [[ -f "$SUNDIALS_DIR/include/cvode/cvode.h" ]]; then
  export LD_LIBRARY_PATH="$SUNDIALS_DIR/lib:${LD_LIBRARY_PATH:-}"
  (cd "$ROOT/src/cvodeChemistrySolver" && wmake libso)
else
  echo "WARN: SUNDIALS not found at $SUNDIALS_DIR — skipping cvodeChemistrySolver"
fi

# LibTorch (optional for policyRuntime / rlChemistryModel)
# Prefer a valid tree under ROOT; ignore a stale LIBTORCH_DIR=/opt/libtorch from a bad env.
_lt_default="$ROOT/opt/libtorch"
if [[ -f "${LIBTORCH_DIR:-}/include/torch/script.h" ]]; then
  :
elif [[ -f "$_lt_default/include/torch/script.h" ]]; then
  export LIBTORCH_DIR="$_lt_default"
else
  export LIBTORCH_DIR="${LIBTORCH_DIR:-$_lt_default}"
fi
unset _lt_default
if [[ -f "$LIBTORCH_DIR/include/torch/script.h" ]]; then
  export LD_LIBRARY_PATH="$LIBTORCH_DIR/lib:${LD_LIBRARY_PATH:-}"
  echo "LIBTORCH_DIR=$LIBTORCH_DIR"
  (cd "$ROOT/src/policyRuntime" && wmake libso)
  (cd "$ROOT/src/rlChemistryModel" && wmake libso)
else
  echo "WARN: LibTorch not found at $LIBTORCH_DIR — skipping policyRuntime/rlChemistryModel"
  echo "      Expected: $ROOT/opt/libtorch  (headers + libtorch_cpu.so)"
fi

(cd "$ROOT/applications/solvers/chemFoam" && wmake)
(cd "$ROOT/applications/solvers/reactingFoam" && wmake)

ls -la "$FOAM_USER_LIBBIN"
ls -la "$FOAM_USER_APPBIN"/chemFoamDebug 2>/dev/null || true
ls -la "$FOAM_USER_APPBIN"/reactingFoamDebug 2>/dev/null || true
