#!/usr/bin/env bash
# E17 remote: parallel opposed-jet run (cvodeOnly | qssOnly | rlAdaptive).
# Env:
#   NPROC          MPI ranks (default 8)
#   E17_MODE       cvodeOnly|qssOnly|rlAdaptive (default cvodeOnly)
#   E17_OUT        output directory under OPENFOAM_PATH
#   E17_END_TIME   endTime seconds (default 0.001)
#   E17_SKIP_KERNEL=1  do not rewrite IC
#   E17_T_AIR / E17_U  optional BC overrides
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
CASE="$ROOT/cases/opposedJet_2D"
KIT="$ROOT/validation/zeroD/e17_remote"
NPROC="${NPROC:-8}"
MODE="${E17_MODE:-cvodeOnly}"
ENDT="${E17_END_TIME:-0.001}"
OUT="${E17_OUT:-$ROOT/validation/zeroD/e17_remote_runs/$(date +%Y%m%d_%H%M%S)_${MODE}}"
IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
PLATFORM="${OF_PLATFORM:-linux/amd64}"
SKIP_KERNEL="${E17_SKIP_KERNEL:-0}"

mkdir -p "$OUT"
# path as seen inside container
OUT_REL="${OUT#"$ROOT"/}"
echo "[e17 run] MODE=$MODE NPROC=$NPROC ENDT=$ENDT OUT=$OUT" | tee "$OUT/run_banner.txt"

