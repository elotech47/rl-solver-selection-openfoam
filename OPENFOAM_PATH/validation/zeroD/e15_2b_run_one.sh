#!/bin/bash
# Run one E15.2b job by index (e15_2b_jobs.tsv).
set +e
source /usr/lib/openfoam/openfoam2312/etc/bashrc || true
set +e

ROOT="${ROOT:-/work}"
IDX="${1:?job index}"
TSV="$ROOT/validation/zeroD/e15_conformance/e15_2b_jobs.tsv"
SAFE_PREFIX="$ROOT/validation/zeroD/e15_conformance/e15_2b_work/"

LINE=$(awk -F'\t' -v i="$IDX" 'NR>1 && $1==i {print; exit}' "$TSV")
[ -n "$LINE" ] || { echo "No job $IDX"; exit 2; }
IFS=$'\t' read -r _JIDX TAG TOGGLE SOLVER TEND WALL_CAP WORK_REL OUT_REL IC_REL CHEM_REL <<<"$LINE"

if [ -z "${WM_OPTIONS:-}" ]; then
  CHEM=$(ls -1 "$ROOT"/platforms/*/bin/chemFoamDebug 2>/dev/null | head -1 || true)
  WM_OPTIONS=$(basename "$(dirname "$(dirname "$CHEM")")")
fi
export WM_PROJECT_USER_DIR="$ROOT"
export FOAM_USER_APPBIN="$ROOT/platforms/${WM_OPTIONS}/bin"
export FOAM_USER_LIBBIN="$ROOT/platforms/${WM_OPTIONS}/lib"
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${ROOT}/opt/sundials-arm64/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"
export OFRL_STOCK_THE=1
export OFRL_DEBUG_STATE=0
export OFRL_DEBUG_INVARIANTS=0

WORK="$ROOT/$WORK_REL"
OUT="$ROOT/$OUT_REL"
case "$WORK" in
  "$SAFE_PREFIX"*) ;;
  *) echo "REFUSING unsafe WORK=$WORK"; exit 99 ;;
esac

mkdir -p "$OUT" "$(dirname "$WORK")"
rm -rf "$WORK"
mkdir -p "$WORK"
CASE_SRC="$ROOT/cases/chemFoam_0D"
cp -a "$CASE_SRC/constant" "$CASE_SRC/system" "$CASE_SRC/chemkin" "$CASE_SRC/Allclean" "$WORK/" 2>/dev/null || true
cd "$WORK"
./Allclean >/dev/null 2>&1 || true
rm -rf 0 2>/dev/null || true
cp -f "$ROOT/$IC_REL" constant/initialConditions
cp -f "$ROOT/$CHEM_REL" constant/chemistryProperties

cat > system/controlDict <<EOF
FoamFile
{
    version     2;
    format      ascii;
    class       dictionary;
    object      controlDict;
}
application     chemFoamDebug;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         ${TEND};
deltaT          1e-06;
maxDeltaT       1e-06;
adjustTimeStep  yes;
writeControl    adjustable;
writeInterval   ${TEND};
purgeWrite      0;
writeFormat     ascii;
writeCompression off;
timeFormat      general;
timePrecision   8;
runTimeModifiable yes;
libs            ( "libofRlInvariants.so" "libqssChemistrySolver.so" "libcvodeChemistrySolver.so" );
DebugSwitches { SolverPerformance 0; }
EOF

echo "=== E15.2b idx=$IDX $TAG toggle=$TOGGLE solver=$SOLVER ===" | tee "$OUT/run_header.txt"
START=$(date +%s)
set +e
timeout --signal=TERM --kill-after=30s "${WALL_CAP}" chemFoamDebug > "$OUT/log.chemFoam" 2>&1
RC=$?
set -e
END=$(date +%s)
echo "wall_s=$((END-START))" | tee "$OUT/wall.txt"
echo "exit_code=$RC" | tee -a "$OUT/wall.txt"
cp -f chemFoam.out constant/chemistryProperties constant/initialConditions "$OUT/" 2>/dev/null || true
FINAL=""
for d in $(ls -1d [0-9]* 2>/dev/null | sort -g); do FINAL="$d"; done
if [ -n "$FINAL" ] && [ -d "$FINAL" ]; then
  mkdir -p "$OUT/fields"
  for f in "$FINAL"/*; do
    bn=$(basename "$f")
    case "$bn" in uniform|polyMesh) ;; *) cp -f "$f" "$OUT/fields/$bn" 2>/dev/null || true ;; esac
  done
fi
FAIL=ok
if [ "$RC" -eq 124 ] || [ "$RC" -eq 137 ]; then FAIL=wall_timeout
elif grep -q "FOAM FATAL" "$OUT/log.chemFoam" 2>/dev/null; then FAIL=foam_fatal
elif grep -qE "Maximum number of iterations exceeded|JANAF" "$OUT/log.chemFoam" 2>/dev/null; then FAIL=thermo_newton
elif [ ! -s "$OUT/chemFoam.out" ]; then FAIL=no_output
elif ! grep -q "End" "$OUT/log.chemFoam" 2>/dev/null; then FAIL=incomplete
fi
echo "failure=$FAIL" | tee "$OUT/failure.txt"
exit 0
