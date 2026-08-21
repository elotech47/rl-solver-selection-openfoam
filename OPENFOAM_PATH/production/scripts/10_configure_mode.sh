#!/usr/bin/env bash
# Configure chemistryProperties for one case directory.
# Usage: bash production/scripts/10_configure_mode.sh <mode> <case_path>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODE="${1:?mode: cvodeOnly|qssOnly|rlAdaptive}"
CASE_PATH="${2:?case path}"
export E17_CONTAINER_ROOT="${E17_CONTAINER_ROOT:-/work}"
exec bash "$ROOT/validation/zeroD/e18_prep/stage2_configure_mode.sh" "$MODE" "$CASE_PATH"
