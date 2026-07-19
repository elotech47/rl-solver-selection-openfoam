#!/bin/bash
# Rebuild SUNDIALS 6.7 (arm64) + OF user libs/apps after platforms wipe.
# Usage (host):
#   docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
#     -v "$PWD:/work" -w /work opencfd/openfoam-default:2312 \
#     -lc 'bash /work/tools/recover_platforms.sh'
set +e
echo "=== recover_platforms: start ==="
ROOT="${ROOT:-/work}"
export SUNDIALS_DIR="$ROOT/opt/sundials-arm64"
VER=6.7.0
SRC="/tmp/sundials-${VER}"

# OF bashrc references optional unset vars and may return nonzero — never abort here
set +u
source /usr/lib/openfoam/openfoam2312/etc/bashrc
SRC_RC=$?
echo "bashrc sourced rc=$SRC_RC WM_OPTIONS=${WM_OPTIONS:-UNSET}"
if [ -z "${WM_OPTIONS:-}" ]; then
  echo "FATAL: WM_OPTIONS unset after bashrc"
  exit 1
fi

export WM_PROJECT_USER_DIR="$ROOT"
export FOAM_USER_LIBBIN="$ROOT/platforms/${WM_OPTIONS}/lib"
export FOAM_USER_APPBIN="$ROOT/platforms/${WM_OPTIONS}/bin"
mkdir -p "$FOAM_USER_LIBBIN" "$FOAM_USER_APPBIN" "$ROOT/opt"
echo "FOAM_USER_APPBIN=$FOAM_USER_APPBIN"

set -e

if [ ! -f "$SUNDIALS_DIR/include/cvode/cvode.h" ]; then
  echo "=== Installing cmake / curl ==="
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq cmake curl ca-certificates
  echo "cmake=$(command -v cmake)"
  echo "=== Building SUNDIALS ${VER} → $SUNDIALS_DIR ==="
  cd /tmp
  if [ ! -d "$SRC" ]; then
    curl -fsSL -o "sundials-${VER}.tar.gz" \
      "https://github.com/LLNL/sundials/releases/download/v${VER}/sundials-${VER}.tar.gz"
    tar xzf "sundials-${VER}.tar.gz"
  fi
  rm -rf /tmp/sundials-build
  mkdir -p /tmp/sundials-build
  cd /tmp/sundials-build
  cmake "$SRC" \
    -DCMAKE_INSTALL_PREFIX="$SUNDIALS_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_STATIC_LIBS=OFF \
    -DENABLE_MPI=OFF \
    -DENABLE_OPENMP=OFF \
    -DEXAMPLES_ENABLE_C=OFF \
    -DEXAMPLES_ENABLE_CXX=OFF \
    -DEXAMPLES_INSTALL=OFF
  NJOBS=$(nproc 2>/dev/null || echo 4)
  cmake --build . -j"$NJOBS"
  cmake --install .
else
  echo "SUNDIALS already present at $SUNDIALS_DIR"
fi

export SUNDIALS_DIR
export LD_LIBRARY_PATH="$SUNDIALS_DIR/lib:${LD_LIBRARY_PATH:-}"
echo "=== build_libs.sh ==="
bash "$ROOT/tools/build_libs.sh"
echo "=== verifying binaries ==="
ls -la "$FOAM_USER_APPBIN/chemFoamDebug"
ls -la "$FOAM_USER_LIBBIN"/libqssChemistrySolver.so \
       "$FOAM_USER_LIBBIN"/libcvodeChemistrySolver.so \
       "$FOAM_USER_LIBBIN"/libofRlInvariants.so
echo "RECOVERY OK"
