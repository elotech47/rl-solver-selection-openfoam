#!/usr/bin/env bash
# E18 Stage 1 — cold mixing (Docker /work or native HPC).
# Env: OUT, NPROC, ENDT, CASE, ROOT, OF_BASHRC (optional)
#
# If you already `source production/env.qb.sh`, SKIP_OF_SOURCE=1 (set by
# 11_run_stage1_cold.sh) avoids a second bashrc source hang.
set -eo pipefail
: "${OUT:?}"
: "${NPROC:?}"
: "${ENDT:?}"

ROOT="${ROOT:-/work}"
OF_BASHRC="${OF_BASHRC:-/usr/lib/openfoam/openfoam2312/etc/bashrc}"
CASE="${CASE:-$ROOT/cases/opposedJet_E18}"
MODE=coldMix

mkdir -p "$OUT"
LOG="$OUT/run.log"
log() { echo "$(date -Is) $*" | tee -a "$LOG"; }
log "stage1_run_cold START CASE=$CASE NPROC=$NPROC ENDT=$ENDT"

# Prefer already-loaded interactive env
if [[ "${SKIP_OF_SOURCE:-}" == "1" ]] \
  || { [[ -n "${WM_PROJECT_DIR:-}" ]] && command -v reactingFoamDebug >/dev/null 2>&1; }; then
  log "skip OpenFOAM bashrc (already loaded)"
  set +u
  # shellcheck disable=SC1091
  source "$ROOT/tools/ofrl_container_env.sh" || true
  set +u
else
  log "sourcing OF_BASHRC=$OF_BASHRC"
  [[ -f "$OF_BASHRC" ]] || { echo "FATAL: missing $OF_BASHRC"; exit 1; }
  set +eu
  # shellcheck disable=SC1090
  source "$OF_BASHRC"
  set -e
  set +u
  # shellcheck disable=SC1091
  source "$ROOT/tools/ofrl_container_env.sh"
  set +u
fi

export FOAM_USER_LIBBIN="${ROOT}/platforms/${WM_OPTIONS}/lib"
export FOAM_USER_APPBIN="${ROOT}/platforms/${WM_OPTIONS}/bin"
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${SUNDIALS_DIR}/lib:${LIBTORCH_DIR}/lib:${LD_LIBRARY_PATH:-}"
export PATH="${FOAM_USER_APPBIN}:${PATH}"
export OFRL_PROP_SANITY=1

cd "$CASE"
log "cwd=$(pwd)"

log "patch controlDict / chem (python)"
python3 - <<PY
from pathlib import Path
import re
case = Path(".")
end = float("$ENDT")
nproc = int("$NPROC")
cd = case / "system/controlDict"
t = cd.read_text()
for pat, rep in [
    (r"endTime\s+[^;]+;", f"endTime         {end};"),
    (r"startFrom\s+[^;]+;", "startFrom       startTime;"),
    (r"startTime\s+[^;]+;", "startTime       0;"),
]:
    t, _ = re.subn(pat, rep, t, count=1)
cd.write_text(t)
dp = case / "system/decomposeParDict"
if dp.is_file():
    t = re.sub(r"numberOfSubdomains\s+[^;]+;", f"numberOfSubdomains {nproc};", dp.read_text(), count=1)
    dp.write_text(t)
chem = case / "constant/chemistryProperties"
if chem.is_file():
    t = re.sub(r"chemistry\s+[^;]+;", "chemistry       off;", chem.read_text(), count=1)
    chem.write_text(t)
print("patched OK")
PY

log "clean processor* / old time dirs"
rm -rf processor* postProcessing 2>/dev/null || true
for d in [1-9]* 0.[0-9]*; do
  [[ -d "$d" ]] || continue
  log "  rm -rf $d"
  rm -rf "$d"
done

command -v reactingFoamDebug >/dev/null || {
  echo "FATAL: reactingFoamDebug missing — wmake applications/solvers/reactingFoam" >&2
  exit 1
}
log "reactingFoamDebug=$(command -v reactingFoamDebug)"

