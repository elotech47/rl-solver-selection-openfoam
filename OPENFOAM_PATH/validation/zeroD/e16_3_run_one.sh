#!/usr/bin/env bash
# E16.3 inside-container runner: OF rlAdaptive / cvodeOnly / qssOnly for one IC.
# Args: LABEL T0 P_ATM PHI END_TIME MODE
# MODE in {rlAdaptive,cvodeOnly,qssOnly}
set -eo pipefail
set +eu
source /usr/lib/openfoam/openfoam2312/etc/bashrc
set -e
set +u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL="${1:?label}"
T0="${2:?T0}"
PATM="${3:?p_atm}"
PHI="${4:?phi}"
ENDT="${5:?endTime}"
MODE="${6:?mode}"

CASE="${ROOT}/cases/chemFoam_0D"
OUT="${ROOT}/validation/e16_parity/e16_3_runs/${LABEL}_${MODE}"
IC_DIR="${ROOT}/validation/zeroD/e15_conformance/of_ics"

# Prefer frozen IC when available
IC_NAME="T${T0%.*}_p${PATM%.*}_phi$(echo "$PHI" | sed 's/\./p/')_initialConditions"
# phi 1.0 → phi1p0
case "$PHI" in
  1|1.0) IC_NAME="T${T0%.*}_p${PATM%.*}_phi1p0_initialConditions" ;;
  0.5)  IC_NAME="T${T0%.*}_p${PATM%.*}_phi0p5_initialConditions" ;;
  1.5)  IC_NAME="T${T0%.*}_p${PATM%.*}_phi1p5_initialConditions" ;;
esac
IC="${IC_DIR}/${IC_NAME}"

export FOAM_USER_LIBBIN="${ROOT}/platforms/${WM_OPTIONS}/lib"
export FOAM_USER_APPBIN="${ROOT}/platforms/${WM_OPTIONS}/bin"
export WM_PROJECT_USER_DIR="${ROOT}"
export LIBTORCH_DIR="${ROOT}/opt/libtorch"
export SUNDIALS_DIR="${ROOT}/opt/sundials-arm64"
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${LIBTORCH_DIR}/lib:${SUNDIALS_DIR}/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"
# LibTorch (OpenMP) + OpenFOAM thread runtime coexistence
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export TORCH_MKLDNN_ENABLED=0
# Preload LibTorch before OpenFOAM symbols (required for JIT load/infer in-process)
export LD_PRELOAD="${LIBTORCH_DIR}/lib/libtorch_cpu.so:${LIBTORCH_DIR}/lib/libc10.so:${LIBTORCH_DIR}/lib/libomp-b8e5bcfb.so${LD_PRELOAD:+:$LD_PRELOAD}"

CHEMBIN="$(ls -1 "${ROOT}"/platforms/*/bin/chemFoamDebug 2>/dev/null | head -1 || true)"
test -n "$CHEMBIN" && test -x "$CHEMBIN" || { echo "FATAL missing chemFoamDebug"; exit 2; }
test -f "$IC" || { echo "FATAL missing $IC"; exit 2; }
test -f "${ROOT}/policy/policy.ts" || { echo "FATAL missing policy.ts"; exit 2; }
test -f "${ROOT}/policy/policy_manifest" || { echo "FATAL missing policy_manifest"; exit 2; }
test -f "${FOAM_USER_LIBBIN}/librlChemistryModel.so" || { echo "FATAL missing librlChemistryModel.so"; exit 2; }

mkdir -p "$OUT"
cd "$CASE"
./Allclean >/dev/null 2>&1 || true
rm -rf 0/p 0/T 0/Y* rl_decisions.csv 2>/dev/null || true
cp -f "$IC" constant/initialConditions

cat > constant/chemistryProperties <<EOF
FoamFile
{
    version         2;
    format          ascii;
    class           dictionary;
    object          chemistryProperties;
}
chemistryType
{
    solver          ode;
    method          rl;
}
chemistry       on;
initialChemicalTimeStep 1e-07;
rl
{
    mode                ${MODE};
    maxChemDeltaT       1e-6;
    numSteps            20;
    confidenceThreshold 0.6;
    manifest            "${ROOT}/policy/policy_manifest";
    torchScript         "${ROOT}/policy/policy.ts";
}
qssCoeffs
{
    epsmin          0.02;
    epsmax          100;
    dtmin           1e-12;
    dtmax           1e-06;
    abstol          1e-11;
    itermax         2;
    Tfreeze         true;
}
cvodeCoeffs
{
    relTol          1e-08;
    absTol          1e-12;
    maxSteps        100000;
}
odeCoeffs
{
    solver          seulex;
    absTol          1e-12;
    relTol          1e-08;
}
EOF

cat > system/controlDict <<EOF
FoamFile
{
    version         2;
    format          ascii;
    class           dictionary;
    object          controlDict;
}
application     chemFoamDebug;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         ${ENDT};
deltaT          1e-06;
writeControl    runTime;
writeInterval   ${ENDT};
purgeWrite      0;
writeFormat     ascii;
runTimeModifiable true;
adjustTimeStep  no;
maxDeltaT       1e-06;
libs
(
    "libqssChemistrySolver.so"
    "libcvodeChemistrySolver.so"
    "libpolicyRuntime.so"
    "librlChemistryModel.so"
);
EOF

echo "[e16.3] ${LABEL} mode=${MODE} endTime=${ENDT} IC=${IC_NAME}"
T0_WALL=$(date +%s)
"$CHEMBIN" > "${OUT}/log.chemFoam" 2>&1 || {
  echo "chemFoam FAILED — see ${OUT}/log.chemFoam"
  tail -80 "${OUT}/log.chemFoam" || true
  exit 1
}
T1_WALL=$(date +%s)
WALL=$(awk -v t0="$T0_WALL" -v t1="$T1_WALL" 'BEGIN{printf "%.3f", t1-t0}')
echo "WALL_SEC ${WALL}" | tee -a "${OUT}/log.chemFoam"

# Capture wall from log (time writes to stderr merged into log)
grep -E 'WALL_SEC|ExecutionTime|rlChemistryModel' "${OUT}/log.chemFoam" | tail -20 || true
cp -f chemFoam.out "${OUT}/" 2>/dev/null || true
cp -f constant/chemistryProperties constant/initialConditions "${OUT}/"
cp -f rl_decisions.csv "${OUT}/" 2>/dev/null || true
# Final T
FINAL_TDIR="$(ls -d [0-9]* 2>/dev/null | sort -g | tail -1 || true)"
if [[ -n "${FINAL_TDIR:-}" && -f "${FINAL_TDIR}/T" ]]; then
  mkdir -p "${OUT}/fields"
  cp -f "${FINAL_TDIR}/T" "${OUT}/fields/"
  cp -f "${FINAL_TDIR}/solverFlag" "${OUT}/fields/" 2>/dev/null || true
fi
echo "DONE ${LABEL} ${MODE} -> ${OUT}"
