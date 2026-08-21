# Source me after editing, or: source production/env.example.sh
# Copy to production/env.local.sh for machine-specific overrides (gitignored).

export OF_IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
export OF_PLATFORM="${OF_PLATFORM:-linux/amd64}"
# docker | apptainer | native  (QB: prefer native ESI v2312 under /work)
export OF_RUNTIME="${OF_RUNTIME:-native}"
export OF_SIF="${OF_SIF:-}"
# Native only: path to OpenFOAM-v2312 etc/bashrc (set after install)
export OF_BASHRC="${OF_BASHRC:-}"

export NPROC="${NPROC:-32}"
export E18_END_TIME="${E18_END_TIME:-0.009}"
export E18_WRITE_INTERVAL="${E18_WRITE_INTERVAL:-1e-05}"
export E18_MODES="${E18_MODES:-cvodeOnly}"
# SBATCH account on QB:
export SLURM_ACCOUNT="${SLURM_ACCOUNT:-loni_pca_dns}"
