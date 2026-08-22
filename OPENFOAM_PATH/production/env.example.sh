# Source for generic defaults. On Queen Bee prefer:
#   source production/env.qb.sh

export OF_IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
export OF_PLATFORM="${OF_PLATFORM:-linux/amd64}"
export OF_RUNTIME="${OF_RUNTIME:-native}"
export OF_SIF="${OF_SIF:-}"
export OF_BASHRC="${OF_BASHRC:-/work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc}"

export NPROC="${NPROC:-32}"
export E18_END_TIME="${E18_END_TIME:-0.009}"
export E18_WRITE_INTERVAL="${E18_WRITE_INTERVAL:-1e-04}"
export E18_FULL_WRITE_INTERVAL="${E18_FULL_WRITE_INTERVAL:-1e6}"
export E18_WRITE_FORMAT="${E18_WRITE_FORMAT:-binary}"
export E18_WRITE_COMPRESSION="${E18_WRITE_COMPRESSION:-on}"
export E18_PACK_OBJECTS="${E18_PACK_OBJECTS:-T U p solverFlag policyFlag chemCpuTime oh o o2 h h2 h2o h2o2 ho2 co co2 ch2o c2h4 nc12h26 n2}"
export E18_MODES="${E18_MODES:-cvodeOnly}"
export SLURM_ACCOUNT="${SLURM_ACCOUNT:-loni_pca_dns}"
