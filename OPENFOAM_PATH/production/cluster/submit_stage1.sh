#!/usr/bin/env bash
# Submit E18 Stage-1 cold mix as a batch job (no interactive node).
#
# Must run on a LOGIN node (sbatch is not on qbc* compute nodes):
#   cd .../OPENFOAM_PATH && bash production/cluster/submit_stage1.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
mkdir -p production/runs

if ! command -v sbatch >/dev/null 2>&1; then
  cat >&2 <<EOF
FATAL: sbatch not found on this host ($(hostname)).

You are probably on a compute node (e.g. qbc012 from salloc).
Exit the interactive allocation and submit from the login node:

  exit
  cd $ROOT
  bash production/cluster/submit_stage1.sh
EOF
  exit 127
fi

# LONI sbatch prints SU banners to stdout even with --parsable — extract job id only.
SBATCH_OUT=$(sbatch --parsable production/cluster/e18_stage1.sbatch 2>&1) || {
  echo "$SBATCH_OUT" >&2
  exit 1
}
JOB=$(printf '%s\n' "$SBATCH_OUT" | awk '
  /Submitted job / { for (i=1;i<=NF;i++) if ($i ~ /^[0-9]+$/) id=$i }
  /^[0-9]+$/ { id=$0 }
  END { print id }
')
if [[ -z "${JOB:-}" || ! "$JOB" =~ ^[0-9]+$ ]]; then
  echo "FATAL: could not parse job id from sbatch output:" >&2
  echo "$SBATCH_OUT" >&2
  exit 1
fi

echo "Submitted Stage1 job $JOB"
echo "  Slurm:  production/runs/slurm-${JOB}-stage1.out"
echo "  Run:    production/runs/stage1_cold_${JOB}/"
echo "  Watch:  tail -f production/runs/slurm-${JOB}-stage1.out"
echo "          tail -f production/runs/stage1_cold_${JOB}/progress.coldMix.log"
echo "  Queue:  squeue -j $JOB"
