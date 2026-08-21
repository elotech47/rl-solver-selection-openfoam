#!/usr/bin/env bash
# Submit three independent E18 twin jobs (edit .sbatch headers first).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
mkdir -p production/runs
for f in e18_cvode e18_rl e18_qss; do
  sbatch "production/cluster/${f}.sbatch"
done
echo "Submitted three jobs. Watch: squeue -u \$USER"
