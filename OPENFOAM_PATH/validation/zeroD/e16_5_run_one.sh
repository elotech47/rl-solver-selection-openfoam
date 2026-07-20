#!/usr/bin/env bash
# E16.5 inside-container: MidT rlAdaptive with fixed or synthetic CFD Δt.
# Args: TAG  MODE_DT
#   TAG     = output subdirectory name (e.g. fixed_ref | synth_dt)
#   MODE_DT = fixed | synth
set -eo pipefail
set +eu
source /usr/lib/openfoam/openfoam2312/etc/bashrc
set -e
set +u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TAG="${1:?tag}"
MODE_DT="${2:?fixed|synth}"

# MidT paper condition (C2), short horizon — enough decisions for the clock gate
T0=800
PATM=10
Z=0.062
DT_REF=1e-6
NUM_STEPS=20
# ~40 decision intervals → chemTime ~ 8e-4 s
ENDT_FIXED=8e-4
# synth: Time advances by DT_REF each CFD step while chemistry uses schedule;
# need more CFD steps so chemTime reaches ~ENDT_FIXED
ENDT_SYNTH=1.5e-3

CASE="${ROOT}/cases/chemFoam_0D"
OUT="${ROOT}/validation/e16_parity/e16_5_runs/${TAG}"
IC="${ROOT}/validation/e16_parity/e16_4_ics/C2_MidT_MidP_initialConditions"

export FOAM_USER_LIBBIN="${ROOT}/platforms/${WM_OPTIONS}/lib"
export FOAM_USER_APPBIN="${ROOT}/platforms/${WM_OPTIONS}/bin"
source "${ROOT}/tools/ofrl_container_env.sh"

CHEMBIN="$(ls -1 "${ROOT}"/platforms/*/bin/chemFoamDebug 2>/dev/null | head -1 || true)"
test -n "$CHEMBIN" && test -x "$CHEMBIN" || { echo "FATAL missing chemFoamDebug"; exit 2; }
test -f "$IC" || { echo "FATAL missing $IC — run e16_4_write_ics.py --all"; exit 2; }
test -f "${ROOT}/policy/policy.ts" || { echo "FATAL missing policy.ts"; exit 2; }
test -f "${ROOT}/policy/policy_manifest" || { echo "FATAL missing policy_manifest"; exit 2; }
test -f "${FOAM_USER_LIBBIN}/librlChemistryModel.so" || { echo "FATAL missing librlChemistryModel.so"; exit 2; }

mkdir -p "$OUT"
cd "$CASE"
./Allclean >/dev/null 2>&1 || true
rm -rf 0/p 0/T 0/Y* rl_decisions.csv 2>/dev/null || true
cp -f "$IC" constant/initialConditions

SCHEDULE_BLOCK=""
ENDT="$ENDT_FIXED"
if [[ "$MODE_DT" == "synth" ]]; then
  # Path-identical to fixed 1e-6 micro-windows: CFD Δt varies but each solve
  # sub-cycles into maxChemDeltaT=dtRef chunks (2+1+3 = 6 windows / period).
  SCHEDULE_BLOCK="    testDeltaTSchedule (2e-6 1e-6 3e-6);"
  ENDT="$ENDT_SYNTH"
elif [[ "$MODE_DT" == "synth_irregular" ]]; then
  # User-requested irregular steps (includes Δt < dtRef). Clock spacing only;
  # free-run flags need not match (integrator path dependence).
  SCHEDULE_BLOCK="    testDeltaTSchedule (1e-6 2e-7 5e-7);"
  ENDT="$ENDT_SYNTH"
fi

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
    mode                rlAdaptive;
    maxChemDeltaT       ${DT_REF};
    dtRef               ${DT_REF};
    numSteps            ${NUM_STEPS};
    confidenceThreshold 0.6;
    manifest            "${ROOT}/policy/policy_manifest";
    torchScript         "${ROOT}/policy/policy.ts";
${SCHEDULE_BLOCK}
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
deltaT          ${DT_REF};
writeControl    runTime;
writeInterval   ${ENDT};
purgeWrite      0;
writeFormat     ascii;
runTimeModifiable true;
adjustTimeStep  no;
maxDeltaT       ${DT_REF};
libs
(
    "libqssChemistrySolver.so"
    "libcvodeChemistrySolver.so"
    "libpolicyRuntime.so"
    "librlChemistryModel.so"
);
EOF

echo "[e16.5] tag=${TAG} mode_dt=${MODE_DT} dtRef=${DT_REF} numSteps=${NUM_STEPS} end=${ENDT}"
T0_WALL=$(date +%s)
"$CHEMBIN" > "${OUT}/log.chemFoam" 2>&1 || {
  echo "chemFoam FAILED — see ${OUT}/log.chemFoam"
  tail -80 "${OUT}/log.chemFoam" || true
  exit 1
}
T1_WALL=$(date +%s)
WALL=$(awk -v t0="$T0_WALL" -v t1="$T1_WALL" 'BEGIN{printf "%.3f", t1-t0}')
echo "WALL_SEC ${WALL}" | tee -a "${OUT}/log.chemFoam"

cat > "${OUT}/run_meta.json" <<META
{
  "tag": "${TAG}",
  "mode_dt": "${MODE_DT}",
  "T0": ${T0},
  "p_atm": ${PATM},
  "Z": ${Z},
  "dt_ref": ${DT_REF},
  "num_steps": ${NUM_STEPS},
  "tau_dec": $(awk -v d="$DT_REF" -v n="$NUM_STEPS" 'BEGIN{printf "%.12g", d*n}'),
  "t_end": ${ENDT},
  "wall_sec": ${WALL}
}
META

cp -f chemFoam.out "${OUT}/" 2>/dev/null || true
cp -f constant/chemistryProperties constant/initialConditions "${OUT}/"
cp -f rl_decisions.csv "${OUT}/" 2>/dev/null || true
grep -E 'WALL_SEC|tauDec|dtRef|testDeltaT|Warning' "${OUT}/log.chemFoam" | tail -30 || true
echo "DONE ${TAG} -> ${OUT}"
