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

if [[ "${SKIP_OF_SOURCE:-}" == "1" ]] \
  || { [[ -n "${WM_PROJECT_DIR:-}" ]] && command -v reactingFoamDebug >/dev/null 2>&1; }; then
  set +u
  # shellcheck disable=SC1091
  source "$ROOT/tools/ofrl_container_env.sh" || true
  set +u
else
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

# LibTorch preload aborts Foam utilities
_foam_util() { env -u LD_PRELOAD "$@"; }

mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
CASE="$(cd "$CASE" && pwd)"
ROOT="$(cd "$ROOT" && pwd)"
cd "$CASE"

_foam_util foamDictionary system/controlDict -entry endTime -set "$ENDT" > /dev/null
_foam_util foamDictionary system/controlDict -entry startFrom -set startTime > /dev/null
_foam_util foamDictionary system/controlDict -entry startTime -set "$FREEZE" > /dev/null
_foam_util foamDictionary system/decomposeParDict -entry numberOfSubdomains -set "$NPROC" > /dev/null

# Drop processors only; keep freeze mesh + fields
rm -rf processor* postProcessing 2>/dev/null || true

test -f constant/polyMesh/points || { echo "FATAL: no polyMesh — Stage1 incomplete"; exit 1; }
test -d "$FREEZE" || { echo "FATAL: freeze dir $FREEZE missing"; exit 1; }
command -v reactingFoamDebug >/dev/null || {
  echo "FATAL: reactingFoamDebug not found on PATH"; exit 1;
}

echo "=== decomposePar from freeze=$FREEZE (NPROC=$NPROC) ==="
_foam_util decomposePar -force -time "$FREEZE" > "$OUT/log.decomposePar" 2>&1 \
  || _foam_util decomposePar -force > "$OUT/log.decomposePar" 2>&1

echo "=== parallel reactingFoamDebug MODE=$MODE freeze=$FREEZE end=$ENDT ===" | tee "$OUT/run_header.txt"
# Default: never LD_PRELOAD LibTorch on native QB (aborts mesh/dict parse).
# Opt-in only: OFRL_TORCH_PRELOAD=1 if policy fails to resolve symbols without it.
if [[ "$MODE" == "rlAdaptive" ]] \
  && [[ "${OFRL_TORCH_PRELOAD:-0}" == "1" ]] \
  && [[ -n "${OFRL_TORCH_LD_PRELOAD:-}" ]]; then
  export LD_PRELOAD="$OFRL_TORCH_LD_PRELOAD"
  echo "LD_PRELOAD=LibTorch (OFRL_TORCH_PRELOAD=1)"
else
  unset LD_PRELOAD
  echo "LD_PRELOAD unset (mode=$MODE OFRL_TORCH_PRELOAD=${OFRL_TORCH_PRELOAD:-0})"
fi
START=$(date +%s)
set +e

if ! declare -F ofrl_run_parallel >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  source "$ROOT/tools/ofrl_container_env.sh"
fi

# Direct log (no awk pipe — OOM risk on chemistry)
: > "$OUT/progress.${MODE}.log"
(
  while true; do
    sleep 60
    [[ -f "$OUT/log.${MODE}" ]] || continue
    tline=$(grep -E '^Time = |^propSanity: T |^End|rlUsage' "$OUT/log.${MODE}" 2>/dev/null | tail -5 || true)
    [[ -n "$tline" ]] && echo "$(date -Is) $tline" >> "$OUT/progress.${MODE}.log"
  done
) &
PROG_PID=$!

ofrl_run_parallel "$NPROC" reactingFoamDebug -parallel > "$OUT/log.${MODE}" 2>&1
RC=$?
kill "$PROG_PID" 2>/dev/null || true
wait "$PROG_PID" 2>/dev/null || true
set -e
END=$(date +%s)
echo "wall_s=$((END-START)) exit=$RC" | tee "$OUT/wall.txt"
grep -E '^Time = |^End|Floating point|SIGFPE|FOAM FATAL|rlUsage' "$OUT/log.${MODE}" 2>/dev/null \
  | tail -50 | tee -a "$OUT/progress.${MODE}.log" || true
tail -30 "$OUT/progress.${MODE}.log" 2>/dev/null || true

if [[ "$RC" -ne 0 ]]; then
  echo "FATAL solver exit=$RC"
  exit "$RC"
fi

echo "=== reconstructPar ==="
_foam_util reconstructPar > "$OUT/log.reconstructPar" 2>&1 || true
if [[ -d /work ]] && [[ "$ROOT" == "/work" ]]; then
  chown -R "$(stat -c '%u:%g' /work)" "$OUT" "$CASE" 2>/dev/null || true
fi
echo "STAGE2_MODE_DONE mode=$MODE exit=0"