# LibTorch LD_PRELOAD aborts checkMesh / decomposePar / reconstructPar on native HPC
_foam_util() {
  env -u LD_PRELOAD "$@"
}

if [[ ! -f constant/polyMesh/points ]]; then
  log "=== blockMesh ==="
  _foam_util blockMesh > "$OUT/log.blockMesh" 2>&1
else
  log "polyMesh present — skip blockMesh (E18_REMESH=1 to force)"
  if [[ "${E18_REMESH:-0}" == "1" ]]; then
    rm -rf constant/polyMesh
    _foam_util blockMesh > "$OUT/log.blockMesh" 2>&1
  fi
fi
log "=== checkMesh ==="
_foam_util checkMesh > "$OUT/log.checkMesh" 2>&1 || true
grep -E 'cells:|Max cell|Mesh OK|Failed' "$OUT/log.checkMesh" | head -20 || true

log "=== decomposePar ($NPROC) ==="
if ! _foam_util decomposePar -force > "$OUT/log.decomposePar" 2>&1; then
  echo "FATAL: decomposePar failed — see $OUT/log.decomposePar" >&2
  tail -40 "$OUT/log.decomposePar" >&2 || true
  exit 1
fi
log "decomposePar done"

log "=== mpirun reactingFoamDebug -parallel (chem OFF) ==="
# Stage1 is chem-off: do NOT LD_PRELOAD LibTorch (8 ranks × torch ≈ OOM / SIGPIPE on interactive nodes)
unset LD_PRELOAD
START=$(date +%s)
set +e
if [[ "${OF_RUNTIME:-native}" == "docker" ]]; then
  MPI=(mpirun --allow-run-as-root -np "$NPROC" --map-by core --bind-to core)
else
  MPI=(mpirun -np "$NPROC")
fi

# Direct log — do not pipe through awk (OOM → "Killed" → solver exit 141 SIGPIPE)
: > "$OUT/progress.${MODE}.log"
(
  # light progress sampler; dies with solver when log stops growing
  while true; do
    sleep 30
    [[ -f "$OUT/log.${MODE}" ]] || continue
    # last Time= and propSanity if present
    tline=$(grep -E '^Time = |^propSanity: T |^End' "$OUT/log.${MODE}" 2>/dev/null | tail -3 || true)
    [[ -n "$tline" ]] && echo "$(date -Is) $tline" >> "$OUT/progress.${MODE}.log"
  done
) &
PROG_PID=$!

"${MPI[@]}" reactingFoamDebug -parallel > "$OUT/log.${MODE}" 2>&1
RC=$?
kill "$PROG_PID" 2>/dev/null || true
wait "$PROG_PID" 2>/dev/null || true

set -e
END=$(date +%s)
echo "wall_s=$((END-START)) exit=$RC" | tee "$OUT/wall.txt"
# Summary crumbs
grep -E '^Time = |^End|Floating point|SIGFPE|FOAM FATAL' "$OUT/log.${MODE}" | tail -40 \
  | tee -a "$OUT/progress.${MODE}.log" || true
tail -20 "$OUT/progress.${MODE}.log" 2>/dev/null || true

if [[ "$RC" -ne 0 ]]; then
  echo "FATAL solver exit=$RC (see $OUT/log.${MODE})"
  exit "$RC"
fi

log "=== reconstructPar ==="
_foam_util reconstructPar -latestTime > "$OUT/log.reconstructPar" 2>&1 \
  || _foam_util reconstructPar > "$OUT/log.reconstructPar" 2>&1

ls -d [0-9]* 0.* 2>/dev/null | sort -g | tee "$OUT/times.txt" || true

if [[ -d /work ]] && [[ "$ROOT" == "/work" ]]; then
  chown -R "$(stat -c '%u:%g' /work)" "$OUT" "$CASE" 2>/dev/null || true
fi

log "STAGE1_COLD_DONE exit=0"
