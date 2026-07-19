#!/usr/bin/env bash
# E13.1 OpenFOAM QSS single-step harness (one pinned state per invocation).
set +e
source /usr/lib/openfoam/openfoam2312/etc/bashrc
set -e

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CASE="${ROOT}/cases/chemFoam_0D"
E13="${ROOT}/validation/zeroD/e13_qss"
OUT_BASE="${E13}/of_runs"

export FOAM_USER_LIBBIN="${ROOT}/platforms/${WM_OPTIONS}/lib"
export FOAM_USER_APPBIN="${ROOT}/platforms/${WM_OPTIONS}/bin"
export WM_PROJECT_USER_DIR="${ROOT}"
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${ROOT}/opt/sundials-arm64/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"

# Save/restorable templates
CTRL_TMPL="${E13}/chemFoam_controlDict.template"
CHEM_TMPL="${E13}/chemFoam_chemistryProperties.template"
if [[ ! -f "${CTRL_TMPL}" ]]; then
  cp "${CASE}/system/controlDict" "${CTRL_TMPL}"
  cp "${CASE}/constant/chemistryProperties" "${CHEM_TMPL}"
fi

run_one() {
  local tag="$1"
  local ic="${E13}/of_ic/${tag}/initialConditions"
  local out="${OUT_BASE}/${tag}"
  if [[ ! -f "${ic}" ]]; then
    echo "Missing ${ic} — run e13_1_qss_step.py first" >&2
    return 1
  fi
  mkdir -p "${out}"
  cd "${CASE}"
  ./Allclean >/dev/null 2>&1 || true
  rm -rf 0/p 0/T 0/Y* 2>/dev/null || true

  cp -f "${ic}" constant/initialConditions

  # Restore templates then set QSS + 1 µs
  cp -f "${CTRL_TMPL}" system/controlDict
  cp -f "${CHEM_TMPL}" constant/chemistryProperties

  # chemistryType solver → qss
  sed -i "s/solver          [a-zA-Z0-9_]*/solver          qss/" constant/chemistryProperties
  # Only first solver line (chemistryType) - rewrite safely from known template
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
    solver          qss;
}
chemistry       on;
initialChemicalTimeStep 1e-07;
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
endTime         1e-06;
deltaT          1e-06;
writeControl    runTime;
writeInterval   1e-06;
purgeWrite      0;
writeFormat     ascii;
runTimeModifiable true;
adjustTimeStep  no;
maxDeltaT       1e-06;
libs            ( "libqssChemistrySolver.so" "libcvodeChemistrySolver.so" );
EOF

  export OFRL_DEBUG_STATE=1
  chemFoamDebug > "${out}/log.chemFoam" 2>&1 || true
  cp -f chemFoam.out "${out}/" 2>/dev/null || true
  cp -f e8_state.csv "${out}/" 2>/dev/null || true
  cp -f e8_crash_state.dat "${out}/" 2>/dev/null || true
  # Capture species from time dir if written
  if [[ -d 1e-06 ]]; then
    mkdir -p "${out}/fields"
    cp -f 1e-06/T "${out}/fields/" 2>/dev/null || true
    # sample a few species
    for sp in oh ho2 ch2o nc12h26; do
      cp -f "1e-06/${sp}" "${out}/fields/" 2>/dev/null || true
    done
  fi
  cp -f constant/chemistryProperties constant/initialConditions "${out}/"

  echo "DONE tag=${tag}"
  grep -E "End|FOAM FATAL|min/max|T =" "${out}/log.chemFoam" | tail -15 || true
  tail -3 "${out}/chemFoam.out" 2>/dev/null || true
}

if [[ "${1:-}" == "all" ]]; then
  for ic in "${E13}"/of_ic/*/initialConditions; do
    tag="$(basename "$(dirname "$ic")")"
    run_one "${tag}"
  done
else
  run_one "${1:?tag required (e.g. T1301 or all)}"
fi

# Restore MidT case defaults
cp -f "${ROOT}/validation/zeroD/e11_3/chemistryProperties.template" \
  "${CASE}/constant/chemistryProperties.template" 2>/dev/null || true
sed 's/__SOLVER__/cvode/' "${CASE}/constant/chemistryProperties.template" \
  > "${CASE}/constant/chemistryProperties" 2>/dev/null || true
