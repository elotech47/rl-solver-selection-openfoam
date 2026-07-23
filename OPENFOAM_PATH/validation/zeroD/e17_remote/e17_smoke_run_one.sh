#!/usr/bin/env bash
# E17 full three-mode smoke — one mode (inside OpenFOAM container).
# Env: MODE, OUT, NPROC, ENDT, CASE
# Quiet progress: awk filter (no python required in OF image).
set -eo pipefail
: "${MODE:?}"
: "${OUT:?}"
: "${NPROC:?}"
: "${ENDT:?}"
CASE="${CASE:-/work/cases/opposedJet_2D}"

# OpenFOAM bashrc references unset WM_PROJECT_SITE under set -u
set +eu
source /usr/lib/openfoam/openfoam2312/etc/bashrc
set -e
set +u
export ROOT=/work
# shellcheck disable=SC1091
source /work/tools/ofrl_container_env.sh
set +u
export FOAM_USER_LIBBIN=/work/platforms/${WM_OPTIONS}/lib
export FOAM_USER_APPBIN=/work/platforms/${WM_OPTIONS}/bin
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${SUNDIALS_DIR}/lib:${LIBTORCH_DIR}/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"

mkdir -p "$OUT"
cd "$CASE"
rm -rf processor* [1-9]* 0.[0-9]* postProcessing 2>/dev/null || true

trap 'echo "[${MODE}] SIGINT → stopAt writeNow"; foamDictionary system/controlDict -entry stopAt -set writeNow 2>/dev/null || true' INT TERM

echo "=== blockMesh ==="
blockMesh > "$OUT/log.blockMesh" 2>&1
echo "=== decomposePar ($NPROC scotch) ==="
decomposePar -force > "$OUT/log.decomposePar" 2>&1
test -f processor0/0/p || { echo "FATAL decomposePar"; exit 1; }

PROGRESS_AWK='
BEGIN { step=0; last_t=""; last_tmax=""; last_clock=""; endt=ENVIRON["ENDT"]+0 }
/^Time = / { last_t=$3; next }
/min\/max\(T\) = / {
  split($0, a, ", ");
  split(a[2], b, " ");
  last_tmax=b[1];
  next
}
/^propSanity: T / {
  if (step % 10 == 0)
    printf "propSanity t=%s Tint=%s Tmax=%s\n", last_t, $3, $4 > "/dev/stderr"
  next
}
/^rlUsage / {
  print > "/dev/stderr"
  next
}
/^Writing field / {
  printf "WROTE t=%s field=%s\n", $6, $3 > "/dev/stderr"
  next
}
/ClockTime = / {
  clock=$NF; gsub(/s$/, "", clock)
  step++
  if (step % 20 == 0) {
    dt=0
    if (last_clock != "") dt = clock - last_clock
    last_clock=clock
    eta=""
    if (dt > 0 && last_t+0 > 0) {
      rem = endt - (last_t+0)
      if (rem < 0) rem=0
      eta_m = rem * dt / (last_t+0) / 60
      eta = sprintf(" ETA=%.1fm", eta_m)
    }
    printf "t=%s dt=%.4gs maxT=%s s/step=%.3g%s\n", last_t, dt, last_tmax, dt, eta > "/dev/stderr"
  } else {
    last_clock=clock
  }
  next
}
{ print }
'

echo "=== mpirun reactingFoamDebug -parallel ===" | tee "$OUT/run_header.txt"
START=$(date +%s)
set +e
# Full solver log → log.<mode>; quiet progress → progress.<mode>.log (stderr of awk)
mpirun --allow-run-as-root -np "$NPROC" --map-by core --bind-to core \
  reactingFoamDebug -parallel \
  2>&1 \
  | tee "$OUT/log.${MODE}" \
  | ENDT="$ENDT" awk "$PROGRESS_AWK" \
  2> "$OUT/progress.${MODE}.log"
