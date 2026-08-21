#!/usr/bin/env bash
# Export checkpoint → policy.ts + Foam policy_manifest (snake_case).
# Usage: bash production/scripts/01_setup_policy.sh [checkpoint.pt]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CKPT="${1:-}"
if [[ -z "$CKPT" ]]; then
  for c in \
    "$ROOT/policy/lambda_1p0_with_base_obs_rms.pt" \
    "$ROOT/policy/best_offline_eval2.pt"
  do
    [[ -f "$c" ]] && CKPT="$c" && break
  done
fi
if [[ -z "${CKPT}" || ! -f "$CKPT" ]]; then
  echo "Need checkpoint .pt (pass path or place under policy/)" >&2
  exit 1
fi

PY=python3
if command -v conda >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh" 2>/dev/null || true
  conda activate rlEnv 2>/dev/null && PY=python || true
fi

echo "Exporting $CKPT → $ROOT/policy/"
"$PY" "$ROOT/tools/export_policy.py" --checkpoint "$CKPT" --out-dir "$ROOT/policy"
"$PY" "$ROOT/tools/export_policy_manifest_foam.py" \
  --json "$ROOT/policy/policy_manifest.json" \
  --out "$ROOT/policy/policy_manifest"

mkdir -p "$ROOT/production/pins"
{
  echo "checkpoint=$CKPT"
  echo "exported=$(date -Iseconds)"
  if command -v sha256sum >/dev/null; then
    sha256sum "$ROOT/policy/policy.ts" "$ROOT/policy/policy_manifest" 2>/dev/null || true
  fi
} | tee "$ROOT/production/pins/POLICY_HASH.txt"

echo "Done. See production/pins/POLICY.md"
