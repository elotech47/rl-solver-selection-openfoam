#!/usr/bin/env bash
# Build custom chemistry libraries (run inside ESI OpenFOAM shell).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# WM_OPTIONS is linux64GccDPInt32Opt (x86_64) or linuxARM64GccDPInt32Opt (arm64)
PLAT="${WM_OPTIONS:-linux64GccDPInt32Opt}"
export FOAM_USER_LIBBIN="${FOAM_USER_LIBBIN:-$ROOT/platforms/$PLAT/lib}"
export FOAM_USER_APPBIN="${FOAM_USER_APPBIN:-$ROOT/platforms/$PLAT/bin}"
export WM_PROJECT_USER_DIR="${WM_PROJECT_USER_DIR:-$ROOT}"
if [[ "$PLAT" == linuxARM64* ]]; then
  export SUNDIALS_DIR="${SUNDIALS_DIR:-$ROOT/opt/sundials-arm64}"
else
  export SUNDIALS_DIR="${SUNDIALS_DIR:-$ROOT/opt/sundials}"
fi
mkdir -p "$FOAM_USER_LIBBIN" "$FOAM_USER_APPBIN"

echo "FOAM_USER_LIBBIN=$FOAM_USER_LIBBIN"
echo "SUNDIALS_DIR=$SUNDIALS_DIR"

(cd "$ROOT/src/qssChemistrySolver" && wmake libso)

if [[ -f "$SUNDIALS_DIR/include/cvode/cvode.h" ]]; then
  export LD_LIBRARY_PATH="$SUNDIALS_DIR/lib:${LD_LIBRARY_PATH:-}"
  (cd "$ROOT/src/cvodeChemistrySolver" && wmake libso)
else
  echo "WARN: SUNDIALS not found at $SUNDIALS_DIR — skipping cvodeChemistrySolver"
fi

ls -la "$FOAM_USER_LIBBIN"
