#!/usr/bin/env bash
# Bootstrap OpenFOAM user stack on this machine (once per image/node).
# Prefers e17_remote/00_bootstrap.sh; falls back to tools/build_libs.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/validation/zeroD/e17_remote/00_bootstrap.sh" ]]; then
  exec bash "$ROOT/validation/zeroD/e17_remote/00_bootstrap.sh" "$@"
fi

echo "e17_remote bootstrap missing — running tools/build_libs.sh inside container"
IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
PLATFORM="${OF_PLATFORM:-linux/amd64}"
docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work "$IMAGE" -lc '
set +eu
source /usr/lib/openfoam/openfoam2312/etc/bashrc
set -e
set +u
source /work/tools/ofrl_container_env.sh
set +u
bash /work/tools/build_libs.sh
'
