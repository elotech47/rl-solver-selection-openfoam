#!/bin/bash
#SBATCH --job-name=e18_cvode
#SBATCH --account=loni_pca_dns
#SBATCH --partition=single
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=3900
#SBATCH --time=5-00:00:00
#SBATCH --output=production/runs/slurm-%j-cvode.out
#SBATCH --error=production/runs/slurm-%j-cvode.err

# Run from OPENFOAM_PATH after native OF-v2312 + user libs are built.
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"

# module load ...   # gcc / intel-mpi matching your OF build — fill after install
# source /work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc
# source "$PWD/tools/ofrl_container_env.sh"   # or a host-native env helper

source production/env.example.sh
export OF_RUNTIME=native
export E18_MODES=cvodeOnly
export NPROC="${SLURM_NTASKS:-32}"
export E18_PROD_OUT="production/runs/e18_${SLURM_JOB_ID:-manual}_cvodeOnly"

bash production/scripts/20_run_chem.sh
