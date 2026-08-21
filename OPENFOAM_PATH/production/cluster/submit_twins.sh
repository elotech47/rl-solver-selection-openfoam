#!/usr/bin/env bash
# Submit three independent E18 twin jobs on Queen Bee.
# Run FROM OPENFOAM_PATH on the LOGIN node:
#   bash production/cluster/submit_twins.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
mkdir -p production/runs

parse_jobid() {
  # LONI prints SU banners to stdout even with --parsable
  printf '%s\n' "$1" | awk '
    /Submitted job / { for (i=1;i<=NF;i++) if ($i ~ /^[0-9]+$/) id=$i }
    /^[0-9]+$/ { id=$0 }
    END { print id }
  '
}

if ! command -v sbatch >/dev/null 2>&1; then
  echo "FATAL: sbatch not found — run on the login node, not a compute node" >&2
  exit 127
fi

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
  out=$(sbatch --parsable "production/cluster/${f}.sbatch" 2>&1) || {
    echo "$out" >&2
    exit 1
  }
  jid=$(parse_jobid "$out")
  echo "submitted $f → job $jid"
done
echo "Watch: squeue -u \$USER"
echo "Logs:  production/runs/slurm-*.out"
