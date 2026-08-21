#!/usr/bin/env bash
# Production Stage-2 host launcher — chemistry restart into production/runs/.
#
# Queen Bee:
#   source production/env.qb.sh
#   export E18_MODES=cvodeOnly   # or rlAdaptive / qssOnly
#   bash production/scripts/20_run_chem.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CASE="$ROOT/cases/opposedJet_E18"
IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
PLATFORM="${OF_PLATFORM:-linux/amd64}"
RUNTIME="${OF_RUNTIME:-native}"
SIF="${OF_SIF:-}"
NPROC="${NPROC:-32}"
ENDT_REL="${E18_END_TIME:-0.009}"
WRITE_INT="${E18_WRITE_INTERVAL:-1e-05}"
BASE="${E18_PROD_OUT:-$ROOT/production/runs/e18_$(date +%Y%m%d_%H%M%S)}"
# Policy paths inside Foam dicts
POLICY_ROOT="${E17_CONTAINER_ROOT:-$ROOT}"
# shellcheck disable=SC2206
MODES=(${E18_MODES:-cvodeOnly})

mkdir -p "$BASE"
chmod +x "$ROOT/validation/zeroD/e18_prep/stage2_run_one.sh"
chmod +x "$ROOT/production/scripts/"*.sh 2>/dev/null || true

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
    raise SystemExit("No Stage1 time dirs — freeze missing under cases/opposedJet_E18")
times.sort()
print(times[-1][1])
PY
)
ENDT=$(python3 -c "print(float('$FREEZE') + float('$ENDT_REL'))")
{
  echo "freeze=$FREEZE chem_horizon=${ENDT_REL}s endTime=$ENDT BASE=$BASE"
  echo "modes=${MODES[*]} NPROC=$NPROC runtime=$RUNTIME"
  echo "git=$(git -C "$ROOT/.." rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "case=$CASE ROOT=$ROOT POLICY_ROOT=$POLICY_ROOT"
} | tee "$BASE/stage2_header.txt" "$BASE/MANIFEST.txt"
echo "$FREEZE" > "$BASE/freeze_time.txt"

run_one() {
  local mode="$1" mode_case="$2" out="$3"
  if [[ "$RUNTIME" == "native" ]]; then
    export MODE="$mode" OUT="$out" NPROC="$NPROC" ENDT="$ENDT" CASE="$mode_case" FREEZE="$FREEZE"
    export ROOT OF_BASHRC OF_RUNTIME
    bash "$ROOT/validation/zeroD/e18_prep/stage2_run_one.sh"
    return $?
  fi
  local rel_out="${out#"$ROOT"/}"
  local rel_case="${mode_case#"$ROOT"/}"
  local inner='bash /work/validation/zeroD/e18_prep/stage2_run_one.sh'
  if [[ "$RUNTIME" == "apptainer" || "$RUNTIME" == "singularity" ]]; then
    [[ -n "$SIF" && -f "$SIF" ]] || { echo "Set OF_SIF to Apptainer image" >&2; return 2; }
    apptainer exec --cleanenv --bind "$ROOT:/work" "$SIF" \
      /bin/bash -lc "export MODE=$mode OUT=/work/$rel_out NPROC=$NPROC ENDT=$ENDT CASE=/work/$rel_case FREEZE=$FREEZE ROOT=/work; $inner"
  else
    docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
      -v "$ROOT:/work" -w /work \
      -e MODE="$mode" \
      -e OUT="/work/$rel_out" \
      -e NPROC="$NPROC" \
      -e ENDT="$ENDT" \
      -e CASE="/work/$rel_case" \
      -e FREEZE="$FREEZE" \
      -e ROOT=/work \
      "$IMAGE" \
      -lc "$inner"
  fi
}

FAILED=()
for MODE in "${MODES[@]}"; do
  OUT="$BASE/$MODE"
  MODE_CASE="$BASE/case_$MODE"
  mkdir -p "$OUT"
  rm -rf "$MODE_CASE"
  mkdir -p "$MODE_CASE"
  cp -a --no-preserve=ownership "$CASE/constant" "$MODE_CASE/constant"
  cp -a --no-preserve=ownership "$CASE/system" "$MODE_CASE/system"
  cp -a --no-preserve=ownership "$CASE/0" "$MODE_CASE/0"
  cp -a --no-preserve=ownership "$CASE/$FREEZE" "$MODE_CASE/$FREEZE"

  E17_CONTAINER_ROOT="$POLICY_ROOT" \
    bash "$ROOT/validation/zeroD/e18_prep/stage2_configure_mode.sh" "$MODE" "$MODE_CASE"

  python3 - <<PY
from pathlib import Path
import re
case = Path(r"$MODE_CASE")
freeze, endt, wint = "$FREEZE", float("$ENDT"), float("$WRITE_INT")
cd = case/"system/controlDict"
t = cd.read_text()
for pat, rep in {
    r"startFrom\s+[^;]+;": "startFrom       startTime;",
    r"startTime\s+[^;]+;": f"startTime       {freeze};",
    r"endTime\s+[^;]+;": f"endTime         {endt};",
    r"writeInterval\s+[^;]+;": f"writeInterval   {wint};",
    r"writeControl\s+[^;]+;": "writeControl    adjustableRunTime;",
    r"purgeWrite\s+[^;]+;": "purgeWrite      0;",
    r"deltaT\s+[^;]+;": "deltaT          1e-6;",
    r"maxCo\s+[^;]+;": "maxCo           0.5;",
    r"maxDeltaT\s+[^;]+;": "maxDeltaT       1e-5;",
    r"adjustTimeStep\s+[^;]+;": "adjustTimeStep  yes;",
}.items():
    t2, n = re.subn(pat, rep, t, count=1)
    t = t2 if n else t
cd.write_text(t)
chem = case/"constant/chemistryProperties"
ct = re.sub(r"chemistry\s+[^;]+;", "chemistry       on;", chem.read_text(), count=1)
chem.write_text(ct)
comb = case/"constant/combustionProperties"
bt = re.sub(r"active\s+[^;]+;", "active           true;", comb.read_text(), count=1)
comb.write_text(bt)
print("configured", case, "mode=$MODE")
PY

  cp -f "$MODE_CASE/system/controlDict" "$MODE_CASE/constant/chemistryProperties" "$OUT/" || true

  set +e
  run_one "$MODE" "$MODE_CASE" "$OUT"
  RC=$?
  set -e
  if [[ "$RUNTIME" == "docker" ]]; then
    docker run --rm -v "$OUT:/out" -v "$MODE_CASE:/case" alpine \
      sh -c "chown -R $(id -u):$(id -g) /out /case" 2>/dev/null || true
  fi
  echo "MODE=$MODE runtime_exit=$RC" | tee -a "$OUT/wall.txt"
  [[ "$RC" -eq 0 ]] || FAILED+=("$MODE:$RC")
done

echo "BASE=$BASE"
if ((${#FAILED[@]})); then
  echo "FAILED=${FAILED[*]}" | tee "$BASE/failures.txt"
  exit 1
fi
echo "PROD_CHEM_DONE" | tee "$BASE/DONE.txt"
