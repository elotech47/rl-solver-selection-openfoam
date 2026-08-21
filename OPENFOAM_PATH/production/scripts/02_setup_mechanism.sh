#!/usr/bin/env bash
# Mechanism conversion — RARE. Production twins use case constant/ already.
# Usage: bash production/scripts/02_setup_mechanism.sh [--refit]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "WARNING: reconverting mechanism invalidates Stage-1 freeze unless you re-run cold mix."
echo "See production/pins/MECHANISM.md"
if [[ "${FORCE:-0}" != "1" ]]; then
  read -r -p "Continue? [y/N] " ans
  [[ "${ans:-}" =~ ^[Yy]$ ]] || exit 0
fi

python3 "$ROOT/tools/convert_mechanism.py"
if [[ "${1:-}" == "--refit" ]]; then
  bash "$ROOT/tools/run_chemkinToFoam_refit.sh"
else
  bash "$ROOT/tools/run_chemkinToFoam.sh"
fi
echo "Copy foam thermo/reactions into cases/opposedJet_E18/constant/ and re-freeze Stage 1."
