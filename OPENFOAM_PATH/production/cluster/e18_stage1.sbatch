#!/bin/bash
#SBATCH --job-name=e18_stage1
#SBATCH --account=loni_pca_dns
#SBATCH --partition=single
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=3900
#SBATCH --time=06:00:00
#SBATCH --output=production/runs/slurm-%j-stage1.out
#SBATCH --error=production/runs/slurm-%j-stage1.err

# Cold mix → freeze t=0.05 under cases/opposedJet_E18/
# Submit FROM OPENFOAM_PATH (login node):
#   bash production/cluster/submit_stage1.sh
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
mkdir -p production/runs

# shellcheck disable=SC1091
source production/env.qb.sh
set -euo pipefail

export NPROC="${SLURM_NTASKS:-8}"
export E18_STAGE1_END="${E18_STAGE1_END:-0.05}"
# Absolute OUT — relative path breaks after cd into the case
export E18_STAGE1_OUT="${ROOT}/production/runs/stage1_cold_${SLURM_JOB_ID}"
export SKIP_OF_SOURCE=1
unset LD_PRELOAD

echo "=== E18 Stage1 Slurm job ${SLURM_JOB_ID} NPROC=$NPROC OUT=$E18_STAGE1_OUT ==="
bash production/scripts/11_run_stage1_cold.sh
echo "=== Stage1 job done — check cases/opposedJet_E18/0.05/ and $E18_STAGE1_OUT ==="
