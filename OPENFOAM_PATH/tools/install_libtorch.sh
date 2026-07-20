#!/usr/bin/env bash
# Install LibTorch CPU from the official torch wheel into opt/libtorch.
# Default platform follows host arch; override with OF_PLATFORM=linux/amd64|linux/arm64.
# pip torch wheels use _GLIBCXX_USE_CXX11_ABI=0 — match in policyRuntime/rlChemistryModel Make/options.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/opt/libtorch"
PLATFORM="${OF_PLATFORM:-}"
if [[ -z "$PLATFORM" ]]; then
  case "$(uname -m)" in
    x86_64|amd64) PLATFORM=linux/amd64 ;;
    aarch64|arm64) PLATFORM=linux/arm64 ;;
    *) echo "Unknown arch $(uname -m); set OF_PLATFORM=linux/amd64|linux/arm64"; exit 2 ;;
  esac
fi
TORCH_VER="${TORCH_VER:-2.2.2}"

if [[ -f "$OUT/include/torch/script.h" && -f "$OUT/lib/libtorch_cpu.so" ]]; then
  # Refuse to reuse a wrong-ISA tree
  if file "$OUT/lib/libtorch_cpu.so" | grep -q "ARM aarch64" && [[ "$PLATFORM" == linux/amd64 ]]; then
    echo "Removing arm64 LibTorch so amd64 can be installed"
    rm -rf "$OUT"
  elif file "$OUT/lib/libtorch_cpu.so" | grep -q "x86-64" && [[ "$PLATFORM" == linux/arm64 ]]; then
    echo "Removing amd64 LibTorch so arm64 can be installed"
    rm -rf "$OUT"
  else
    echo "LibTorch already present at $OUT ($(file -b "$OUT/lib/libtorch_cpu.so" | cut -d, -f1))"
    exit 0
  fi
fi

mkdir -p "$ROOT/opt"
echo "[libtorch] installing torch==$TORCH_VER for $PLATFORM → $OUT"
docker run --rm --platform="$PLATFORM" \
  -v "$ROOT/opt:/out" \
  python:3.11-slim-bookworm \
  bash -lc "
    set -e
    apt-get update -qq && apt-get install -y -qq libgomp1 file >/dev/null
    pip install -q --no-cache-dir torch==${TORCH_VER} --index-url https://download.pytorch.org/whl/cpu
    SITE=\$(python -c \"import torch, pathlib; print(pathlib.Path(torch.__file__).parent)\")
    rm -rf /out/libtorch
    mkdir -p /out/libtorch/lib
    cp -a \"\$SITE/include\" /out/libtorch/
    cp -a \"\$SITE/lib\"/*.so* /out/libtorch/lib/
    test -f /out/libtorch/include/torch/script.h
    file /out/libtorch/lib/libtorch_cpu.so
    du -sh /out/libtorch
  "
echo "Installed $OUT for $PLATFORM"
