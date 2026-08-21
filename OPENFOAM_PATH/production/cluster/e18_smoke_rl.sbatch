#!/bin/bash
#SBATCH --job-name=e18_smoke_rl
#SBATCH --account=loni_pca_dns
#SBATCH --partition=single
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=3900
#SBATCH --time=02:00:00
#SBATCH --output=production/runs/slurm-%j-smoke_rl.out
#SBATCH --error=production/runs/slurm-%j-smoke_rl.err

# Short rlAdaptive smoke (~0.2 ms chem) — no LibTorch LD_PRELOAD by default.
# Submit FROM OPENFOAM_PATH (login node):
#   sbatch production/cluster/e18_smoke_rl.sbatch
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
mkdir -p production/runs
# shellcheck disable=SC1091
source production/env.qb.sh
set -euo pipefail

test -f "${ROOT}/policy/policy.ts" || {
  echo "FATAL: missing ${ROOT}/policy/policy.ts" >&2
  exit 1
}
test -f "${ROOT}/policy/policy_manifest" || {
  echo "FATAL: missing ${ROOT}/policy/policy_manifest" >&2
  exit 1
}

export E18_MODES=rlAdaptive
export E18_END_TIME=0.0002
export NPROC="${SLURM_NTASKS:-8}"
export E18_PROD_OUT="${ROOT}/production/runs/e18_${SLURM_JOB_ID}_smoke_rl"
# Prefer rpath/LD_LIBRARY_PATH only — LD_PRELOAD aborts Foam on QB
export OFRL_TORCH_PRELOAD=0
unset LD_PRELOAD

bash production/scripts/20_run_chem.sh
