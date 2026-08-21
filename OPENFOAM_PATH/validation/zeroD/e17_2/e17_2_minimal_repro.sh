#!/usr/bin/env bash
# E17.2 minimal repro: one 1e-6 chem window, QSS vs CVODE, ± Y_n2 poison.
# Expectation: CVODE fine on both; QSS on Y_n2=-1e-4 shows spurious ΔT / reject.
set -euo pipefail
# Script lives at OPENFOAM_PATH/validation/zeroD/e17_2/ → three levels up.
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
CASE="$ROOT/cases/chemFoam_0D"
IMG="${OF_IMAGE:-${OFR_IMAGE:-opencfd/openfoam-default:2312}}"
PLATFORM="${OF_PLATFORM:-linux/amd64}"
OUT="${E17_2_REPRO_OUT:-$HERE/repro_runs}"
mkdir -p "$OUT"

python3 "$HERE/e17_2_write_ics.py"

run_one() {
  local IC_DIR="$1" MODE="$2" TAG="$3"
  local RUN="$OUT/$TAG"
  mkdir -p "$RUN"
  rm -rf "$RUN/case"
  cp -a "$CASE/." "$RUN/case"
  cp -f "$IC_DIR/initialConditions" "$RUN/case/constant/initialConditions"

  # Short single-window chemFoam via rl method
  cat > "$RUN/case/constant/chemistryProperties" <<EOF
FoamFile
{
    version         2;
    format          ascii;
    class           dictionary;
    object          chemistryProperties;
}
chemistryType { solver ode; method rl; }
chemistry on;
initialChemicalTimeStep 1e-07;
rl
{
    mode                ${MODE};
    maxChemDeltaT       1e-6;
    dtRef               1e-6;
    numSteps            20;
    confidenceThreshold 0.6;
    manifest            "/work/policy/policy_manifest";
    torchScript         "/work/policy/policy.ts";
}
qssCoeffs
{
    epsmin 0.02; epsmax 100; dtmin 1e-12; dtmax 1e-06;
    abstol 1e-11; itermax 2; Tfreeze true;
}
cvodeCoeffs { relTol 1e-08; absTol 1e-12; maxSteps 100000; }
guardCoeffs
{
    enabled     true;
    epsY        1e-12;
    epsSumY     1e-3;
    dTmaxWindow 500;
    TminAccept  310;
    TmaxAccept  3400;
}
odeCoeffs { solver seulex; absTol 1e-12; relTol 1e-08; }
EOF

  # endTime = one chem window
  python3 - <<PY
from pathlib import Path
import re
p = Path("$RUN/case/system/controlDict")
t = p.read_text()
t = re.sub(r"endTime\s+[^;]+;", "endTime         1e-6;", t, count=1)
t = re.sub(r"deltaT\s+[^;]+;", "deltaT          1e-6;", t, count=1)
t = re.sub(r"writeInterval\s+[^;]+;", "writeInterval   1e-6;", t, count=1)
t = re.sub(r"stopAt\s+[^;]+;", "stopAt          endTime;", t, count=1)
libs = 'libs ( "libqssChemistrySolver.so" "libcvodeChemistrySolver.so" "libpolicyRuntime.so" "librlChemistryModel.so" );'
t2, n = re.subn(r"libs\s*\([^;]*\);", libs, t, count=1)
if n == 0:
    t2 = t.rstrip() + "\n" + libs + "\n"
p.write_text(t2)
print("patched controlDict for $TAG")
PY

  echo "=== $TAG ($MODE) ==="
  # Image default entrypoint is /openfoam/run (dash); bypass for bash.
  # OpenFOAM bashrc must NOT run under set -e (unset WM_* vars).
  set +e
  docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
    -v "$ROOT:/work" -w "/work/validation/zeroD/e17_2/repro_runs/$TAG/case" \
    -e MODE="$MODE" \
    "$IMG" -lc '
      set +eu
      source /usr/lib/openfoam/openfoam2312/etc/bashrc
      set -e
      set +u
      export ROOT=/work
      source /work/tools/ofrl_container_env.sh
      set +u
      echo "[repro] WM_PROJECT_DIR=$WM_PROJECT_DIR"
      echo "[repro] rebuilding rlChemistryModel..."
      if ! wmake -j"$(nproc)" /work/src/rlChemistryModel > /tmp/wmake_rl.out 2>&1; then
        echo "wmake FAILED"; tail -60 /tmp/wmake_rl.out; exit 2
      fi
      echo "[repro] wmake OK; running chemFoamDebug mode='"$MODE"'"
      set +e
      chemFoamDebug > log.chemFoam 2>&1
      RC=$?
      set -e
      echo "[repro] chemFoamDebug exit=$RC"
      grep -E "guards|rlChemistryModel|Time =|min/max\\(T\\)|propSanity|FOAM FATAL|Signal|End" log.chemFoam | tail -50 || true
      # Always surface FATAL/SIGFPE clearly
      if grep -q "FOAM FATAL\\|Floating point exception\\|Signal: Floating point" log.chemFoam; then
        echo "[repro] FAIL markers in log:"
        grep -n "FOAM FATAL\\|Floating point\\|Signal:" log.chemFoam | tail -20
      fi
      exit "$RC"
    ' 2>&1 | tee "$RUN/console.txt"
  DRC=${PIPESTATUS[0]}
  set -e
  echo "[host] docker_exit=$DRC" | tee -a "$RUN/console.txt"
  cp -f "$RUN/case/log.chemFoam" "$RUN/" 2>/dev/null || true
  if [[ ! -s "$RUN/console.txt" ]]; then
    echo "ERROR: empty docker console for $TAG (daemon/image issue?)" >&2
    exit 1
  fi
  # Continue remaining cases even if one fails (poisoned QSS may non-zero exit)
  return 0
}

