#!/usr/bin/env bash
# Host launcher — E18 Stage 1 cold mix → freeze t=0.05 on Queen Bee.
#
#   source production/env.qb.sh
#   bash production/scripts/11_run_stage1_cold.sh
#
# If cases/opposedJet_E18 is incomplete, set E18_RECONFIGURE=1 to rebuild
# from opposedJet_2D via stage1_configure.sh (needs opposedJet_2D in tree).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CASE="$ROOT/cases/opposedJet_E18"
OUT="${E18_STAGE1_OUT:-$ROOT/production/runs/stage1_cold_$(date +%Y%m%d_%H%M%S)}"
NPROC="${NPROC:-${SLURM_NTASKS:-8}}"
ENDT="${E18_STAGE1_END:-0.05}"

mkdir -p "$OUT"
chmod +x "$ROOT/validation/zeroD/e18_prep/stage1_run_cold.sh"

if [[ "${E18_RECONFIGURE:-0}" == "1" ]] || [[ ! -f "$CASE/0/T" ]]; then
  echo "=== stage1_configure (rebuild opposedJet_E18 from opposedJet_2D) ==="
  bash "$ROOT/validation/zeroD/e18_prep/stage1_configure.sh"
fi

# Ensure cold chem-off + endTime even if case already exists
python3 - <<PY
from pathlib import Path
import re
case = Path(r"$CASE")
assert (case/"0/T").is_file(), f"missing IC: {case}/0/T"
cd = case/"system/controlDict"
t = cd.read_text()
for pat, rep in {
    r"endTime\s+[^;]+;": f"endTime         {float('$ENDT')};",
    r"startFrom\s+[^;]+;": "startFrom       startTime;",
    r"startTime\s+[^;]+;": "startTime       0;",
    r"application\s+[^;]+;": "application     reactingFoamDebug;",
    r"writeInterval\s+[^;]+;": "writeInterval   0.005;",
}.items():
    t2, n = re.subn(pat, rep, t, count=1)
    t = t2 if n else t
cd.write_text(t)
chem = case/"constant/chemistryProperties"
ct = re.sub(r"chemistry\s+[^;]+;", "chemistry       off;", chem.read_text(), count=1)
chem.write_text(ct)
print("Stage1 control: endTime=$ENDT chemistry off")
PY

# Patch Sutherland As/Ts if still zero (alphaEff bug)
python3 - <<PY
from pathlib import Path
import re
p = Path(r"$CASE") / "constant/thermo"
if not p.is_file():
    raise SystemExit("missing constant/thermo")
t = p.read_text()
t2, n1 = re.subn(r"(As\s+)0(\s*;)", r"\g<1>1.67212e-06\2", t)
t2, n2 = re.subn(r"(Ts\s+)0(\s*;)", r"\g<1>170.672\2", t2)
if n1 or n2:
    p.write_text(t2)
    print(f"patched Sutherland As/Ts zeros: As={n1} Ts={n2}")
else:
    print("Sutherland As/Ts look non-zero (OK)")
PY

export ROOT CASE OUT NPROC ENDT
export OF_RUNTIME="${OF_RUNTIME:-native}"
export OF_BASHRC="${OF_BASHRC:-/work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc}"
# Avoid second OpenFOAM bashrc source (common hang on interactive nodes)
export SKIP_OF_SOURCE=1

echo "OUT=$OUT NPROC=$NPROC ENDT=$ENDT CASE=$CASE"
if ! command -v reactingFoamDebug >/dev/null 2>&1; then
  echo "FATAL: reactingFoamDebug not on PATH — source production/env.qb.sh first" >&2
  exit 1
fi
bash "$ROOT/validation/zeroD/e18_prep/stage1_run_cold.sh"

# Verify freeze
FREEZE=$(python3 - <<PY
from pathlib import Path
case = Path(r"$CASE")
times = []
for p in case.iterdir():
    if not p.is_dir() or p.name in ("0","constant","system") or p.name.startswith("processor"):
        continue
    try:
        times.append((float(p.name), p.name))
    except ValueError:
        pass
if not times:
    raise SystemExit("No freeze time after Stage1")
times.sort()
print(times[-1][1])
PY
)
echo "FREEZE=$FREEZE" | tee "$OUT/freeze_time.txt"
test -f "$CASE/$FREEZE/T" || { echo "FATAL: $CASE/$FREEZE/T missing"; exit 1; }
echo "STAGE1_OK freeze=$CASE/$FREEZE"
echo "Next: bash production/scripts/20_run_chem.sh"
