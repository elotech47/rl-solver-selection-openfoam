#!/bin/bash
# Host launcher: prepare jobs + Docker OF batch.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${E15_PYTHON:-/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python}"
export KMP_DUPLICATE_LIB_OK=TRUE

"$PY" validation/zeroD/e15_of_prepare_jobs.py

docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  -e E15_BATCH_WIDTH="${E15_BATCH_WIDTH:-8}" \
  opencfd/openfoam-default:2312 \
  -lc 'bash /work/validation/zeroD/e15_of_batch_inside.sh'

echo "OF batch finished — postprocess with e15_of_postprocess.py"
