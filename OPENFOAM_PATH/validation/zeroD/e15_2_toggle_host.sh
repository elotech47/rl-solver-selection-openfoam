#!/bin/bash
# Host: prepare + run E15.2 toggle batch (8-wide), NTC first.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${E15_PYTHON:-/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python}"
export KMP_DUPLICATE_LIB_OK=TRUE
"$PY" validation/zeroD/e15_2_prepare.py

N=$(awk 'NR>1 {c++} END{print c+0}' validation/zeroD/e15_conformance/e15_2_jobs.tsv)
WIDTH="${E15_BATCH_WIDTH:-8}"
echo "E15.2: $N jobs, width=$WIDTH"

docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  -e E15_BATCH_WIDTH="$WIDTH" \
  opencfd/openfoam-default:2312 \
  -lc "
CHEMBIN=\$(ls -1 /work/platforms/*/bin/chemFoamDebug | head -1)
test -x \"\$CHEMBIN\" || { echo FATAL missing chemFoamDebug; exit 2; }
echo chemFoamDebug OK: \$CHEMBIN
seq 0 $((N - 1)) | xargs -P $WIDTH -n 1 bash /work/validation/zeroD/e15_2_run_one.sh
echo E15.2 batch complete
"
echo "Next: $PY validation/zeroD/e15_2_postprocess.py"
