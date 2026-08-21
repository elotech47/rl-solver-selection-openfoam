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

# Short rlAdaptive smoke (~0.2 ms chem).
# - No LibTorch LD_PRELOAD (breaks Foam mesh/dict on QB).
# - FOAM_SIGFPE unset for this smoke only: torch JIT import Abort(134) under SIGFPE trap.
#   Production twins should re-enable SIGFPE once smoke proves policy load works.
#
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
export OFRL_TORCH_PRELOAD=0
export OFRL_RL_NO_SIGFPE=1
unset LD_PRELOAD
unset FOAM_SIGFPE

mkdir -p "$E18_PROD_OUT"
# Foam-free JIT load first (isolates LibTorch from OpenFOAM)
chmod +x tools/run_torch_jit_smoke.sh
bash tools/run_torch_jit_smoke.sh | tee "$E18_PROD_OUT/jit_preflight.txt"

bash production/scripts/20_run_chem.sh
