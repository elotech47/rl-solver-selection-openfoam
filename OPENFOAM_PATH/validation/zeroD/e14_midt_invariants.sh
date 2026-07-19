#!/bin/bash
# E14.2 — MidT_MidP Option R with OFRL_DEBUG_INVARIANTS=1 (qss + cvode).
# Usage (OF container, /work = OPENFOAM_PATH):
#   e14_midt_invariants.sh [cvode|qss|both]
set +e
source /usr/lib/openfoam/openfoam2312/etc/bashrc
set -e

ROOT=/work
CASE="$ROOT/cases/chemFoam_0D"
BASE_OUT="$ROOT/validation/zeroD/e14_midt"
MODE="${1:-both}"

export WM_PROJECT_USER_DIR="$ROOT"
export FOAM_USER_APPBIN="$ROOT/platforms/${WM_OPTIONS}/bin"
export FOAM_USER_LIBBIN="$ROOT/platforms/${WM_OPTIONS}/lib"
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${ROOT}/opt/sundials-arm64/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"
export OFRL_STOCK_THE=1
export OFRL_DEBUG_STATE=0
export OFRL_DEBUG_INVARIANTS=1

IC_SRC="$ROOT/validation/zeroD/e11_3/cvode_stockTHE/initialConditions"
CHEM_TMPL="$ROOT/cases/chemFoam_0D/constant/chemistryProperties.template"

run_one() {
  local SOLVER="$1"
  local OUT="$BASE_OUT/$SOLVER"
  mkdir -p "$OUT"
  cd "$CASE"
  ./Allclean >/dev/null 2>&1 || true
  rm -rf 0/[0-9]* 0/p 0/T 0/Y* e14_invariants.csv e8_state.csv 2>/dev/null || true

  cp -f "$IC_SRC" constant/initialConditions
  cp -f "$CHEM_TMPL" constant/chemistryProperties
  sed -i "s/__SOLVER__/${SOLVER}/" constant/chemistryProperties

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
endTime         0.0035;
deltaT          1e-06;
maxDeltaT       1e-06;
adjustTimeStep  yes;
writeControl    adjustable;
writeInterval   0.0005;
purgeWrite      0;
writeFormat     ascii;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable yes;
libs            ( "libofRlInvariants.so" "libqssChemistrySolver.so" "libcvodeChemistrySolver.so" );
DebugSwitches
{
    SolverPerformance 0;
}
EOF

  echo "=== E14 MidT invariants solver=${SOLVER} ==="
  START=$(date +%s)
  chemFoamDebug > "$OUT/log.chemFoam" 2>&1 || true
  END=$(date +%s)
  echo "wall_s=$((END-START))" | tee "$OUT/wall.txt"
  cp -f chemFoam.out "$OUT/chemFoam.out" 2>/dev/null || true
  cp -f e14_invariants.csv "$OUT/" 2>/dev/null || true
  cp -f e14_Y.csv "$OUT/" 2>/dev/null || true
  cp -f constant/chemistryProperties "$OUT/"
  cp -f constant/initialConditions "$OUT/"
  grep -E "End$|FOAM FATAL|JANAF|Maximum number" "$OUT/log.chemFoam" | tail -20 || true
  tail -3 "$OUT/chemFoam.out" 2>/dev/null || true
  wc -l "$OUT/e14_invariants.csv" 2>/dev/null || echo "MISSING e14_invariants.csv"
  wc -l "$OUT/e14_Y.csv" 2>/dev/null || echo "MISSING e14_Y.csv"
}

case "$MODE" in
  cvode) run_one cvode ;;
  qss) run_one qss ;;
  both) run_one cvode; run_one qss ;;
  *) echo "usage: $0 [cvode|qss|both]"; exit 2 ;;
esac

echo "E14 MidT done → $BASE_OUT"
