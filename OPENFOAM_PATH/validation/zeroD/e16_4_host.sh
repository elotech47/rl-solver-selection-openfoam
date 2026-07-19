#!/usr/bin/env bash
# E16.4 host orchestrator — paper-conditions 0D suite.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export DOCKER_HOST="${DOCKER_HOST:-unix:///Users/el0tech/.colima/default/docker.sock}"
PY="${PY:-/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python}"
export KMP_DUPLICATE_LIB_OK=TRUE
OUT="$ROOT/validation/e16_parity/e16_4_runs"
mkdir -p "$OUT"

chmod +x validation/zeroD/e16_4_*.sh validation/zeroD/e16_4_*.py 2>/dev/null || true

echo "[e16.4] write Z-based ICs"
"$PY" validation/zeroD/e16_4_write_ics.py --all

# Optional: only rebuild libs if FORCE_REBUILD=1
if [[ "${FORCE_REBUILD:-0}" == "1" ]]; then
  echo "[e16.4] rebuild rlChemistryModel"
  docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work --memory=7g \
    opencfd/openfoam-default:2312 \
    -lc 'set +eu; source /usr/lib/openfoam/openfoam2312/etc/bashrc; set +u; set -e
         export WM_PROJECT_USER_DIR=/work FOAM_USER_LIBBIN=/work/platforms/${WM_OPTIONS}/lib
         export LIBTORCH_DIR=/work/opt/libtorch SUNDIALS_DIR=/work/opt/sundials-arm64
         export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$LIBTORCH_DIR/lib:$SUNDIALS_DIR/lib
         cd /work/src/rlChemistryModel && wmake libso
         '
fi

# Run order: C2,C3,C4 first (shorter), then C1 (12k steps @ 1e-5)
COND_ORDER="${COND_ORDER:-C2 C3 C4 C1}"
MODES="${MODES:-cvodeOnly qssOnly rlAdaptive}"
ONLY_PY="${ONLY_PY:-0}"
ONLY_OF="${ONLY_OF:-0}"

if [[ "$ONLY_OF" != "1" ]]; then
  echo "[e16.4] Python CVODE/QSS/AdaptiveRL"
  for cid in $COND_ORDER; do
    echo "===== PY $cid ====="
    "$PY" validation/zeroD/e16_4_python.py --id "$cid"
  done
fi

if [[ "$ONLY_PY" != "1" ]]; then
  echo "[e16.4] OpenFOAM modes"
  # shell-read conditions from JSON via python
  while IFS=$'\t' read -r cid label T0 patm Z dt tend; do
    case " $COND_ORDER " in
      *" $cid "*) ;;
      *) continue ;;
    esac
    for mode in $MODES; do
      echo "===== OF $cid $mode ====="
      docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
        -v "$ROOT:/work" -w /work --memory=7g \
        opencfd/openfoam-default:2312 \
        -lc "bash /work/validation/zeroD/e16_4_run_one.sh $cid $label $T0 $patm $Z $dt $tend $mode"
    done
  done < <("$PY" - <<'PY'
import json
from pathlib import Path
cfg = json.loads(Path("validation/e16_parity/E16_4_CONDITIONS.json").read_text())
for c in cfg["conditions"]:
    print(f"{c['id']}\t{c['label']}\t{c['T0']}\t{c['p_atm']}\t{c['Z']}\t{c['dt']}\t{c['t_end']}")
PY
)
fi

echo "[e16.4] figures + gate"
"$PY" analysis/e16_4_figures.py
"$PY" validation/zeroD/e16_4_gate.py
echo "E16.4 host done."
