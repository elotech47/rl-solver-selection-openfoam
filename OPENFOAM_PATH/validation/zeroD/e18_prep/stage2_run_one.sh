#!/usr/bin/env bash
# E18 Stage 2 — one chemistry mode from frozen Stage1 field.
# Works in Docker (/work) and native HPC (ROOT + OF_BASHRC set by env.qb.sh).
set -eo pipefail
: "${MODE:?}"
: "${OUT:?}"
: "${NPROC:?}"
: "${ENDT:?}"
: "${CASE:?}"
: "${FREEZE:?}"

# Defaults: container layout unless caller set ROOT / OF_BASHRC
ROOT="${ROOT:-/work}"
OF_BASHRC="${OF_BASHRC:-/usr/lib/openfoam/openfoam2312/etc/bashrc}"

set +eu
# shellcheck disable=SC1090
source "$OF_BASHRC"
set -e
set +u
# shellcheck disable=SC1091
source "$ROOT/tools/ofrl_container_env.sh"
set +u
export FOAM_USER_LIBBIN="${ROOT}/platforms/${WM_OPTIONS}/lib"
export FOAM_USER_APPBIN="${ROOT}/platforms/${WM_OPTIONS}/bin"
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${SUNDIALS_DIR}/lib:${LIBTORCH_DIR}/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"
export OFRL_PROP_SANITY=1

mkdir -p "$OUT"
cd "$CASE"

foamDictionary system/controlDict -entry endTime -set "$ENDT" > /dev/null
foamDictionary system/controlDict -entry startFrom -set startTime > /dev/null
foamDictionary system/controlDict -entry startTime -set "$FREEZE" > /dev/null
foamDictionary system/decomposeParDict -entry numberOfSubdomains -set "$NPROC" > /dev/null

# Drop processors only; keep freeze mesh + fields
rm -rf processor* postProcessing 2>/dev/null || true

test -f constant/polyMesh/points || { echo "FATAL: no polyMesh — Stage1 incomplete"; exit 1; }
test -d "$FREEZE" || { echo "FATAL: freeze dir $FREEZE missing"; exit 1; }
command -v reactingFoamDebug >/dev/null || {
  echo "FATAL: reactingFoamDebug not found on PATH"; exit 1;
}

echo "=== decomposePar from freeze=$FREEZE (NPROC=$NPROC) ==="
decomposePar -force -time "$FREEZE" > "$OUT/log.decomposePar" 2>&1 \
  || decomposePar -force > "$OUT/log.decomposePar" 2>&1

PROGRESS_AWK='
BEGIN { step=0; last_t=""; last_tmax=""; endt=ENVIRON["ENDT"]+0; warn_skip=0 }
/^Time = / { last_t=$3; next }
/^propSanity: T / {
  last_tmax=$4
  if (step % 20 == 0) {
    printf "propSanity t=%s Tmax=%s\n", last_t, last_tmax > "/dev/stderr"
    print
  }
  next
}
/^rlUsage / { print > "/dev/stderr"; print; next }
/^rlFallbackReasons / { print > "/dev/stderr"; print; next }
/ClockTime = / {
  step++
  if (step % 20 == 0) {
    printf "t=%s maxT=%s\n", last_t, last_tmax > "/dev/stderr"
    print
  }
  next
}
/janafThermo/ { warn_skip=3; next }
warn_skip > 0 { warn_skip--; next }
/^FOAM Warning/ { next }
/Solving for / { next }
/DILUPBiCGStab/ { next }
/GAMG:/ { next }
/smoothSolver:/ { next }
/FATAL|Floating point|SIGFPE|Signal:/ { print > "/dev/stderr"; print; next }
/^End/ { print > "/dev/stderr"; print; next }
/^Courant Number/ {
  if (step % 20 == 0) print
  next
}
{ next }
'

echo "=== mpirun reactingFoamDebug MODE=$MODE freeze=$FREEZE end=$ENDT ===" | tee "$OUT/run_header.txt"
START=$(date +%s)
set +e
# Slurm: use allocation; interactive: plain mpirun
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
  MPI_LAUNCH=(mpirun -np "$NPROC")
else
  MPI_LAUNCH=(mpirun -np "$NPROC")
  # Docker-only convenience flags (ignore failures on HPC)
  if [[ "${OF_RUNTIME:-}" == "docker" ]]; then
    MPI_LAUNCH=(mpirun --allow-run-as-root -np "$NPROC" --map-by core --bind-to core)
  fi
fi
"${MPI_LAUNCH[@]}" reactingFoamDebug -parallel \
  2>&1 \
  | ENDT="$ENDT" awk "$PROGRESS_AWK" \
  2> "$OUT/progress.${MODE}.log" \
  | tee "$OUT/log.${MODE}"
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
reconstructPar > "$OUT/log.reconstructPar" 2>&1 || true
if [[ -d /work ]] && [[ "$ROOT" == "/work" ]]; then
  chown -R "$(stat -c '%u:%g' /work)" "$OUT" "$CASE" 2>/dev/null || true
fi
echo "STAGE2_MODE_DONE mode=$MODE exit=0"
