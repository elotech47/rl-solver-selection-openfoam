#!/usr/bin/env bash
# Build e16_3b_teacher_forced inside the OF container (links libpolicyRuntime).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DOCKER_HOST="${DOCKER_HOST:-unix:///Users/el0tech/.colima/default/docker.sock}"
docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work --memory=7g \
  opencfd/openfoam-default:2312 \
  -lc 'set +eu; source /usr/lib/openfoam/openfoam2312/etc/bashrc; set +u; set -e
       export WM_PROJECT_USER_DIR=/work FOAM_USER_LIBBIN=/work/platforms/${WM_OPTIONS}/lib
       export LIBTORCH_DIR=/work/opt/libtorch
       export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$LIBTORCH_DIR/lib:${LD_LIBRARY_PATH:-}
       cd /work/src/policyRuntime && wmake libso
       g++ -std=c++17 -O2 -D_GLIBCXX_USE_CXX11_ABI=0 \
         -I/work/src/policyRuntime \
         -I$LIBTORCH_DIR/include \
         -I$LIBTORCH_DIR/include/torch/csrc/api/include \
         -o /work/platforms/${WM_OPTIONS}/bin/e16_3b_teacher_forced \
         /work/tools/e16_3b_teacher_forced.C \
         -L$FOAM_USER_LIBBIN -lpolicyRuntime \
         -L$LIBTORCH_DIR/lib -Wl,-rpath,$LIBTORCH_DIR/lib \
         -Wl,-rpath,$FOAM_USER_LIBBIN \
         -ltorch -ltorch_cpu -lc10
       ls -la /work/platforms/*/bin/e16_3b_teacher_forced
       '
