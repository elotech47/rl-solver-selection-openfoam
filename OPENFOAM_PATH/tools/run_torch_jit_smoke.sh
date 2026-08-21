#!/usr/bin/env bash
# Build + run a Foam-free LibTorch JIT load of policy.ts (isolates ABI/SIGFPE from OF).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/tools/ofrl_container_env.sh" 2>/dev/null || true
LIBTORCH_DIR="${LIBTORCH_DIR:-$ROOT/opt/libtorch}"
POLICY="${1:-$ROOT/policy/policy.ts}"
BIN="$ROOT/opt/bin/torch_jit_smoke"
mkdir -p "$ROOT/opt/bin"

test -f "$LIBTORCH_DIR/lib/libtorch_cpu.so" || {
  echo "FATAL: no LibTorch at $LIBTORCH_DIR" >&2
  exit 1
}
test -f "$POLICY" || {
  echo "FATAL: missing $POLICY" >&2
  exit 1
}

CXX="${CXX:-g++}"
echo "building $BIN with $CXX (ABI=0)"
"$CXX" -O2 -std=c++17 -D_GLIBCXX_USE_CXX11_ABI=0 \
  -I"$LIBTORCH_DIR/include" \
  -I"$LIBTORCH_DIR/include/torch/csrc/api/include" \
  "$ROOT/tools/torch_jit_smoke.cpp" -o "$BIN" \
  -L"$LIBTORCH_DIR/lib" -Wl,-rpath,"$LIBTORCH_DIR/lib" \
  -ltorch -ltorch_cpu -lc10

unset FOAM_SIGFPE
unset LD_PRELOAD
echo "running: env -u FOAM_SIGFPE -u LD_PRELOAD $BIN $POLICY"
env -u FOAM_SIGFPE -u LD_PRELOAD "$BIN" "$POLICY"
