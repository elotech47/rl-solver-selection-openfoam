#!/usr/bin/env bash
# E18 Stage 1 — cold mixing (Docker /work or native HPC).
# Env: OUT, NPROC, ENDT, CASE, ROOT, OF_BASHRC (optional)
set -eo pipefail
: "${OUT:?}"
: "${NPROC:?}"
: "${ENDT:?}"

ROOT="${ROOT:-/work}"
OF_BASHRC="${OF_BASHRC:-/usr/lib/openfoam/openfoam2312/etc/bashrc}"
CASE="${CASE:-$ROOT/cases/opposedJet_E18}"
MODE=coldMix

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
foamDictionary system/controlDict -entry startTime -set 0 > /dev/null
foamDictionary system/decomposeParDict -entry numberOfSubdomains -set "$NPROC" > /dev/null

# Chemistry must stay OFF for Stage 1
foamDictionary constant/chemistryProperties -entry chemistry -set off > /dev/null 2>&1 || true

rm -rf processor* postProcessing 2>/dev/null || true
# Remove prior time dirs except 0 (keep IC)
find . -maxdepth 1 -type d \( -name '[1-9]*' -o -name '0.*' \) -exec rm -rf {} + 2>/dev/null || true

command -v reactingFoamDebug >/dev/null || {
  echo "FATAL: reactingFoamDebug missing — wmake applications/solvers/reactingFoam" >&2
  exit 1
}

# Mesh: rebuild if missing
if [[ ! -f constant/polyMesh/points ]]; then
  echo "=== blockMesh ==="
  blockMesh > "$OUT/log.blockMesh" 2>&1
else
  echo "=== polyMesh present — skip blockMesh (set E18_REMESH=1 to force) ==="
  if [[ "${E18_REMESH:-0}" == "1" ]]; then
    rm -rf constant/polyMesh
    blockMesh > "$OUT/log.blockMesh" 2>&1
  fi
fi
checkMesh > "$OUT/log.checkMesh" 2>&1 || true
grep -E 'cells:|Max cell|Mesh OK|Failed' "$OUT/log.checkMesh" | head -20 || true

echo "=== decomposePar ($NPROC) ==="
decomposePar -force > "$OUT/log.decomposePar" 2>&1

PROGRESS_AWK='
BEGIN { step=0; last_t=""; last_tmax=""; last_tmin=""; endt=ENVIRON["ENDT"]+0 }
/^Time = / { last_t=$3; next }
/^propSanity: T / {
  last_tmin=$3; last_tmax=$4
  if (step % 5 == 0)
    printf "propSanity t=%s T=%s..%s\n", last_t, $3, $4 > "/dev/stderr"
  next
}
/ClockTime = / {
  step++
  if (step % 10 == 0)
    printf "t=%s maxT=%s\n", last_t, last_tmax > "/dev/stderr"
  next
}
/janafThermo/ { next }
/^FOAM Warning/ { next }
/Solving for / { next }
/FATAL|Floating point|SIGFPE|Signal:/ { print > "/dev/stderr"; print; next }
/^End/ { print > "/dev/stderr"; print; next }
{ next }
'

echo "=== mpirun reactingFoamDebug -parallel (chem OFF) ===" | tee "$OUT/run_header.txt"
START=$(date +%s)
set +e
if [[ "${OF_RUNTIME:-native}" == "docker" ]]; then
  MPI=(mpirun --allow-run-as-root -np "$NPROC" --map-by core --bind-to core)
else
  MPI=(mpirun -np "$NPROC")
fi
"${MPI[@]}" reactingFoamDebug -parallel \
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

echo "=== reconstructPar (latest = freeze) ==="
reconstructPar -latestTime > "$OUT/log.reconstructPar" 2>&1 || reconstructPar > "$OUT/log.reconstructPar" 2>&1

# List freeze time
ls -d [0-9]* 0.* 2>/dev/null | sort -g | tee "$OUT/times.txt" || true

if [[ -d /work ]] && [[ "$ROOT" == "/work" ]]; then
  chown -R "$(stat -c '%u:%g' /work)" "$OUT" "$CASE" 2>/dev/null || true
fi

echo "STAGE1_COLD_DONE exit=0"
