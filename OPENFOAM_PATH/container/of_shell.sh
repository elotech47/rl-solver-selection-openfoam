#!/usr/bin/env bash
# Launch an interactive ESI OpenFOAM v2312 shell with this repo mounted at /work.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE="${OF_RL_IMAGE:-of-rl-chem:2312}"
BASE_IMAGE="opencfd/openfoam-default:2312"

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "[of_shell] Custom image ${IMAGE} not found; using ${BASE_IMAGE}"
  echo "[of_shell] Build with:  docker build -t ${IMAGE} -f container/Dockerfile ."
  IMAGE="${BASE_IMAGE}"
fi

OF_BASHRC="/usr/lib/openfoam/openfoam2312/etc/bashrc"

exec docker run --rm -it \
  --platform=linux/amd64 \
  --entrypoint /bin/bash \
  -v "${ROOT}:/work" \
  -w /work \
  -e SUNDIALS_DIR=/opt/sundials \
  -e LIBTORCH_DIR=/opt/libtorch \
  "${IMAGE}" \
  -lc "source '${OF_BASHRC}'; cd /work; exec bash"
