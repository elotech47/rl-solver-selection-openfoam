#!/usr/bin/env bash
# Run MidT chemFoamDebug (or stock chemFoam) for E8/E9.
# Usage: run_e8.sh <outdir> [chemFoamDebug|chemFoam] [OFRL_DEBUG_STATE]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CASE="${ROOT}/cases/chemFoam_0D"
OUT="${1:?outdir}"
APP="${2:-chemFoamDebug}"
DBG="${3:-0}"

source /usr/lib/openfoam/openfoam2312/etc/bashrc
export FOAM_USER_LIBBIN="${ROOT}/platforms/${WM_OPTIONS}/lib"
export FOAM_USER_APPBIN="${ROOT}/platforms/${WM_OPTIONS}/bin"
export WM_PROJECT_USER_DIR="${ROOT}"
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${ROOT}/opt/sundials-arm64/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"
export OFRL_DEBUG_STATE="${DBG}"

mkdir -p "${OUT}"
cd "${CASE}"
./Allclean >/dev/null 2>&1 || true
# Ensure no stale 0/{p,T,Y*}
rm -rf 0/[0-9]* 0/p 0/T 0/Y* 2>/dev/null || true

# Restore MidT IC / mechanism if Allclean wiped nothing important
# (constant/ is ours)

/usr/bin/time -p -o "${OUT}/wall.txt" "${APP}" > "${OUT}/log.chemFoam" 2>&1 || true
cp -f chemFoam.out "${OUT}/chemFoam.out" 2>/dev/null || true
cp -f e8_state.csv "${OUT}/" 2>/dev/null || true
cp -f e8_crash_state.dat "${OUT}/" 2>/dev/null || true
cp -f e8_crash_hs_cp.dat "${OUT}/" 2>/dev/null || true
# Keep a copy of chemistryProperties used
cp -f constant/chemistryProperties "${OUT}/chemistryProperties"
cp -f constant/initialConditions "${OUT}/initialConditions"
echo "DONE app=${APP} dbg=${DBG} out=${OUT}"
tail -5 "${OUT}/wall.txt" || true
grep -E "Maximum number|End$|ignition|OFRL_DEBUG|FATAL" "${OUT}/log.chemFoam" | tail -20 || true
