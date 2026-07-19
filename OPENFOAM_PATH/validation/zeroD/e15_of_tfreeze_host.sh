#!/bin/bash
# Host: full 38-condition OF-QSS map with Tfreeze=true (epsmin=0.02).
# CVODE not re-run — reuse of_runs/*/cvode.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${E15_PYTHON:-/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python}"
export KMP_DUPLICATE_LIB_OK=TRUE

"$PY" validation/zeroD/e15_of_tfreeze_prepare.py

N=$(awk 'NR>1 {c++} END{print c+0}' validation/zeroD/e15_conformance/e15_of_tfreeze_jobs.tsv)
WIDTH="${E15_BATCH_WIDTH:-8}"
echo "E15 OF T-freeze map: $N QSS jobs, width=$WIDTH"

docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  -e E15_BATCH_WIDTH="$WIDTH" \
  opencfd/openfoam-default:2312 \
  -lc "
CHEMBIN=\$(ls -1 /work/platforms/*/bin/chemFoamDebug | head -1)
test -x \"\$CHEMBIN\" || { echo FATAL missing chemFoamDebug; exit 2; }
echo chemFoamDebug OK: \$CHEMBIN
# Confirm lib has Tfreeze (built after E15.3)
test -f /work/platforms/*/lib/libqssChemistrySolver.so
seq 0 $((N - 1)) | xargs -P $WIDTH -n 1 bash /work/validation/zeroD/e15_of_tfreeze_run_one.sh
echo E15 OF T-freeze batch complete
"
echo "Next: $PY validation/zeroD/e15_of_tfreeze_postprocess.py"
