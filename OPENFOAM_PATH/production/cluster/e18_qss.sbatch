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

# module load ... ; source OpenFOAM-v2312 bashrc ; source tools env — see cluster/README.md

source production/env.example.sh
export OF_RUNTIME=native
export E18_MODES=qssOnly
export NPROC="${SLURM_NTASKS:-32}"
export E18_PROD_OUT="production/runs/e18_${SLURM_JOB_ID:-manual}_qssOnly"

bash production/scripts/20_run_chem.sh
