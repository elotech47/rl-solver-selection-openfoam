#!/usr/bin/env bash
# Install LibTorch (Linux aarch64) from the official torch wheel into opt/libtorch.
# NOTE: pip torch wheels use _GLIBCXX_USE_CXX11_ABI=0. Compile policyRuntime /
# rlChemistryModel with the same flag (see Make/options).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/opt/libtorch"
if [[ -f "$OUT/include/torch/script.h" && -f "$OUT/lib/libtorch_cpu.so" ]]; then
  echo "LibTorch already present at $OUT"
  exit 0
fi
export DOCKER_HOST="${DOCKER_HOST:-unix:///Users/el0tech/.colima/default/docker.sock}"
mkdir -p "$ROOT/opt"
docker run --rm --platform=linux/arm64 \
  -v "$ROOT/opt:/out" \
  python:3.11-slim-bookworm \
  bash -lc '
    set -e
    apt-get update -qq && apt-get install -y -qq libgomp1 >/dev/null
    pip install -q --no-cache-dir torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
    SITE=$(python -c "import torch, pathlib; print(pathlib.Path(torch.__file__).parent)")
    rm -rf /out/libtorch
    mkdir -p /out/libtorch/lib
    cp -a "$SITE/include" /out/libtorch/
    cp -a "$SITE/lib"/*.so* /out/libtorch/lib/
    test -f /out/libtorch/include/torch/script.h
    du -sh /out/libtorch
  '
echo "Installed $OUT"
