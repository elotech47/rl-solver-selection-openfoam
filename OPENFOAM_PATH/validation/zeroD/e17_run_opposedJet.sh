#!/bin/bash
# E17.1 — opposed-jet CVODE ignition scout / smoke.
# Run inside OF container with /work = OPENFOAM_PATH.
# Args: OUT_DIR [optional label]
set +e
source /usr/lib/openfoam/openfoam2312/etc/bashrc
set -e

ROOT=/work
CASE="$ROOT/cases/opposedJet_2D"
OUT="${1:-$ROOT/validation/zeroD/e17_ignition_scout}"

export WM_PROJECT_USER_DIR="$ROOT"
export FOAM_USER_APPBIN="$ROOT/platforms/${WM_OPTIONS}/bin"
export FOAM_USER_LIBBIN="$ROOT/platforms/${WM_OPTIONS}/lib"
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${ROOT}/opt/sundials-arm64/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"
export OFRL_PROP_SANITY=1

mkdir -p "$OUT"
cd "$CASE"

rm -rf [1-9]* 0.[0-9]* processor* postProcessing 2>/dev/null || true
rm -f log.blockMesh log.reactingFoam e12_prop_sanity.csv e17_prop_sanity.csv 2>/dev/null || true

echo "=== blockMesh ==="
blockMesh 2>&1 | tee "$OUT/log.blockMesh" | tail -20

echo "=== reactingFoamDebug (cvodeOnly scout) ==="
START=$(date +%s)
reactingFoamDebug 2>&1 | tee "$OUT/log.reactingFoam" || true
END=$(date +%s)
echo "wall_s=$((END-START))" | tee "$OUT/wall.txt"

cp -f e12_prop_sanity.csv "$OUT/e17_prop_sanity.csv" 2>/dev/null || true
cp -f e12_prop_sanity.csv "$OUT/" 2>/dev/null || true
cp -f system/controlDict constant/chemistryProperties 0/T 0/U "$OUT/" 2>/dev/null || true

echo "=== summary greps ==="
grep -E "FOAM FATAL|End$|propSanity:|min/max\(T\)|nCells" "$OUT/log.reactingFoam" | tail -50 || true
echo "DONE out=$OUT"
