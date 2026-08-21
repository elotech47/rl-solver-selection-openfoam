#!/usr/bin/env bash
# Build SUNDIALS (CVODE) into opt/sundials for native linux/amd64 (LONI QB).
# Does not require Docker.
#
#   bash tools/install_sundials.sh
#   SUNDIALS_VER=6.7.0 bash tools/install_sundials.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="${SUNDIALS_VER:-6.7.0}"
case "$(uname -m)" in
  aarch64|arm64) OUT="${SUNDIALS_DIR:-$ROOT/opt/sundials-arm64}" ;;
  *)             OUT="${SUNDIALS_DIR:-$ROOT/opt/sundials}" ;;
esac

if [[ -f "$OUT/include/cvode/cvode.h" ]]; then
  echo "SUNDIALS already at $OUT"
  exit 0
fi

# Prefer cmake from module if present
if ! command -v cmake >/dev/null 2>&1; then
  echo "cmake not found — try: module load cmake/3.27.7/gcc-8.5.0" >&2
  exit 1
fi

SRC_PARENT="${TMPDIR:-/tmp}"
SRC="$SRC_PARENT/sundials-${VER}"
BUILD="$SRC_PARENT/sundials-build-$$"

mkdir -p "$ROOT/opt" "$SRC_PARENT"
if [[ ! -d "$SRC" ]]; then
  echo "Downloading SUNDIALS ${VER}..."
  curl -fsSL -o "$SRC_PARENT/sundials-${VER}.tar.gz" \
    "https://github.com/LLNL/sundials/releases/download/v${VER}/sundials-${VER}.tar.gz" \
    || wget -q -O "$SRC_PARENT/sundials-${VER}.tar.gz" \
    "https://github.com/LLNL/sundials/releases/download/v${VER}/sundials-${VER}.tar.gz"
  tar xzf "$SRC_PARENT/sundials-${VER}.tar.gz" -C "$SRC_PARENT"
fi

echo "Building SUNDIALS ${VER} → $OUT"
rm -rf "$BUILD"
mkdir -p "$BUILD"
cd "$BUILD"
cmake "$SRC" \
  -DCMAKE_INSTALL_PREFIX="$OUT" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DENABLE_MPI=OFF \
  -DENABLE_OPENMP=OFF \
  -DEXAMPLES_ENABLE_C=OFF \
  -DEXAMPLES_INSTALL=OFF
cmake --build . -j"${NPROC:-$(nproc)}"
cmake --install .

test -f "$OUT/include/cvode/cvode.h"
echo "OK SUNDIALS_DIR=$OUT"
du -sh "$OUT"
