#!/bin/bash
# Rerun OF-CVODE @ T1000/1atm φ=1.0 and 1.5 with wall_cap=3600s.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
TSV="$ROOT/validation/zeroD/e15_conformance/e15_of_jobs.tsv"
BAK="$ROOT/validation/zeroD/e15_conformance/e15_of_jobs.tsv.bak_pre_1000_1"

# Restore if a previous failed run left wall_cap mutated
if [[ -f "$BAK" ]]; then
  cp -f "$BAK" "$TSV"
fi
cp -f "$TSV" "$BAK"

awk -F'\t' -v OFS='\t' '
  NR==1 {print; next}
  $2 ~ /^T1000_p1_/ && $3=="cvode" {$8=3600}
  {print}
' "$BAK" > "$TSV"

IDXS=$(awk -F'\t' 'NR>1 && $2 ~ /^T1000_p1_/ && $3=="cvode" {printf "%s ", $1}' "$TSV")
echo "CVODE idxs: $IDXS (wall_cap=3600)"

docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  opencfd/openfoam-default:2312 \
  -lc "
set -e
for i in $IDXS; do
  echo \"=== rerun idx=\$i ===\"
  bash /work/validation/zeroD/e15_of_run_one.sh \$i
done
echo CVODE_1000_1_RERUN_COMPLETE
"

cp -f "$BAK" "$TSV"
echo "Restored TSV. Check of_runs/T1000_p1_*/cvode/failure.txt"
