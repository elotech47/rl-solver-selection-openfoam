#!/usr/bin/env bash
# Resume E18 Stage2 remaining modes after cvodeOnly (or any finished mode).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
BASE="${1:?stage2 base dir}"
FREEZE=$(cat "$BASE/freeze_time.txt")
ENDT_REL="${E18_END_TIME:-0.003}"
ENDT=$(python3 -c "print(round(float('$FREEZE') + float('$ENDT_REL'), 6))")
NPROC="${NPROC:-8}"
IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
PLATFORM="${OF_PLATFORM:-linux/amd64}"
# shellcheck disable=SC2206
MODES=(${E18_MODES:-qssOnly rlAdaptive})
WRITE_INT="${E18_WRITE_INTERVAL:-5e-05}"

echo "resume BASE=$BASE FREEZE=$FREEZE ENDT=$ENDT modes=${MODES[*]}"

for MODE in "${MODES[@]}"; do
  if [[ -f "$BASE/$MODE/wall.txt" ]] && grep -q 'exit=0' "$BASE/$MODE/wall.txt"; then
    echo "skip $MODE (already exit=0)"
    continue
  fi
  OUT="$BASE/$MODE"
  MODE_CASE="$BASE/case_$MODE"
  mkdir -p "$OUT"
  rm -rf "$MODE_CASE"
  mkdir -p "$MODE_CASE"
  CASE_SRC="$ROOT/cases/opposedJet_E18"
  cp -a --no-preserve=ownership "$CASE_SRC/constant" "$MODE_CASE/constant"
  cp -a --no-preserve=ownership "$CASE_SRC/system" "$MODE_CASE/system"
  cp -a --no-preserve=ownership "$CASE_SRC/0" "$MODE_CASE/0"
  cp -a --no-preserve=ownership "$CASE_SRC/$FREEZE" "$MODE_CASE/$FREEZE"

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
}.items():
    t2, n = re.subn(pat, rep, t, count=1)
    t = t2 if n else t
cd.write_text(t)
chem = case/"constant/chemistryProperties"
chem.write_text(re.sub(r"chemistry\s+[^;]+;", "chemistry       on;", chem.read_text(), count=1))
comb = case/"constant/combustionProperties"
comb.write_text(re.sub(r"active\s+[^;]+;", "active           true;", comb.read_text(), count=1))
print("ready", case)
PY
  cp -f "$MODE_CASE/system/controlDict" "$MODE_CASE/constant/chemistryProperties" "$OUT/" || true

  set +e
  docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work \
    -e MODE="$MODE" -e OUT="/work/${OUT#"$ROOT"/}" -e NPROC="$NPROC" -e ENDT="$ENDT" \
    -e CASE="/work/${MODE_CASE#"$ROOT"/}" -e FREEZE="$FREEZE" \
    "$IMAGE" \
    -lc 'bash /work/validation/zeroD/e18_prep/stage2_run_one.sh'
  RC=$?
  set -e
  docker run --rm -v "$OUT:/out" -v "$MODE_CASE:/case" alpine \
    sh -c "chown -R $(id -u):$(id -g) /out /case" 2>/dev/null || true
  echo "MODE=$MODE docker_exit=$RC" | tee -a "$OUT/wall.txt"
  [[ "$RC" -eq 0 ]] || exit "$RC"
done
echo "RESUME_DONE" | tee "$BASE/RESUME_DONE.txt"
