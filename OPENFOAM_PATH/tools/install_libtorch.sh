#!/usr/bin/env bash
# Install LibTorch CPU into opt/libtorch (ABI=0, matches policyRuntime Make/options).
#
# Prefer native pip (HPC / no Docker). Optional Docker path if docker is available.
#
#   bash tools/install_libtorch.sh
#   TORCH_VER=2.2.2 bash tools/install_libtorch.sh
#   LIBTORCH_USE_DOCKER=1 bash tools/install_libtorch.sh   # old path
#
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

have_libtorch() {
  [[ -f "$OUT/include/torch/script.h" && -f "$OUT/lib/libtorch_cpu.so" ]]
}

if have_libtorch; then
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

install_from_python() {
  local py="${LIBTORCH_PYTHON:-}"
  if [[ -z "$py" ]]; then
    if command -v python3 >/dev/null 2>&1; then py=python3
    elif command -v python >/dev/null 2>&1; then py=python
    else return 1
    fi
  fi
  echo "[libtorch] native pip via $py (CPU wheel, ABI=0)"
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/libtorch_pip.XXXXXX")"
  # Isolate install so we do not touch the user's conda env packages permanently
  "$py" -m pip install -q --upgrade pip
  "$py" -m pip install -q --no-cache-dir \
    --target "$tmp/site" \
    "torch==${TORCH_VER}" \
    --index-url https://download.pytorch.org/whl/cpu

  local site
  site="$("$py" - <<PY
import glob, os
cands = glob.glob("$tmp/site/torch")
assert cands, "torch package missing under $tmp/site"
print(cands[0])
PY
)"
  rm -rf "$OUT"
  mkdir -p "$OUT/lib"
  cp -a "$site/include" "$OUT/"
  cp -a "$site/lib"/*.so* "$OUT/lib/" 2>/dev/null || \
    cp -a "$site"/lib/*.so* "$OUT/lib/"
  # Some wheels nest libs under torch/lib
  if [[ ! -f "$OUT/lib/libtorch_cpu.so" && -d "$site/lib" ]]; then
    find "$site" -name 'libtorch_cpu.so' -exec cp -a {} "$OUT/lib/" \;
    find "$site" -name 'libc10.so' -exec cp -a {} "$OUT/lib/" \;
    find "$site" -name 'libtorch.so' -exec cp -a {} "$OUT/lib/" \;
    find "$site" -name 'libgomp*.so*' -exec cp -a {} "$OUT/lib/" \;
    find "$site" -name 'libomp*.so*' -exec cp -a {} "$OUT/lib/" \;
  fi
  # Copy all .so from torch/lib if still missing
  if [[ ! -f "$OUT/lib/libtorch_cpu.so" ]]; then
    local tlib="$site/lib"
    [[ -d "$tlib" ]] || tlib="$(dirname "$site")/torch/lib"
    cp -a "$tlib"/*.so* "$OUT/lib/"
  fi
  test -f "$OUT/include/torch/script.h"
  test -f "$OUT/lib/libtorch_cpu.so"
  file "$OUT/lib/libtorch_cpu.so"
  du -sh "$OUT"
  rm -rf "$tmp"
}

install_from_zip() {
  # Official prebuilt (pre-cxx11 ABI = 0). Prefer when pip is broken.
  local ver="$TORCH_VER"
  local url zip
  case "$PLATFORM" in
    linux/amd64)
      url="https://download.pytorch.org/libtorch/cpu/libtorch-shared-with-deps-${ver}%2Bcpu.zip"
      ;;
    linux/arm64)
      echo "No official arm64 libtorch zip for ${ver}; use pip path" >&2
      return 1
      ;;
    *) return 1 ;;
  esac
  echo "[libtorch] downloading $url"
  zip="$(mktemp "${TMPDIR:-/tmp}/libtorch.XXXXXX.zip")"
  if command -v wget >/dev/null 2>&1; then
    wget -q -O "$zip" "$url"
  else
    curl -fsSL -o "$zip" "$url"
  fi
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/libtorch_zip.XXXXXX")"
  unzip -q "$zip" -d "$tmp"
  rm -f "$zip"
  rm -rf "$OUT"
  mv "$tmp/libtorch" "$OUT"
  rm -rf "$tmp"
  test -f "$OUT/include/torch/script.h"
  test -f "$OUT/lib/libtorch_cpu.so"
  file "$OUT/lib/libtorch_cpu.so"
  du -sh "$OUT"
}

install_from_docker() {
  command -v docker >/dev/null 2>&1 || return 1
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
}

if [[ "${LIBTORCH_USE_DOCKER:-0}" == "1" ]]; then
  install_from_docker || { echo "Docker install failed" >&2; exit 1; }
elif install_from_python; then
  :
elif install_from_zip; then
  :
elif install_from_docker; then
  :
else
  echo "FATAL: could not install LibTorch (no working pip/zip/docker)" >&2
  exit 1
fi

echo "Installed $OUT for $PLATFORM"
