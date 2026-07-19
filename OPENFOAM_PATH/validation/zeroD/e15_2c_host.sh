#!/bin/bash
# Host: E15.2c — Tfreeze + epsmin=0.01 (no rebuild; QSS-only 5 jobs).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${E15_PYTHON:-/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python}"
export KMP_DUPLICATE_LIB_OK=TRUE

"$PY" validation/zeroD/e15_2c_prepare.py

N=$(awk 'NR>1 {c++} END{print c+0}' validation/zeroD/e15_conformance/e15_2c_jobs.tsv)
WIDTH="${E15_BATCH_WIDTH:-5}"
echo "E15.2c: $N jobs, width=$WIDTH"

docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  opencfd/openfoam-default:2312 \
  -lc "
CHEMBIN=\$(ls -1 /work/platforms/*/bin/chemFoamDebug | head -1)
test -x \"\$CHEMBIN\" || { echo FATAL missing chemFoamDebug; exit 2; }
echo chemFoamDebug OK: \$CHEMBIN
seq 0 $((N - 1)) | xargs -P $WIDTH -n 1 bash /work/validation/zeroD/e15_2c_run_one.sh
echo E15.2c batch complete
"
echo "Next: $PY validation/zeroD/e15_2c_postprocess.py"
