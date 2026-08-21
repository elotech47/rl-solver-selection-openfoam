#!/usr/bin/env bash
# Submit E18 Stage-1 cold mix as a batch job (no interactive node).
#
#   cd .../OPENFOAM_PATH
#   bash production/cluster/submit_stage1.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
mkdir -p production/runs

JOB=$(sbatch --parsable production/cluster/e18_stage1.sbatch)
echo "Submitted Stage1 job $JOB"
echo "  Slurm:  production/runs/slurm-${JOB}-stage1.out"
echo "  Run:    production/runs/stage1_cold_${JOB}/"
echo "  Watch:  tail -f production/runs/slurm-${JOB}-stage1.out"
echo "          tail -f production/runs/stage1_cold_${JOB}/progress.coldMix.log"
echo "  Queue:  squeue -j $JOB"
