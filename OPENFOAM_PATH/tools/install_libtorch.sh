#!/usr/bin/env bash
# Install LibTorch CPU into opt/libtorch.
#
# Native OpenFOAM (gcc, default) needs **cxx11 ABI=1**. Pre-cxx11 ABI=0 wheels/zips
# crash inside Foam at torch::jit::load (Foam::newError / old std::string Ss).
#
#   bash tools/install_libtorch.sh
#   LIBTORCH_FORCE=1 bash tools/install_libtorch.sh          # replace existing
#   LIBTORCH_CXX11_ABI=0 bash tools/install_libtorch.sh      # Docker/old path only
#   TORCH_VER=2.2.2 bash tools/install_libtorch.sh
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
# RHEL8 / glibc 2.28 cannot use official cxx11-abi zips (need GLIBC_2.29).
# Default ABI=0 (pip / pre-cxx11 zip) on old glibc; cxx11 only when glibc >= 2.29.
_glibc_minor="$(ldd --version 2>/dev/null | head -1 | sed -n 's/.* \([0-9]\+\)\.\([0-9]\+\)$/\2/p' || true)"
if [[ -z "${LIBTORCH_CXX11_ABI:-}" ]]; then
  if [[ "${_glibc_minor:-0}" -ge 29 ]]; then
    LIBTORCH_CXX11_ABI=1
  else
    LIBTORCH_CXX11_ABI=0
    echo "[libtorch] glibc minor=${_glibc_minor:-?} < 29 → ABI=0 (use OFRL_POLICY_WORKER for Foam RL)"
  fi
fi

have_libtorch() {
  [[ -f "$OUT/include/torch/script.h" && -f "$OUT/lib/libtorch_cpu.so" ]]
}

if have_libtorch && [[ "${LIBTORCH_FORCE:-0}" != "1" ]]; then
  if file "$OUT/lib/libtorch_cpu.so" | grep -q "ARM aarch64" && [[ "$PLATFORM" == linux/amd64 ]]; then
    echo "Removing arm64 LibTorch so amd64 can be installed"
    rm -rf "$OUT"
  elif file "$OUT/lib/libtorch_cpu.so" | grep -q "x86-64" && [[ "$PLATFORM" == linux/arm64 ]]; then
    echo "Removing amd64 LibTorch so arm64 can be installed"
    rm -rf "$OUT"
  else
    echo "LibTorch already present at $OUT ($(file -b "$OUT/lib/libtorch_cpu.so" | cut -d, -f1))"
    echo "  Reinstall with: LIBTORCH_FORCE=1 LIBTORCH_CXX11_ABI=${LIBTORCH_CXX11_ABI} bash tools/install_libtorch.sh"
    exit 0
  fi
fi

if [[ "${LIBTORCH_FORCE:-0}" == "1" ]]; then
  rm -rf "$OUT"
fi

mkdir -p "$ROOT/opt"
echo "[libtorch] installing torch==$TORCH_VER for $PLATFORM ABI_cxx11=${LIBTORCH_CXX11_ABI} → $OUT"

