#!/bin/bash
# E11.3 — stock THE MidT on refit thermo.
# Usage (OF container, /work = OPENFOAM_PATH):
#   e11_3_midt.sh <outdir> <ode|cvode> [OFRL_DEBUG_STATE]
set +e
source /usr/lib/openfoam/openfoam2312/etc/bashrc
set -e

ROOT=/work
CASE="$ROOT/cases/chemFoam_0D"
OUT="${1:?outdir}"
SOLVER="${2:?ode or cvode}"
DBG="${3:-0}"

export WM_PROJECT_USER_DIR="$ROOT"
export FOAM_USER_APPBIN="$ROOT/platforms/${WM_OPTIONS}/bin"
export FOAM_USER_LIBBIN="$ROOT/platforms/${WM_OPTIONS}/lib"
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${ROOT}/opt/sundials-arm64/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"
export OFRL_STOCK_THE=1
export OFRL_DEBUG_STATE="$DBG"

mkdir -p "$OUT"
cd "$CASE"
./Allclean >/dev/null 2>&1 || true
rm -rf 0/[0-9]* 0/p 0/T 0/Y* 2>/dev/null || true

# chemistryProperties from template with selected solver
cp "$ROOT/cases/chemFoam_0D/constant/chemistryProperties.template" \
   constant/chemistryProperties 2>/dev/null || true
if [ ! -f constant/chemistryProperties.template ]; then
  cp "$ROOT/validation/zeroD/e11_3/chemistryProperties.template" constant/chemistryProperties.template
fi
cp constant/chemistryProperties.template constant/chemistryProperties
# Replace only the chemistryType solver line (marked __SOLVER__)
sed -i "s/__SOLVER__/${SOLVER}/" constant/chemistryProperties
echo "chemistryType.solver = $SOLVER"
grep -A2 chemistryType constant/chemistryProperties | head -5

APP=chemFoamDebug
if [ "$SOLVER" = "ode" ] && [ "$DBG" = "0" ] && command -v chemFoam >/dev/null 2>&1; then
  APP=chemFoam
fi

echo "Running APP=$APP SOLVER=$SOLVER OFRL_STOCK_THE=1 OFRL_DEBUG_STATE=$DBG"
START=$(date +%s)
"$APP" > "$OUT/log.chemFoam" 2>&1 || true
END=$(date +%s)
echo "wall_s=$((END-START))" | tee "$OUT/wall.txt"
cp -f chemFoam.out "$OUT/chemFoam.out" 2>/dev/null || true
cp -f e8_state.csv "$OUT/" 2>/dev/null || true
cp -f constant/chemistryProperties "$OUT/chemistryProperties"
cp -f constant/initialConditions "$OUT/initialConditions"

echo "DONE"
tail -5 "$OUT/wall.txt" || true
grep -E "Maximum number|End$|FOAM FATAL|JANAF|attempt to use" "$OUT/log.chemFoam" | tail -30 || true
tail -3 "$OUT/chemFoam.out" 2>/dev/null || true
