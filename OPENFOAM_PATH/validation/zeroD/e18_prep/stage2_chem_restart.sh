#!/usr/bin/env bash
# E18 Stage 2 host launcher — chem restart, three solvers, endTime ~8–10 ms.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
CASE="$ROOT/cases/opposedJet_E18"
IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
PLATFORM="${OF_PLATFORM:-linux/amd64}"
NPROC="${NPROC:-8}"
ENDT_REL="${E18_END_TIME:-0.009}"   # chem horizon after freeze (~8–10 ms)
WRITE_INT="${E18_WRITE_INTERVAL:-1e-05}"
BASE="${E18_STAGE2_OUT:-$ROOT/validation/zeroD/e18_prep/stage2_chem_$(date +%Y%m%d_%H%M%S)}"
# shellcheck disable=SC2206
MODES=(${E18_MODES:-cvodeOnly qssOnly rlAdaptive})

mkdir -p "$BASE"
chmod +x "$ROOT/validation/zeroD/e18_prep/stage2_run_one.sh"

# Freeze = latest Stage1 time
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
    raise SystemExit("No Stage1 time dirs — freeze missing")
times.sort()
print(times[-1][1])
PY
)
ENDT=$(python3 -c "print(float('$FREEZE') + float('$ENDT_REL'))")
echo "$FREEZE" > "$BASE/freeze_time.txt"
echo "freeze=$FREEZE chem_horizon=${ENDT_REL}s endTime=$ENDT BASE=$BASE" | tee "$BASE/stage2_header.txt"

# Configure helper targeting a given case path
configure_mode() {
  local mode="$1" case_path="$2"
  CASE="$case_path" MODE="$mode" E17_CONTAINER_ROOT=/work \
  bash "$ROOT/validation/zeroD/e18_prep/stage2_configure_mode.sh" "$mode" "$case_path"
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

  configure_mode "$MODE" "$MODE_CASE"

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
  docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work \
    -e MODE="$MODE" \
    -e OUT="/work/${OUT#"$ROOT"/}" \
    -e NPROC="$NPROC" \
    -e ENDT="$ENDT" \
    -e CASE="/work/${MODE_CASE#"$ROOT"/}" \
    -e FREEZE="$FREEZE" \
    "$IMAGE" \
    -lc 'bash /work/validation/zeroD/e18_prep/stage2_run_one.sh'
  RC=$?
  set -e
  docker run --rm -v "$OUT:/out" -v "$MODE_CASE:/case" alpine \
    sh -c "chown -R $(id -u):$(id -g) /out /case" 2>/dev/null || true
  echo "MODE=$MODE docker_exit=$RC" | tee -a "$OUT/wall.txt"
  [[ "$RC" -eq 0 ]] || FAILED+=("$MODE:$RC")
done

echo "BASE=$BASE"
if ((${#FAILED[@]})); then
  echo "FAILED=${FAILED[*]}" | tee "$BASE/failures.txt"
  exit 1
fi
echo "STAGE2_ALL_DONE" | tee "$BASE/DONE.txt"