install_from_python() {
  # Pip CPU wheels are typically pre-cxx11 (ABI=0) — only use when ABI=0 requested
  if [[ "$LIBTORCH_CXX11_ABI" == "1" ]]; then
    echo "[libtorch] skip pip for ABI=1; prefer official cxx11-abi zip" >&2
    return 1
  fi
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
  # Cluster pythons are often too old for torch>=2.x — fail clean, caller tries zip
  if ! "$py" -m pip install -q --upgrade pip; then
    rm -rf "$tmp"; return 1
  fi
  if ! "$py" -m pip install -q --no-cache-dir \
      --target "$tmp/site" \
      "torch==${TORCH_VER}" \
      --index-url https://download.pytorch.org/whl/cpu; then
    echo "[libtorch] pip cannot install torch==${TORCH_VER} (old Python?). Trying zip next." >&2
    rm -rf "$tmp"
    return 1
  fi

  local site
  site="$("$py" - <<PY
import glob
cands = glob.glob("$tmp/site/torch")
assert cands, "torch package missing under $tmp/site"
print(cands[0])
PY
)" || { rm -rf "$tmp"; return 1; }

  rm -rf "$OUT"
  mkdir -p "$OUT/lib"
  cp -a "$site/include" "$OUT/"
  cp -a "$site/lib"/*.so* "$OUT/lib/" 2>/dev/null || \
    cp -a "$site"/lib/*.so* "$OUT/lib/" 2>/dev/null || true
  if [[ ! -f "$OUT/lib/libtorch_cpu.so" ]]; then
    find "$site" -name 'libtorch_cpu.so' -exec cp -a {} "$OUT/lib/" \;
    find "$site" -name 'libc10.so' -exec cp -a {} "$OUT/lib/" \;
    find "$site" -name 'libtorch.so' -exec cp -a {} "$OUT/lib/" \;
    find "$site" -name 'libgomp*.so*' -exec cp -a {} "$OUT/lib/" \;
    find "$site" -name 'libomp*.so*' -exec cp -a {} "$OUT/lib/" \;
  fi
  if [[ ! -f "$OUT/lib/libtorch_cpu.so" ]]; then
    local tlib="$site/lib"
    [[ -d "$tlib" ]] || tlib="$(dirname "$site")/torch/lib"
    [[ -d "$tlib" ]] && cp -a "$tlib"/*.so* "$OUT/lib/" 2>/dev/null || true
  fi
  if [[ ! -f "$OUT/include/torch/script.h" || ! -f "$OUT/lib/libtorch_cpu.so" ]]; then
    echo "[libtorch] pip install left incomplete tree" >&2
    rm -rf "$OUT" "$tmp"
    return 1
  fi
  echo "0" > "$OUT/OFR_CXX11_ABI"
  file "$OUT/lib/libtorch_cpu.so"
  du -sh "$OUT"
  rm -rf "$tmp"
}

install_from_zip() {
  local ver="$TORCH_VER"
  local url zip name
  case "$PLATFORM" in
    linux/amd64)
      if [[ "$LIBTORCH_CXX11_ABI" == "1" ]]; then
        name="libtorch-cxx11-abi-shared-with-deps-${ver}%2Bcpu.zip"
      else
        # pre-cxx11 ABI — works with older cluster Python; usually OK on RHEL8
        name="libtorch-shared-with-deps-${ver}%2Bcpu.zip"
      fi
      url="https://download.pytorch.org/libtorch/cpu/${name}"
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
    wget -O "$zip" "$url" || { rm -f "$zip"; return 1; }
  else
    curl -fL -o "$zip" "$url" || { rm -f "$zip"; return 1; }
  fi
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/libtorch_zip.XXXXXX")"
  unzip -q "$zip" -d "$tmp" || { rm -rf "$tmp" "$zip"; return 1; }
  rm -f "$zip"
  rm -rf "$OUT"
  mv "$tmp/libtorch" "$OUT"
  rm -rf "$tmp"
  if [[ ! -f "$OUT/include/torch/script.h" || ! -f "$OUT/lib/libtorch_cpu.so" ]]; then
    echo "[libtorch] zip extract incomplete" >&2
    rm -rf "$OUT"
    return 1
  fi
  echo "$LIBTORCH_CXX11_ABI" > "$OUT/OFR_CXX11_ABI"
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
      apt-get update -qq && apt-get install -y -qq libgomp1 file unzip >/dev/null
      pip install -q --no-cache-dir torch==${TORCH_VER} --index-url https://download.pytorch.org/whl/cpu
      SITE=\$(python -c \"import torch, pathlib; print(pathlib.Path(torch.__file__).parent)\")
      rm -rf /out/libtorch
      mkdir -p /out/libtorch/lib
      cp -a \"\$SITE/include\" /out/libtorch/
      cp -a \"\$SITE/lib\"/*.so* /out/libtorch/lib/
      echo 0 > /out/libtorch/OFR_CXX11_ABI
      test -f /out/libtorch/include/torch/script.h
      test -f /out/libtorch/lib/libtorch_cpu.so
      file /out/libtorch/lib/libtorch_cpu.so
      du -sh /out/libtorch
    "
}

# Prefer zip on HPC (old system Python cannot pip-install torch 2.x)
ok=0
if [[ "${LIBTORCH_USE_DOCKER:-0}" == "1" ]]; then
  install_from_docker && ok=1
elif [[ "$LIBTORCH_CXX11_ABI" == "1" ]]; then
  install_from_zip && ok=1
else
  # ABI=0: zip first (QB), then pip, then docker
  if install_from_zip; then ok=1
  elif install_from_python; then ok=1
  elif install_from_docker; then ok=1
  fi
fi

if [[ "$ok" != "1" ]] || [[ ! -f "$OUT/lib/libtorch_cpu.so" ]]; then
  echo "FATAL: could not install LibTorch (need wget/curl + unzip for official zip)" >&2
  echo "  Manual: download libtorch-shared-with-deps-${TORCH_VER}+cpu.zip from download.pytorch.org" >&2
  echo "  and unpack to $OUT" >&2
  rm -rf "$OUT"
  exit 1
fi

echo "Installed $OUT for $PLATFORM (OFR_CXX11_ABI=$(cat "$OUT/OFR_CXX11_ABI" 2>/dev/null || echo '?'))"
echo "Next: bash tools/build_ofrl_policy_worker.sh && wmake -j8 src/policyRuntime"
