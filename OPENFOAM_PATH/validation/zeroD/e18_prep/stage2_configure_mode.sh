#!/usr/bin/env bash
# E17 — configure opposedJet_2D chemistry for cvodeOnly / qssOnly / rlAdaptive.
#
# E17.2 mode meanings (CFD):
#   cvodeOnly  — force CVODE (guards still sanitize inputs)
#   qssOnly    — QSS + Layer-1/2 guards with CVODE fallback (reported)
#   rlAdaptive — policy + same guards; fallback counts as CVODE usage
#
# Unguarded stock QSS (chemistryType.solver=qss) is RETIRED for CFD.
# 0D chemFoam may still use stock qss for algorithm studies.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CASE="${2:-$ROOT/cases/opposedJet_E18}"
MODE="${1:?mode}"
CONTAINER_ROOT="${E17_CONTAINER_ROOT:-/work}"

case "$MODE" in
  cvodeOnly|qssOnly|rlAdaptive) ;;
  *) echo "MODE must be cvodeOnly|qssOnly|rlAdaptive"; exit 2 ;;
esac

if [[ "${E17_STOCK:-0}" == "1" ]]; then
  echo "ERROR: E17_STOCK=1 retired for CFD (E17.2). Unguarded QSS is 0D-only." >&2
  echo "Use method rl with guardCoeffs (default ON)." >&2
  exit 2
fi

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
    mode                ${MODE};
    maxChemDeltaT       1e-6;
    dtRef               1e-6;
    numSteps            20;
    confidenceThreshold 0.6;
    manifest            "${CONTAINER_ROOT}/policy/policy_manifest";
    torchScript         "${CONTAINER_ROOT}/policy/policy.ts";
    logUsage            true;
    logDecisions        false;
    logFallbackReasons  true;
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
guardCoeffs
{
    enabled         true;
    epsY            1e-8;
    epsSumY         1e-2;
    dTmaxWindow     500;
    TminAccept      250;
    TmaxAccept      3400;
}
odeCoeffs
{
    solver          seulex;
    absTol          1e-12;
    relTol          1e-08;
}
EOF

want='libs            ( "libqssChemistrySolver.so" "libcvodeChemistrySolver.so" "libpolicyRuntime.so" "librlChemistryModel.so" );'

python3 - <<PY
from pathlib import Path
import re
p = Path(r"$CASE") / "system" / "controlDict"
t = p.read_text()
want = """$want"""
t2, n = re.subn(r"libs\s*\([^;]*\);", want, t, count=1)
if n == 0:
    raise SystemExit("libs line not found in controlDict")
t = t2
# Quiet solver + suppress redundant foam chatter in production chem runs
if "DebugSwitches" not in t:
    t += """
DebugSwitches
{
    SolverPerformance 0;
}
"""
else:
    if "SolverPerformance" not in t:
        t = t.replace(
            "DebugSwitches\n{",
            "DebugSwitches\n{\n    SolverPerformance 0;",
        )
# Less frequent propSanity spam
t2, n = re.subn(r"propSanityInterval\s+[^;]+;", "propSanityInterval 50;", t, count=1)
t = t2 if n else t
p.write_text(t)
print("controlDict libs + quiet switches for mode=$MODE")
PY

echo "Configured opposedJet_E18 for mode=${MODE} (guards ON, policy root=${CONTAINER_ROOT})"
