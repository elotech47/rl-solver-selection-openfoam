#!/usr/bin/env bash
# Build Foam-free policy worker (ABI=0 LibTorch — OK on RHEL8 glibc 2.28).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIBTORCH_DIR="${LIBTORCH_DIR:-$ROOT/opt/libtorch}"
BIN="$ROOT/opt/bin/ofrl_policy_worker"
mkdir -p "$ROOT/opt/bin"

test -f "$LIBTORCH_DIR/lib/libtorch_cpu.so" || {
  echo "FATAL: no LibTorch at $LIBTORCH_DIR — use ABI=0 install:" >&2
  echo "  LIBTORCH_FORCE=1 LIBTORCH_CXX11_ABI=0 bash tools/install_libtorch.sh" >&2
  exit 1
}

CXX="${CXX:-g++}"
echo "building $BIN (ABI=0) with $CXX"
"$CXX" -O2 -std=c++17 -D_GLIBCXX_USE_CXX11_ABI=0 \
  -I"$LIBTORCH_DIR/include" \
  -I"$LIBTORCH_DIR/include/torch/csrc/api/include" \
  "$ROOT/tools/ofrl_policy_worker.cpp" -o "$BIN" \
  -L"$LIBTORCH_DIR/lib" -Wl,-rpath,"$LIBTORCH_DIR/lib" \
  -ltorch -ltorch_cpu -lc10

echo "OK $BIN"
# quick load test if policy exists
if [[ -f "$ROOT/policy/policy.ts" ]]; then
  echo "smoke-load: printf quit | …"
  # send QUIT magic
  python3 - <<PY
import struct, subprocess, sys
p = subprocess.Popen(
    ["$BIN", "$ROOT/policy/policy.ts"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
ready = p.stdout.readline()
assert ready.strip() == b"READY", ready
p.stdin.write(struct.pack("<I", 0xFFFFFFFF))
p.stdin.flush()
rc = p.wait(timeout=60)
print("worker_exit", rc, "ready", ready)
sys.exit(0 if rc == 0 else 1)
PY
fi
