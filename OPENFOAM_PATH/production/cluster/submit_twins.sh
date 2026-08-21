#!/usr/bin/env bash
# Submit three independent E18 twin jobs on Queen Bee.
# Run FROM OPENFOAM_PATH after env/libs are built:
#   bash production/cluster/submit_twins.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
mkdir -p production/runs

# Preflight (fail fast on login node)
# shellcheck disable=SC1091
source production/env.qb.sh
command -v reactingFoamDebug >/dev/null || {
  echo "FATAL: build reactingFoamDebug first:" >&2
  echo "  cd applications/solvers/reactingFoam && wmake -j8" >&2
  exit 1
}
test -f policy/policy.ts || echo "WARN: policy/policy.ts missing — rlAdaptive will fail"
test -d cases/opposedJet_E18/0.05 || echo "WARN: freeze 0.05 missing"

for f in e18_cvode e18_rl e18_qss; do
  jid=$(sbatch --parsable "production/cluster/${f}.sbatch")
  echo "submitted $f → job $jid"
done
echo "Watch: squeue -u \$USER"
echo "Logs:  production/runs/slurm-*.out"