# --- Host-side case prep ---
if [[ "$SKIP_KERNEL" != "1" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    python3 "$ROOT/validation/zeroD/e17_set_hot_kernel.py" --Z 0.05 --T 1300 --p-atm 10 \
      2>&1 | tee "$OUT/log.kernel.txt" || echo "WARN: kernel script failed (Cantera?); continuing"
  fi
fi

# BCs (optional overrides)
python3 - <<PY
from pathlib import Path
import re
case = Path("$CASE")
t_air = float("${E17_T_AIR:-1350}")
u = float("${E17_U:-0.05}")
tp = case/"0/T"
text = tp.read_text()
parts = text.split("air")
if len(parts) >= 2:
    head, rest = parts[0], "air".join(parts[1:])
    rest2, n = re.subn(r"(value\s+uniform\s+)[0-9.]+", rf"\g<1>{t_air:g}", rest, count=1)
    tp.write_text(head + rest2 if n else text)
up = case/"0/U"
ut = up.read_text()
ut = re.sub(r"uniform \(\s*[0-9.eE+-]+\s+0\s+0\s*\);", f"uniform ({u:g} 0 0);", ut, count=1)
ut = re.sub(r"uniform \(\s*-[0-9.eE+-]+\s+0\s+0\s*\);", f"uniform (-{u:g} 0 0);", ut, count=1)
up.write_text(ut)
print("T_air", t_air, "U", u)
PY

# endTime
python3 - <<PY
from pathlib import Path
import re
p = Path("$CASE/system/controlDict")
t = p.read_text()
t = re.sub(r"endTime\s+[^;]+;", f"endTime         {float('$ENDT')};", t, count=1)
# libs for rl modes
if "$MODE" != "cvodeOnly":
    want = 'libs            ( "libqssChemistrySolver.so" "libcvodeChemistrySolver.so" "libpolicyRuntime.so" "librlChemistryModel.so" );'
else:
    want = 'libs            ( "libqssChemistrySolver.so" "libcvodeChemistrySolver.so" );'
t2, n = re.subn(r"libs\s*\([^;]*\);", want, t, count=1)
p.write_text(t2 if n else t)
print("controlDict updated")
PY

# chemistry
if [[ "$MODE" == "cvodeOnly" ]]; then
  # Prefer stock cvode solver path for max speed on scout; also supports method rl
  bash "$ROOT/validation/zeroD/e17_configure_mode.sh" cvodeOnly
else
  bash "$ROOT/validation/zeroD/e17_configure_mode.sh" "$MODE"
fi

# decomposeParDict
sed "s/numberOfSubdomains.*/numberOfSubdomains  ${NPROC};/" \
  "$KIT/decomposeParDict.template" > "$CASE/system/decomposeParDict"

# --- Inside container ---
docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  -e NPROC="$NPROC" -e MODE="$MODE" -e OUT="/work/$OUT_REL" \
  "$IMAGE" \
  -lc 'set +eu; source /usr/lib/openfoam/openfoam2312/etc/bashrc; set +u; set -e
       mkdir -p "$OUT"
       export WM_PROJECT_USER_DIR=/work
       export FOAM_USER_LIBBIN=/work/platforms/${WM_OPTIONS}/lib
       export FOAM_USER_APPBIN=/work/platforms/${WM_OPTIONS}/bin
       export SUNDIALS_DIR=/work/opt/sundials
       export LIBTORCH_DIR=/work/opt/libtorch
       export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$SUNDIALS_DIR/lib:$LIBTORCH_DIR/lib:${LD_LIBRARY_PATH:-}
       export PATH=$FOAM_USER_APPBIN:$PATH
       export OFRL_PROP_SANITY=1
       export KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TORCH_MKLDNN_ENABLED=0
       if [[ -f $LIBTORCH_DIR/lib/libtorch_cpu.so ]]; then
         export LD_PRELOAD="$LIBTORCH_DIR/lib/libtorch_cpu.so:$LIBTORCH_DIR/lib/libc10.so:${LD_PRELOAD:-}"
         OMPLIB=$(ls $LIBTORCH_DIR/lib/libomp*.so 2>/dev/null | head -1 || true)
         [[ -n "$OMPLIB" ]] && export LD_PRELOAD="$LD_PRELOAD:$OMPLIB"
       fi
       CASE=/work/cases/opposedJet_2D
       cd "$CASE"
       rm -rf processor* [1-9]* 0.[0-9]* postProcessing 2>/dev/null || true
       echo "=== blockMesh ==="
       blockMesh 2>&1 | tee "$OUT/log.blockMesh" | tail -15
       echo "=== decomposePar ($NPROC) ==="
       decomposePar -force 2>&1 | tee "$OUT/log.decomposePar" | tail -20
       echo "=== mpirun reactingFoamDebug -parallel ==="
       START=$(date +%s)
       mpirun --allow-run-as-root -np "$NPROC" reactingFoamDebug -parallel \
         2>&1 | tee "$OUT/log.reactingFoam" || true
       END=$(date +%s)
       echo "wall_s=$((END-START))" | tee "$OUT/wall.txt"
       echo "=== reconstructPar ==="
       reconstructPar -latestTime 2>&1 | tee "$OUT/log.reconstructPar" | tail -20 || true
       cp -f system/controlDict constant/chemistryProperties system/decomposeParDict "$OUT/" 2>/dev/null || true
       cp -f 0/T 0/U "$OUT/" 2>/dev/null || true
       cp -f e12_prop_sanity.csv "$OUT/" 2>/dev/null || true
       LATEST=$(ls -d [0-9]* 2>/dev/null | sort -g | tail -1 || true)
       if [[ -n "${LATEST:-}" && -f "$LATEST/T" ]]; then
         mkdir -p "$OUT/fields"
         cp -f "$LATEST/T" "$OUT/fields/T"
         [[ -f "$LATEST/OH" ]] && cp -f "$LATEST/OH" "$OUT/fields/OH" || true
         [[ -f "$LATEST/solverFlag" ]] && cp -f "$LATEST/solverFlag" "$OUT/fields/solverFlag" || true
         echo "$LATEST" > "$OUT/latest_time.txt"
       fi
       grep -E "FOAM FATAL|End$|min/max\(T\)|propSanity:|Time =" "$OUT/log.reactingFoam" | tail -40 || true
       echo "DONE out=$OUT"
       '

echo "[e17 run] finished → $OUT"
echo "Next: E17_OUT=$OUT bash validation/zeroD/e17_remote/02_extract_results.sh"
