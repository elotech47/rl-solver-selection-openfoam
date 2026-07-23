#!/usr/bin/env bash
# E18 Stage 1 — cold mixing run inside OpenFOAM container.
# Env: OUT, NPROC, ENDT, CASE (optional)
set -eo pipefail
: "${OUT:?}"
: "${NPROC:?}"
: "${ENDT:?}"
CASE="${CASE:-/work/cases/opposedJet_E18}"
MODE=coldMix

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
export OFRL_PROP_SANITY=1

mkdir -p "$OUT"
cd "$CASE"

# Ensure endTime matches host request
foamDictionary system/controlDict -entry endTime -set "$ENDT" > /dev/null
foamDictionary system/decomposeParDict -entry numberOfSubdomains -set "$NPROC" > /dev/null

rm -rf processor* postProcessing 2>/dev/null || true
find . -maxdepth 1 -type d \( -name '[1-9]*' -o -name '0.*' \) -exec rm -rf {} + 2>/dev/null || true

echo "=== wmake reactingFoamDebug (propSanity + mu/kappa) ==="
(
  cd /work/applications/solvers/reactingFoam
  wmake -j 4 > "$OUT/log.wmake" 2>&1
) || { echo "wmake FAILED"; tail -40 "$OUT/log.wmake"; exit 1; }
echo "wmake OK"

echo "=== blockMesh ==="
blockMesh > "$OUT/log.blockMesh" 2>&1
checkMesh > "$OUT/log.checkMesh" 2>&1 || true
grep -E 'cells:|Max cell|Mesh OK|Failed' "$OUT/log.checkMesh" | head -20 || true

echo "=== decomposePar ($NPROC) ==="
decomposePar -force > "$OUT/log.decomposePar" 2>&1

PROGRESS_AWK='
BEGIN { step=0; last_t=""; last_tmax=""; last_tmin=""; last_clock=""; endt=ENVIRON["ENDT"]+0 }
/^Time = / { last_t=$3; next }
/^propSanity: T / {
  last_tmin=$3; last_tmax=$4
  if (step % 5 == 0)
    printf "propSanity t=%s T=%s..%s alphaEff=%s..%s nPos=%s\n", last_t, $3, $4, $(NF-6), $(NF-5), $(NF) > "/dev/stderr"
  next
}
/ClockTime = / {
  clock=$NF; gsub(/s$/, "", clock)
  step++
  if (step % 10 == 0) {
    printf "t=%s maxT=%s clock=%s\n", last_t, last_tmax, clock > "/dev/stderr"
  }
  next
}
{ print }
'

echo "=== mpirun reactingFoamDebug -parallel (chem OFF) ===" | tee "$OUT/run_header.txt"
START=$(date +%s)
set +e
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
tail -30 "$OUT/progress.${MODE}.log" 2>/dev/null || true

if [[ "$RC" -ne 0 ]]; then
  echo "FATAL solver exit=$RC"
  exit "$RC"
fi

echo "=== reconstructPar ==="
reconstructPar -latestTime > "$OUT/log.reconstructPar" 2>&1 || reconstructPar > "$OUT/log.reconstructPar" 2>&1

# Ownership for host
chown -R "$(stat -c '%u:%g' /work)" "$OUT" "$CASE" 2>/dev/null || true

echo "STAGE1_COLD_DONE exit=0"
