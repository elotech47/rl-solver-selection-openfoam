#!/usr/bin/env bash
# Rung (b): MidT hard-case single 1 µs step under CONFORM (Tfreeze=true).
# Runs OF-QSS and OF-CVODE from map IC T800_p10_phi1p0 (800 K / 10 atm / φ=1).
# Intended to run inside the OpenFOAM container (see e15_rung_b_midt_host.sh).
set -eo pipefail
set +eu
source /usr/lib/openfoam/openfoam2312/etc/bashrc
set -e
set +u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
echo "[rung_b] ROOT=$ROOT"
CASE="${ROOT}/cases/chemFoam_0D"
CONF="${ROOT}/validation/zeroD/e15_conformance"
IC="${CONF}/of_ics/T800_p10_phi1p0_initialConditions"
OUT_BASE="${CONF}/rung_b_midt"

export FOAM_USER_LIBBIN="${ROOT}/platforms/${WM_OPTIONS}/lib"
export FOAM_USER_APPBIN="${ROOT}/platforms/${WM_OPTIONS}/bin"
export WM_PROJECT_USER_DIR="${ROOT}"
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${ROOT}/opt/sundials-arm64/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"

CHEMBIN="$(ls -1 "${ROOT}"/platforms/*/bin/chemFoamDebug 2>/dev/null | head -1 || true)"
echo "[rung_b] CHEMBIN=$CHEMBIN WM_OPTIONS=$WM_OPTIONS"
test -n "$CHEMBIN" && test -x "$CHEMBIN" || { echo "FATAL missing chemFoamDebug under ${ROOT}/platforms"; ls -la "${ROOT}/platforms" || true; exit 2; }
test -f "$IC" || { echo "FATAL missing $IC"; exit 2; }

run_solver() {
  local solver="$1"
  local out="${OUT_BASE}/${solver}"
  mkdir -p "$out"
  cd "$CASE"
  ./Allclean >/dev/null 2>&1 || true
  rm -rf 0/p 0/T 0/Y* 2>/dev/null || true
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
    solver          ${solver};
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
  "$CHEMBIN" > "${out}/log.chemFoam" 2>&1 || true
  cp -f chemFoam.out "${out}/" 2>/dev/null || true
  cp -f e8_state.csv "${out}/" 2>/dev/null || true
  cp -f constant/chemistryProperties constant/initialConditions "${out}/"
  if [[ -d 1e-06 ]]; then
    mkdir -p "${out}/fields"
    cp -f 1e-06/T "${out}/fields/" 2>/dev/null || true
  fi
  echo "DONE solver=${solver}"
  tail -5 "${out}/chemFoam.out" 2>/dev/null || true
}

run_solver qss
run_solver cvode
echo "Rung (b) MidT artifacts under ${OUT_BASE}"
