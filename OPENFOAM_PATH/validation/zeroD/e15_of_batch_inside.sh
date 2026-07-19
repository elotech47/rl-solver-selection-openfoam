#!/bin/bash
# Inside OF container: run E15 OF signature map 8-wide by job index.
# Do NOT source OpenFOAM bashrc here — it trips set -e and aborts the batch.
set -euo pipefail
ROOT="${ROOT:-/work}"
cd "$ROOT"
TSV="$ROOT/validation/zeroD/e15_conformance/e15_of_jobs.tsv"
WIDTH="${E15_BATCH_WIDTH:-8}"

N=$(awk 'NR>1 {c++} END{print c+0}' "$TSV")
echo "E15 OF batch: $N jobs, width=$WIDTH"

# Fail-fast without bashrc: find chemFoamDebug under platforms/
CHEMBIN=$(ls -1 "$ROOT"/platforms/*/bin/chemFoamDebug 2>/dev/null | head -1 || true)
if [ -z "$CHEMBIN" ] || [ ! -x "$CHEMBIN" ]; then
  echo "FATAL: missing $ROOT/platforms/*/bin/chemFoamDebug"
  echo "Run: bash /work/tools/recover_platforms.sh"
  exit 2
fi
echo "chemFoamDebug OK: $CHEMBIN"

export ROOT
seq 0 $((N - 1)) | xargs -P "$WIDTH" -n 1 \
  bash /work/validation/zeroD/e15_of_run_one.sh

echo "E15 OF batch complete"
