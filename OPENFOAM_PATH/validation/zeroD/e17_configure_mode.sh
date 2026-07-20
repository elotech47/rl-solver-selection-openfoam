#!/usr/bin/env bash
# E17 — configure opposedJet_2D chemistry for cvodeOnly / qssOnly / rlAdaptive.
# Args: MODE
# MODE in {cvodeOnly,qssOnly,rlAdaptive}
# Call inside container or host (writes case files only).
#
# cvodeOnly / qssOnly use stock chemistryType.solver (no LibTorch).
# rlAdaptive uses method rl and requires policyRuntime + rlChemistryModel.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CASE="$ROOT/cases/opposedJet_2D"
MODE="${1:?mode}"

case "$MODE" in
  cvodeOnly|qssOnly|rlAdaptive) ;;
  *) echo "MODE must be cvodeOnly|qssOnly|rlAdaptive"; exit 2 ;;
esac

if [[ "$MODE" == "rlAdaptive" ]]; then
  cat > "$CASE/constant/chemistryProperties" <<EOF
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
    maxChemDeltaT       1e-6;
    dtRef               1e-6;
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
  want='libs            ( "libqssChemistrySolver.so" "libcvodeChemistrySolver.so" "libpolicyRuntime.so" "librlChemistryModel.so" );'
else
  # Stock path: works without LibTorch (E17.1 ignition scout).
  SOLVER=cvode
  [[ "$MODE" == "qssOnly" ]] && SOLVER=qss
  cat > "$CASE/constant/chemistryProperties" <<EOF
FoamFile
{
    version         2;
    format          ascii;
    class           dictionary;
    object          chemistryProperties;
}
chemistryType
{
    solver          ${SOLVER};
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
  want='libs            ( "libqssChemistrySolver.so" "libcvodeChemistrySolver.so" );'
fi

python3 - <<PY
from pathlib import Path
import re
p = Path(r"$CASE") / "system" / "controlDict"
t = p.read_text()
want = """$want"""
t2, n = re.subn(r"libs\s*\([^;]*\);", want, t, count=1)
if n == 0:
    raise SystemExit("libs line not found in controlDict")
p.write_text(t2)
print("controlDict libs updated for mode=$MODE")
PY

echo "Configured opposedJet_2D for mode=${MODE}"
