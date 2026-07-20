#!/usr/bin/env bash
# Resume E17 preflight from E16.5 gate + E16.4 C2 (after wmake succeeded).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
PF="${1:-$ROOT/validation/zeroD/e17_remote_runs/preflight_resume_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$PF"
IMAGE="${OF_IMAGE:-opencfd/openfoam-default:2312}"
PLATFORM="${OF_PLATFORM:-linux/amd64}"
export DOCKER_HOST="${DOCKER_HOST:-unix:///var/run/docker.sock}"

echo "[preflight resume] E16.5 gate (docker torch)"
docker run --rm --platform="$PLATFORM" \
  -v "$ROOT:/work" -w /work \
  python:3.11-slim-bookworm \
  bash -lc 'pip install -q torch numpy && python3 /work/validation/zeroD/e16_5_gate.py' \
  | tee "$PF/e16_5_gate.txt"
grep '"verdict"' "$ROOT/validation/e16_parity/E16_5_SUMMARY.json" || true

echo "[preflight resume] E16.4 C2 three modes"
for mode in cvodeOnly qssOnly rlAdaptive; do
  docker run --rm --platform="$PLATFORM" --entrypoint /bin/bash \
    -v "$ROOT:/work" -w /work --memory=16g \
    "$IMAGE" \
    -lc "bash /work/validation/zeroD/e16_4_run_one.sh C2 MidT_MidP 800 10 0.062 1e-6 0.0035 $mode" \
    | tee "$PF/log.e16_4_C2_${mode}.txt"
done
python3 validation/zeroD/e17_remote/preflight_c2_check.py "$PF" | tee "$PF/preflight_c2_check.txt"
echo "DONE $PF"
