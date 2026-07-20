#!/usr/bin/env bash
# E17 x86_64 blocking preflight (WSL ext4 Threadripper):
#   1) ext4 case tree
#   2) E16.5 clock gate (rebuild + run + gate.py)
#   3) E16.4 C2 MidT all three 0D modes vs frozen table
#   4) TorchScript load smoke on x86_64
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
PLATFORM="${OF_PLATFORM:-linux/amd64}"
PY="${PY:-python3}"
export DOCKER_HOST="${DOCKER_HOST:-unix:///var/run/docker.sock}"
PF="$ROOT/validation/zeroD/e17_remote_runs/preflight_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$PF"

fs_type=$(df -T "$ROOT" | awk 'NR==2 {print $2}')
fs_dev=$(df -T "$ROOT" | awk 'NR==2 {print $1}')
{
  echo "preflight=E17_x86_64"
  echo "root=$ROOT"
  echo "fs_type=$fs_type dev=$fs_dev"
  echo "platform=$PLATFORM"
  echo "nproc=$(nproc) physical_cores=16 (use NPROC=16, no SMT)"
  echo "alphaEff_probe=turbulence->alphaEff() same as EEqn; laminar => alphahe(); also log thermo.alpha()"
  echo "E16_5_status=GREEN in repo; rerunning gate on this host"
} | tee "$PF/preflight_header.txt"

if [[ "$fs_type" != ext4 ]]; then
  echo "FATAL: case tree not on ext4 (got $fs_type)" | tee "$PF/FATAL.txt"
  exit 2
fi
case "$ROOT" in
  /mnt/*) echo "FATAL: case tree under /mnt — move to ~/ on WSL ext4" | tee -a "$PF/FATAL.txt"; exit 2 ;;
esac

# LibTorch amd64
if [[ ! -f "$ROOT/opt/libtorch/include/torch/script.h" ]]; then
  echo "[preflight] installing LibTorch amd64"
  OF_PLATFORM="$PLATFORM" bash "$ROOT/tools/install_libtorch.sh" | tee "$PF/log.libtorch.txt"
fi

echo "[preflight] wmake user stack (policyRuntime + rlChemistryModel + reactingFoamDebug)"
docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  -e SUNDIALS_DIR=/work/opt/sundials \
  -e LIBTORCH_DIR=/work/opt/libtorch \
  "$IMAGE" \
  -lc 'set +eu; source /usr/lib/openfoam/openfoam2312/etc/bashrc; set +u; set -e
       export WM_PROJECT_USER_DIR=/work
       export FOAM_USER_LIBBIN=/work/platforms/${WM_OPTIONS}/lib
       export FOAM_USER_APPBIN=/work/platforms/${WM_OPTIONS}/bin
       export SUNDIALS_DIR=/work/opt/sundials
       export LIBTORCH_DIR=/work/opt/libtorch
       export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$SUNDIALS_DIR/lib:$LIBTORCH_DIR/lib:${LD_LIBRARY_PATH:-}
       bash /work/tools/build_libs.sh
       cd /work/applications/solvers/reactingFoam && wmake -j "$(nproc)"
       ls -la /work/platforms/*/lib/lib{policy,rl}* /work/platforms/*/bin/reactingFoamDebug
       ' | tee "$PF/log.wmake.txt"

# TorchScript load smoke (host-side via container)
docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  "$IMAGE" \
  -lc 'set +eu; source /usr/lib/openfoam/openfoam2312/etc/bashrc; set +u; set -e
       export LD_LIBRARY_PATH=/work/opt/libtorch/lib:/work/platforms/linux64GccDPInt32Opt/lib
       export OMP_NUM_THREADS=1
       ldd /work/platforms/linux64GccDPInt32Opt/lib/libpolicyRuntime.so | head -20
       strings /work/platforms/linux64GccDPInt32Opt/lib/libpolicyRuntime.so | grep -i torch | head -3 || true
       ' | tee "$PF/log.torch_ldd.txt"

echo "[preflight] E16.5 clock gate"
chmod +x validation/zeroD/e16_5_*.sh validation/zeroD/e16_5_*.py 2>/dev/null || true
if [[ ! -f validation/e16_parity/e16_4_ics/C2_MidT_MidP_initialConditions ]]; then
  "$PY" validation/zeroD/e16_4_write_ics.py --all | tee "$PF/log.e16_ics.txt"
fi
for tag in fixed_ref fixed_ref_b; do
  docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work --memory=16g \
    "$IMAGE" \
    -lc "bash /work/validation/zeroD/e16_5_run_one.sh $tag fixed" \
    | tee "$PF/log.e16_5_${tag}.txt"
done
docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work --memory=16g \
  "$IMAGE" \
  -lc "bash /work/validation/zeroD/e16_5_run_one.sh synth_irregular synth_irregular" \
  | tee "$PF/log.e16_5_synth_irregular.txt"
# Gate3 needs PyTorch on the runner; use container Python (host may lack torch).
docker run --rm --platform="$PLATFORM" \
  -v "$ROOT:/work" -w /work \
  python:3.11-slim-bookworm \
  bash -lc 'pip install -q torch numpy && python3 /work/validation/zeroD/e16_5_gate.py' \
  | tee "$PF/e16_5_gate.txt"
grep -E "Verdict|gate3|PASS|FAIL|GREEN|RED" "$PF/e16_5_gate.txt" || true
if ! grep -q '"verdict": "GREEN"' "$ROOT/validation/e16_parity/E16_5_SUMMARY.json" 2>/dev/null; then
  echo "FATAL: E16.5 gate not GREEN — hold rlAdaptive" | tee "$PF/FATAL_e16_5.txt"
  exit 3
fi

echo "[preflight] E16.4 C2 MidT (cvodeOnly qssOnly rlAdaptive)"
for mode in cvodeOnly qssOnly rlAdaptive; do
  docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work --memory=16g \
    "$IMAGE" \
    -lc "bash /work/validation/zeroD/e16_4_run_one.sh C2 MidT_MidP 800 10 0.062 1e-6 0.0035 $mode" \
    | tee "$PF/log.e16_4_C2_${mode}.txt"
done
"$PY" validation/zeroD/e17_remote/preflight_c2_check.py "$PF" | tee "$PF/preflight_c2_check.txt"
if ! grep -q '"PASS": true' "$PF/preflight_c2_check.json" 2>/dev/null; then
  echo "FATAL: E16.4 C2 drift vs frozen table" | tee "$PF/FATAL_e16_4_c2.txt"
  exit 4
fi

echo "[preflight] DONE → $PF"
echo "Next: bash validation/zeroD/e17_remote/02_smoke_three_mode.sh"
