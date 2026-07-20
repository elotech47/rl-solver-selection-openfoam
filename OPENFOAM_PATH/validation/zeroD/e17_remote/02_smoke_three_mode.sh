#!/usr/bin/env bash
# E17 full smoke: cvodeOnly → qssOnly → rlAdaptive on opposedJet_2D (16 cores, quiet progress).
# Prerequisite: bash validation/zeroD/e17_remote/preflight_x86.sh (blocking).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
CASE="$ROOT/cases/opposedJet_2D"
KIT="$ROOT/validation/zeroD/e17_remote"
IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
PLATFORM="${OF_PLATFORM:-linux/amd64}"
NPROC="${NPROC:-16}"
ENDT="${E17_END_TIME:-5e-4}"
BASE="${E17_SMOKE_OUT:-$ROOT/validation/zeroD/e17_remote_runs/smoke_$(date +%Y%m%d_%H%M%S)}"
SKIP_KERNEL="${E17_SKIP_KERNEL:-1}"

if [[ "$NPROC" -gt 16 ]]; then
  echo "WARN: NPROC=$NPROC > 16 physical cores — clamping to 16 (disable SMT oversubscription)"
  NPROC=16
fi

mkdir -p "$BASE"
{
  echo "E17_smoke_three_mode"
  echo "host=$(uname -n) arch=$(uname -m) nproc=$(nproc) NPROC=$NPROC"
  echo "fs=$(df -T "$ROOT" | awk 'NR==2{print $2,$1}')"
  echo "ENDT=$ENDT writeInterval=1e-5 mesh=3200cells decompose=scotch"
  echo "mpi=mpirun --map-by core --bind-to core"
  echo "threads: OMP_NUM_THREADS=1 ATEN_NUM_THREADS=1 TORCH_MKLDNN_ENABLED=0"
  echo "alphaEff: turbulence->alphaEff()=alphahe() laminar; also log thermo.alpha() — see propertySanityLog.H"
  echo "E16_5: decision clock GREEN required before rlAdaptive"
} | tee "$BASE/smoke_header.txt"

# Hot kernel IC (reuse from ignition scout unless skipped)
if [[ "$SKIP_KERNEL" != "1" ]]; then
  python3 "$ROOT/validation/zeroD/e17_set_hot_kernel.py" --Z 0.05 --T 1300 --p-atm 10 \
    | tee "$BASE/log.kernel.txt"
fi

python3 - <<PY
from pathlib import Path
import re
case = Path("$CASE")
for name, val in (("T", 1350.0),):
    p = case / "0" / name
    text = p.read_text()
    pat = re.compile(r"(air\s*\{[^}]*?value\s+uniform\s+)[0-9.eE+-]+", re.S)
    text2, n = pat.subn(rf"\g<1>{val:g}", text, count=1)
    if n != 1:
        raise SystemExit("air patch missing in 0/T")
    p.write_text(text2)
u = case / "0/U"
ut = u.read_text()
ut = re.sub(r"uniform \(\s*[0-9.eE+-]+\s+0\s+0\s*\);", "uniform (0.05 0 0);", ut, count=1)
ut = re.sub(r"uniform \(\s*-[0-9.eE+-]+\s+0\s+0\s*\);", "uniform (-0.05 0 0);", ut, count=1)
u.write_text(ut)
PY

python3 - <<PY
from pathlib import Path
import re
p = Path("$CASE/system/controlDict")
t = p.read_text()
subs = {
    r"endTime\s+[^;]+;": f"endTime         {float('$ENDT')};",
    r"writeInterval\s+[^;]+;": "writeInterval   1e-05;",
    # ASCII so T/chemCpuTime/solverFlag are human-readable in the IDE
    r"writeFormat\s+[^;]+;": "writeFormat     ascii;",
    r"writeCompression\s+[^;]+;": "writeCompression off;",
    r"propSanityInterval\s+[^;]+;": "propSanityInterval 10;",
    r"adjustTimeStep\s+[^;]+;": "adjustTimeStep  yes;",
    r"runTimeModifiable\s+[^;]+;": "runTimeModifiable yes;",
}
for pat, rep in subs.items():
    t2, n = re.subn(pat, rep, t, count=1)
    t = t2 if n else t
if "writeCompression" not in t:
    t = t.replace("writeFormat     ascii;", "writeFormat     ascii;\n\nwriteCompression off;")
p.write_text(t)
print("controlDict smoke IO patched (ascii, no compression)")
PY

sed "s/numberOfSubdomains.*/numberOfSubdomains  ${NPROC};/" \
  "$KIT/decomposeParDict.template" > "$CASE/system/decomposeParDict"

FAILED_MODES=()
for MODE in cvodeOnly qssOnly rlAdaptive; do
  OUT="$BASE/${MODE}"
  mkdir -p "$OUT"
  echo "========== E17 smoke MODE=$MODE OUT=$OUT ==========" | tee "$OUT/run_banner.txt"
  E17_CONTAINER_ROOT=/work bash "$ROOT/validation/zeroD/e17_configure_mode.sh" "$MODE"
  cp -f "$CASE/system/controlDict" "$CASE/constant/chemistryProperties" "$OUT/" 2>/dev/null || true

  set +e
  docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work \
    -e MODE="$MODE" -e OUT="/work/${OUT#"$ROOT"/}" -e NPROC="$NPROC" -e ENDT="$ENDT" \
    "$IMAGE" \
    -lc 'chmod +x /work/validation/zeroD/e17_remote/e17_smoke_run_one.sh
         bash /work/validation/zeroD/e17_remote/e17_smoke_run_one.sh'
  RC=$?
  set -e
  echo "MODE=$MODE docker_exit=$RC" | tee -a "$OUT/wall.txt"
  if [[ "$RC" -ne 0 ]]; then
    echo "WARN: $MODE failed (exit $RC) — continuing remaining modes" | tee -a "$BASE/smoke_failures.txt"
    FAILED_MODES+=("$MODE:$RC")
  fi

  # Host-side post (python available on WSL)
  python3 "$KIT/e17_smoke_post_one.py" --run-dir "$OUT" --mode "$MODE" --end-time "$ENDT" || true
  export E17_OUT="$OUT"
  bash "$KIT/02_extract_results.sh" || true
  python3 "$KIT/03_preprocess.py" --run-dir "$OUT" --out-dir "$OUT/preprocess" || true
done

if ((${#FAILED_MODES[@]})); then
  echo "FAILED_MODES=${FAILED_MODES[*]}" | tee -a "$BASE/smoke_failures.txt"
fi

python3 "$KIT/e17_smoke_report.py" --base "$BASE" | tee "$BASE/smoke_report.txt"
echo "[E17 smoke] DONE → $BASE"
