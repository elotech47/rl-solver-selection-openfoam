#!/bin/bash
#SBATCH --job-name=e18_qss
#SBATCH --account=loni_pca_dns
#SBATCH --partition=single
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=3900
#SBATCH --time=5-00:00:00
#SBATCH --output=production/runs/slurm-%j-qss.out
#SBATCH --error=production/runs/slurm-%j-qss.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
mkdir -p production/runs

# shellcheck disable=SC1091
source production/env.qb.sh

export E18_MODES=qssOnly
export NPROC="${SLURM_NTASKS:-32}"
export E18_PROD_OUT="production/runs/e18_${SLURM_JOB_ID}_qssOnly"

bash production/scripts/20_run_chem.sh
