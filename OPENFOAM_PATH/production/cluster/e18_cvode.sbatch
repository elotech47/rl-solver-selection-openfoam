#!/bin/bash
#SBATCH --job-name=e18_cvode
#SBATCH --account=loni_pca_dns
#SBATCH --partition=single
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=3900
#SBATCH --time=7-00:00:00
# 7 d = `single` partition max (168 h). Workstation cvodeOnly was still
# incomplete after ~45 h (8 ranks); RL needed ~91 h to endTime=0.059.
#SBATCH --output=production/runs/slurm-%j-cvode.out
#SBATCH --error=production/runs/slurm-%j-cvode.err

# Submit FROM OPENFOAM_PATH:
#   cd .../OPENFOAM_PATH && sbatch production/cluster/e18_cvode.sbatch
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
mkdir -p production/runs

# shellcheck disable=SC1091
source production/env.qb.sh
set -euo pipefail

export E18_MODES=cvodeOnly
export NPROC="${SLURM_NTASKS:-32}"
export E18_PROD_OUT="${ROOT}/production/runs/e18_${SLURM_JOB_ID}_cvodeOnly"

bash production/scripts/20_run_chem.sh