# Pick first dumped cell
CELL=$(HERE="$HERE" python3 - <<'PY'
import json, os
from pathlib import Path
c = json.loads(Path(os.environ["HERE"], "near_front_cells.json").read_text())["cells"][0]
print(c["global_celli"])
PY
)
echo "Using celli=$CELL"

run_one "$HERE/ics/cell_${CELL}" cvodeOnly "cell${CELL}_cvode_clean"
run_one "$HERE/ics/cell_${CELL}" qssOnly   "cell${CELL}_qss_clean"
run_one "$HERE/ics/cell_${CELL}_Yn2neg" cvodeOnly "cell${CELL}_cvode_Yn2neg"
run_one "$HERE/ics/cell_${CELL}_Yn2neg" qssOnly   "cell${CELL}_qss_Yn2neg"

python3 - <<PY
from pathlib import Path
import re, json
out = Path("$OUT")
rows = []
for d in sorted(out.iterdir()):
    if not d.is_dir():
        continue
    log = d / "log.chemFoam"
    if not log.is_file():
        log = d / "case" / "log.chemFoam"
    text = log.read_text(errors="ignore") if log.is_file() else ""
    chem = d / "case" / "chemFoam.out"
    if not chem.is_file():
        chem = d / "chemFoam.out"
    T0 = None
    m = re.search(r"T\s+=\s+([0-9.eE+-]+)\s+\[K\]", text)
    if m:
        T0 = float(m.group(1))
    T1 = None
    if chem.is_file():
        lines = [l for l in chem.read_text().splitlines() if l.strip() and not l.startswith("#")]
        if lines:
            T1 = float(lines[-1].split()[1])
    fb = clip = flag = None
    for td in ("1e-06", "1e-6"):
        base = d / "case" / td
        if not base.is_dir():
            continue
        def _uf(name, base=base):
            p = base / name
            if not p.is_file():
                return None
            t = p.read_text()
            mm = re.search(r"internalField\s+uniform\s+([^\s;]+)", t)
            return float(mm.group(1)) if mm else None
        fb = _uf("qssFallbackCount")
        clip = _uf("yClipMass")
        flag = _uf("solverFlag")
        break
    # Real abort only — not the FOAM_SIGFPE trap banner
    sigfpe = bool(re.search(r"Signal:\s*Floating point exception", text))
    rows.append({
        "tag": d.name,
        "T0": T0,
        "T1": T1,
        "dT": (T1 - T0) if (T0 is not None and T1 is not None) else None,
        "yClipMass": clip,
        "qssFallbackCount": fb,
        "solverFlag": flag,
        "guards_seen": "rlChemistryModel: guards" in text,
        "FOAM_FATAL": "FOAM FATAL" in text,
        "SIGFPE": sigfpe,
        "End": bool(re.search(r"^End\b", text, re.M)),
    })
(out / "summary.json").write_text(json.dumps(rows, indent=2))
print(json.dumps(rows, indent=2))
print("See validation/zeroD/e17_2/MINIMAL_REPRO_RESULT.md for interpretation.")
PY
