#!/usr/bin/env bash
# Resume E17 smoke from a given mode (default: rlAdaptive) using existing BASE dir.
# Usage: E17_SMOKE_OUT=... E17_MODES="rlAdaptive" bash validation/zeroD/e17_remote/02b_smoke_resume.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
CASE="$ROOT/cases/opposedJet_2D"
KIT="$ROOT/validation/zeroD/e17_remote"
IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
PLATFORM="${OF_PLATFORM:-linux/amd64}"
NPROC="${NPROC:-16}"
ENDT="${E17_END_TIME:-5e-4}"
BASE="${E17_SMOKE_OUT:?set E17_SMOKE_OUT to existing smoke dir}"
[[ "$BASE" = /* ]] || BASE="$ROOT/$BASE"
MODES="${E17_MODES:-rlAdaptive}"

# Ensure ascii IO for readable fields
python3 - <<PY
from pathlib import Path
import re
p = Path("$CASE/system/controlDict")
t = p.read_text()
t = re.sub(r"writeFormat\s+[^;]+;", "writeFormat     ascii;", t, count=1)
t = re.sub(r"writeCompression\s+[^;]+;", "writeCompression off;", t, count=1)
t = re.sub(r"endTime\s+[^;]+;", f"endTime         {float('$ENDT')};", t, count=1)
t = re.sub(r"writeInterval\s+[^;]+;", "writeInterval   1e-05;", t, count=1)
p.write_text(t)
print("controlDict ascii/endTime patched")
PY

sed "s/numberOfSubdomains.*/numberOfSubdomains  ${NPROC};/" \
  "$KIT/decomposeParDict.template" > "$CASE/system/decomposeParDict"

for MODE in $MODES; do
  OUT="$BASE/${MODE}"
  mkdir -p "$OUT"
  echo "========== E17 resume MODE=$MODE OUT=$OUT ==========" | tee "$OUT/run_banner.txt"
  # Ensure host can write logs next to root-owned docker artifacts
  chmod -R u+rwX "$OUT" 2>/dev/null || true
  E17_CONTAINER_ROOT=/work bash "$ROOT/validation/zeroD/e17_configure_mode.sh" "$MODE"
  cp -f "$CASE/system/controlDict" "$CASE/constant/chemistryProperties" "$OUT/" 2>/dev/null || true
  # Sanity: policy paths must be container-visible
  if grep -q '/home/' "$CASE/constant/chemistryProperties"; then
    echo "FATAL: chemistryProperties still has host /home paths — fix E17_CONTAINER_ROOT"
    exit 2
  fi
  set +e
  docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work \
    -e MODE="$MODE" -e OUT="/work/${OUT#"$ROOT"/}" -e NPROC="$NPROC" -e ENDT="$ENDT" \
    "$IMAGE" \
    -lc 'test -f /work/policy/policy_manifest && test -f /work/policy/policy.ts
         bash /work/validation/zeroD/e17_remote/e17_smoke_run_one.sh'
  RC=$?
  set -e
  echo "MODE=$MODE docker_exit=$RC" | tee -a "$OUT/wall.txt" 2>/dev/null \
    || echo "MODE=$MODE docker_exit=$RC" > "$OUT/wall_host.txt"
  python3 "$KIT/e17_smoke_post_one.py" --run-dir "$OUT" --mode "$MODE" --end-time "$ENDT" || true
  export E17_OUT="$OUT"
  bash "$KIT/02_extract_results.sh" || true
  python3 "$KIT/03_preprocess.py" --run-dir "$OUT" --out-dir "$OUT/preprocess" || true
done

python3 "$KIT/e17_smoke_report.py" --base "$BASE" | tee "$BASE/smoke_report.txt"
echo "[E17 resume] DONE → $BASE"
