#!/usr/bin/env bash
# Host wrapper: MidT 1 µs OF-QSS + OF-CVODE under CONFORM T-freeze.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  opencfd/openfoam-default:2312 \
  -lc 'bash /work/validation/zeroD/e15_rung_b_midt.sh'