RC=${PIPESTATUS[0]}
set -e
END=$(date +%s)
echo "wall_s=$((END-START)) exit=$RC" | tee "$OUT/wall.txt"
# Mirror last progress lines to stdout for host tee
tail -20 "$OUT/progress.${MODE}.log" 2>/dev/null || true

echo "=== reconstructPar (all write times) ==="
reconstructPar > "$OUT/log.reconstructPar" 2>&1 || true

cp -f system/controlDict constant/chemistryProperties system/decomposeParDict "$OUT/" 2>/dev/null || true
cp -f 0/T 0/U 0/e17_kernel_meta.txt "$OUT/" 2>/dev/null || true
cp -f e12_prop_sanity.csv "$OUT/" 2>/dev/null || true
cp -f rl_usage_step.csv "$OUT/" 2>/dev/null || true
# Parallel: decisions land in processor*/rl_decisions.csv — merge to OUT
if ls processor*/rl_decisions.csv >/dev/null 2>&1; then
  {
    head -1 "$(ls processor*/rl_decisions.csv | head -1)"
    for f in processor*/rl_decisions.csv; do
      # skip header on each
      tail -n +2 "$f"
    done
  } > "$OUT/rl_decisions.csv"
elif [[ -f rl_decisions.csv ]]; then
  cp -f rl_decisions.csv "$OUT/"
fi

mkdir -p "$OUT/fields"
for td in $(ls -d [0-9]* 2>/dev/null | sort -g); do
  [[ "$td" == "0" ]] && continue
  mkdir -p "$OUT/fields/$td"
  for f in T OH solverFlag chemCpuTime qssFallbackCount yClipMass; do
    [[ -f "$td/$f" ]] && cp -f "$td/$f" "$OUT/fields/$td/"
  done
done
ls -d [0-9]* 2>/dev/null | sort -g | tail -1 > "$OUT/latest_time.txt" || true

# E17.2 usage: CVODE-equivalent = solverFlag==0 OR qssFallbackCount increments
if [[ -f "$OUT/rl_decisions.csv" ]] || ls "$OUT/fields"/*/qssFallbackCount >/dev/null 2>&1; then
  OUT="$OUT" python3 - <<'PY' || true
import os, json, re
from pathlib import Path
out = Path(os.environ["OUT"])
latest = (out/"latest_time.txt").read_text().strip() if (out/"latest_time.txt").is_file() else ""
fb_path = out/"fields"/latest/"qssFallbackCount" if latest else None
summary = {"latest_time": latest}
if fb_path and fb_path.is_file():
    t = fb_path.read_text()
    m = re.search(r"internalField\s+uniform\s+([^\s;]+)", t)
    if m:
        summary["fallback_uniform"] = float(m.group(1))
    else:
        m = re.search(r"internalField\s+nonuniform\s+List<scalar>\s*\n\s*(\d+)\s*\n\s*\((.*?)\)", t, re.S)
        if m:
            vals=[float(x) for x in m.group(2).split()]
            summary["fallback_total"] = sum(vals)
            summary["fallback_cells_gt0"] = sum(v>0 for v in vals)
            summary["fallback_max"] = max(vals)
            summary["n_cells"] = len(vals)
sf = out/"fields"/latest/"solverFlag" if latest else None
if sf and sf.is_file():
    t = sf.read_text()
    m = re.search(r"internalField\s+uniform\s+([^\s;]+)", t)
    if m:
        summary["solverFlag_uniform"] = float(m.group(1))
    else:
        m = re.search(r"internalField\s+nonuniform\s+List<scalar>\s*\n\s*(\d+)\s*\n\s*\((.*?)\)", t, re.S)
        if m:
            vals=[float(x) for x in m.group(2).split()]
            n0=sum(v<0.5 for v in vals); n1=len(vals)-n0
            summary["solverFlag_CVODE"] = n0
            summary["solverFlag_QSS"] = n1
(out/"e17_2_usage.json").write_text(json.dumps(summary, indent=2))
print("e17_2_usage:", summary)
PY
fi

exit "$RC"
