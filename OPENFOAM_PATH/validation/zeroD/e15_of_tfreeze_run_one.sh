#!/bin/bash
# Run one E15 OF T-freeze QSS job (e15_of_tfreeze_jobs.tsv).
set +e
source /usr/lib/openfoam/openfoam2312/etc/bashrc || true
set +e

ROOT="${ROOT:-/work}"
IDX="${1:?job index}"
TSV="$ROOT/validation/zeroD/e15_conformance/e15_of_tfreeze_jobs.tsv"
SAFE_PREFIX="$ROOT/validation/zeroD/e15_conformance/of_work_tfreeze/"

LINE=$(awk -F'\t' -v i="$IDX" 'NR>1 && $1==i {print; exit}' "$TSV")
if [ -z "$LINE" ]; then
  echo "No job idx=$IDX in $TSV"
  exit 2
fi
IFS=$'\t' read -r _JIDX TAG SOLVER _T0 _P _PHI TEND WALL_CAP WORK_REL OUT_REL IC_REL _Y0REL <<<"$LINE"

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

set -e
CASE_SRC="$ROOT/cases/chemFoam_0D"
WORK="$ROOT/$WORK_REL"
OUT="$ROOT/$OUT_REL"
IC="$ROOT/$IC_REL"
CHEM_TMPL="$ROOT/validation/zeroD/e11_3/chemistryProperties.template"

case "$WORK" in
  "$SAFE_PREFIX"*) ;;
  *)
    echo "REFUSING unsafe WORK='$WORK' (must be under $SAFE_PREFIX)"
    exit 99
    ;;
esac

mkdir -p "$OUT" "$(dirname "$WORK")"
rm -rf "$WORK"
mkdir -p "$WORK"
cp -a "$CASE_SRC/constant" "$CASE_SRC/system" "$CASE_SRC/chemkin" "$CASE_SRC/Allclean" "$WORK/" 2>/dev/null || true
cp -f "$CHEM_TMPL" "$WORK/constant/chemistryProperties.template"
cd "$WORK"
./Allclean >/dev/null 2>&1 || true
rm -rf 0 2>/dev/null || true

cp -f "$IC" constant/initialConditions
cp -f constant/chemistryProperties.template constant/chemistryProperties
sed -i "s/__SOLVER__/${SOLVER}/" constant/chemistryProperties

# Sanity: Tfreeze must be on in template
if ! grep -q "Tfreeze[[:space:]]*true" constant/chemistryProperties; then
  echo "FATAL: Tfreeze not true in chemistryProperties" | tee "$OUT/log.chemFoam"
  echo "failure=bad_chem" | tee "$OUT/failure.txt"
  exit 0
fi

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

echo "=== E15 OF-Tfreeze idx=${IDX} tag=${TAG} solver=${SOLVER} endTime=${TEND} wall_cap=${WALL_CAP}s ===" | tee "$OUT/run_header.txt"
START=$(date +%s)
set +e
timeout --signal=TERM --kill-after=30s "${WALL_CAP}" chemFoamDebug > "$OUT/log.chemFoam" 2>&1
RC=$?
set -e
END=$(date +%s)
echo "wall_s=$((END-START))" | tee "$OUT/wall.txt"
echo "exit_code=$RC" | tee -a "$OUT/wall.txt"

cp -f chemFoam.out "$OUT/chemFoam.out" 2>/dev/null || true
cp -f constant/chemistryProperties "$OUT/"
cp -f constant/initialConditions "$OUT/"

FINAL=""
for d in $(ls -1d [0-9]* 2>/dev/null | sort -g); do FINAL="$d"; done
if [ -n "$FINAL" ] && [ -d "$FINAL" ]; then
  mkdir -p "$OUT/fields"
  for f in "$FINAL"/*; do
    bn=$(basename "$f")
    case "$bn" in uniform|polyMesh) ;; *) cp -f "$f" "$OUT/fields/$bn" 2>/dev/null || true ;; esac
  done
  echo "final_time=$FINAL" > "$OUT/final_time.txt"
fi

FAIL="ok"
if [ "$RC" -eq 124 ] || [ "$RC" -eq 137 ]; then FAIL="wall_timeout"
elif grep -q "FOAM FATAL" "$OUT/log.chemFoam" 2>/dev/null; then FAIL="foam_fatal"
elif grep -qE "Maximum number of iterations exceeded|JANAF" "$OUT/log.chemFoam" 2>/dev/null; then FAIL="thermo_newton"
elif [ ! -s "$OUT/chemFoam.out" ]; then FAIL="no_output"
elif ! grep -q "End" "$OUT/log.chemFoam" 2>/dev/null; then FAIL="incomplete"
fi
echo "failure=$FAIL" | tee "$OUT/failure.txt"
echo "RC=$RC FAIL=$FAIL wall=$((END-START))s → $OUT"
exit 0
