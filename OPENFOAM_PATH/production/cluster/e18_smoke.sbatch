#!/bin/bash
#SBATCH --job-name=e18_smoke
#SBATCH --account=loni_pca_dns
#SBATCH --partition=single
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=3900
#SBATCH --time=02:00:00
#SBATCH --output=production/runs/slurm-%j-smoke.out
#SBATCH --error=production/runs/slurm-%j-smoke.err

# Short cvodeOnly smoke (~0.2 ms chem) before full twins.
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
mkdir -p production/runs
# shellcheck disable=SC1091
source production/env.qb.sh
export E18_MODES=cvodeOnly
export E18_END_TIME=0.0002
export NPROC="${SLURM_NTASKS:-8}"
export E18_PROD_OUT="production/runs/e18_${SLURM_JOB_ID}_smoke"
bash production/scripts/20_run_chem.sh
