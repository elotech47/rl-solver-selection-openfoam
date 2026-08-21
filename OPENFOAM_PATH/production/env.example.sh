# Source for generic defaults. On Queen Bee prefer:
#   source production/env.qb.sh

export OF_IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
export OF_PLATFORM="${OF_PLATFORM:-linux/amd64}"
export OF_RUNTIME="${OF_RUNTIME:-native}"
export OF_SIF="${OF_SIF:-}"
export OF_BASHRC="${OF_BASHRC:-/work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc}"

export NPROC="${NPROC:-32}"
export E18_END_TIME="${E18_END_TIME:-0.009}"
export E18_WRITE_INTERVAL="${E18_WRITE_INTERVAL:-1e-05}"
export E18_MODES="${E18_MODES:-cvodeOnly}"
export SLURM_ACCOUNT="${SLURM_ACCOUNT:-loni_pca_dns}"
