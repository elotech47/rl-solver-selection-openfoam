#!/bin/bash
# Host: rebuild QSS (Tfreeze) if needed, prepare + run E15.2b batch.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${E15_PYTHON:-/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python}"
export KMP_DUPLICATE_LIB_OK=TRUE

if [[ "${E15_2B_SKIP_BUILD:-0}" != "1" ]]; then
  echo "=== rebuild libs (qssChemistrySolver Tfreeze) ==="
  docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work \
    opencfd/openfoam-default:2312 \
    -lc 'set +u; source /usr/lib/openfoam/openfoam2312/etc/bashrc; set -u; export WM_PROJECT_USER_DIR=/work FOAM_USER_LIBBIN=/work/platforms/${WM_OPTIONS}/lib FOAM_USER_APPBIN=/work/platforms/${WM_OPTIONS}/bin; bash /work/tools/build_libs.sh'
fi

"$PY" validation/zeroD/e15_2b_prepare.py

N=$(awk 'NR>1 {c++} END{print c+0}' validation/zeroD/e15_conformance/e15_2b_jobs.tsv)
WIDTH="${E15_BATCH_WIDTH:-5}"
echo "E15.2b: $N jobs, width=$WIDTH"

docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  -e E15_BATCH_WIDTH="$WIDTH" \
  opencfd/openfoam-default:2312 \
  -lc "
CHEMBIN=\$(ls -1 /work/platforms/*/bin/chemFoamDebug | head -1)
test -x \"\$CHEMBIN\" || { echo FATAL missing chemFoamDebug; exit 2; }
echo chemFoamDebug OK: \$CHEMBIN
seq 0 $((N - 1)) | xargs -P $WIDTH -n 1 bash /work/validation/zeroD/e15_2b_run_one.sh
echo E15.2b batch complete
"
echo "Next: $PY validation/zeroD/e15_2b_postprocess.py"
