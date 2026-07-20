#!/usr/bin/env bash
# E16.4 inside-container: OF rlAdaptive / cvodeOnly / qssOnly for one paper condition.
# Args: CID LABEL T0 P_ATM Z DT END_TIME MODE
# MODE in {rlAdaptive,cvodeOnly,qssOnly}
set -eo pipefail
set +eu
source /usr/lib/openfoam/openfoam2312/etc/bashrc
set -e
set +u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CID="${1:?cid}"
LABEL="${2:?label}"
T0="${3:?T0}"
PATM="${4:?p_atm}"
Z="${5:?Z}"
DT="${6:?dt}"
ENDT="${7:?endTime}"
MODE="${8:?mode}"

CASE="${ROOT}/cases/chemFoam_0D"
OUT="${ROOT}/validation/e16_parity/e16_4_runs/${CID}_${MODE}"
IC="${ROOT}/validation/e16_parity/e16_4_ics/${CID}_${LABEL}_initialConditions"
NUM_STEPS=20

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

# Window = CFD Δt = maxChemDeltaT = paper dt. QSS internal dtmax stays 1e-6 (paper).
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
    maxChemDeltaT       ${DT};
    dtRef               ${DT};
    numSteps            ${NUM_STEPS};
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
deltaT          ${DT};
writeControl    runTime;
writeInterval   ${ENDT};
purgeWrite      0;
writeFormat     ascii;
runTimeModifiable true;
adjustTimeStep  no;
maxDeltaT       ${DT};
libs
(
    "libqssChemistrySolver.so"
    "libcvodeChemistrySolver.so"
    "libpolicyRuntime.so"
    "librlChemistryModel.so"
);
EOF

echo "[e16.4] ${CID} ${LABEL} mode=${MODE} T0=${T0} p=${PATM}atm Z=${Z} dt=${DT} end=${ENDT} numSteps=${NUM_STEPS}"
T0_WALL=$(date +%s)
"$CHEMBIN" > "${OUT}/log.chemFoam" 2>&1 || {
  echo "chemFoam FAILED — see ${OUT}/log.chemFoam"
  tail -80 "${OUT}/log.chemFoam" || true
  exit 1
}
T1_WALL=$(date +%s)
WALL=$(awk -v t0="$T0_WALL" -v t1="$T1_WALL" 'BEGIN{printf "%.3f", t1-t0}')
echo "WALL_SEC ${WALL}" | tee -a "${OUT}/log.chemFoam"

# Meta header for postprocess
cat > "${OUT}/run_meta.json" <<META
{
  "id": "${CID}",
  "label": "${LABEL}",
  "mode": "${MODE}",
  "T0": ${T0},
  "p_atm": ${PATM},
  "Z": ${Z},
  "dt": ${DT},
  "t_end": ${ENDT},
  "maxChemDeltaT": ${DT},
  "num_steps": ${NUM_STEPS},
  "decision_interval_s": $(awk -v d="$DT" -v n="$NUM_STEPS" 'BEGIN{printf "%.12g", d*n}'),
  "wall_sec": ${WALL},
  "source": "handoff/configs/example_ndodecane.yaml"
}
META

grep -E 'WALL_SEC|ExecutionTime|rlChemistryModel' "${OUT}/log.chemFoam" | tail -20 || true
cp -f chemFoam.out "${OUT}/" 2>/dev/null || true
cp -f constant/chemistryProperties constant/initialConditions "${OUT}/"
cp -f rl_decisions.csv "${OUT}/" 2>/dev/null || true
FINAL_TDIR="$(ls -d [0-9]* 2>/dev/null | sort -g | tail -1 || true)"
if [[ -n "${FINAL_TDIR:-}" ]]; then
  mkdir -p "${OUT}/fields"
  for f in T solverFlag chemCpuTime; do
    [[ -f "${FINAL_TDIR}/${f}" ]] && cp -f "${FINAL_TDIR}/${f}" "${OUT}/fields/"
  done
fi
echo "DONE ${CID} ${MODE} -> ${OUT}"
