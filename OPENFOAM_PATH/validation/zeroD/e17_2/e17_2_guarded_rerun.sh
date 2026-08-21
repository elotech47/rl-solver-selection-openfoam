#!/usr/bin/env bash
# E17.2 guarded CFD campaign:
#   1) stop any leftover smoke (caller may have already stopped)
#   2) new OUT dir with cvodeOnly copied from a prior successful smoke
#   3) run qssOnly → rlAdaptive to endTime (default 2e-4)
#
# Contour fields (AUTO_WRITE, packed under OUT/<mode>/fields/<time>/):
#   solverFlag       0=CVODE (policy or fallback), 1=QSS accepted
#   qssFallbackCount cumulative QSS→CVODE rescues per cell
#   yClipMass        Layer-1 clipped negative mass (diagnostic)
#   T, chemCpuTime, OH
#
# Logs: SolverPerformance 0 → no DILUPBiCGStab spam.
# Always uses an absolute path under OPENFOAM_PATH (ignores stale relative E17_SMOKE_OUT).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
SRC_CVODE="${E17_CVODE_SRC:-$ROOT/validation/zeroD/e17_remote_runs/smoke_20260719_211924/cvodeOnly}"
OUT="${E17_SMOKE_OUT_FORCE:-$ROOT/validation/zeroD/e17_remote_runs/e17_2_guarded_${STAMP}}"

export E17_MODES="${E17_MODES:-qssOnly rlAdaptive}"
export E17_SKIP_KERNEL="${E17_SKIP_KERNEL:-1}"
export E17_END_TIME="${E17_END_TIME:-2e-4}"
export NPROC="${NPROC:-16}"
# Absolute path — do not inherit a relative/stale E17_SMOKE_OUT from the shell
export E17_SMOKE_OUT="$OUT"
unset E17_SMOKE_OUT_FORCE 2>/dev/null || true

if [[ ! -d "$SRC_CVODE" ]]; then
  echo "ERROR: cvodeOnly source missing: $SRC_CVODE" >&2
  exit 1
fi

mkdir -p "$OUT"
echo "E17.2 guarded campaign"
echo "  OUT=$OUT"
echo "  modes=$E17_MODES  endTime=$E17_END_TIME  NPROC=$NPROC"
echo "  copying cvodeOnly from $SRC_CVODE"

# Copy reference CVODE (logs/fields/extract) — do not re-run it
rm -rf "$OUT/cvodeOnly"
cp -a "$SRC_CVODE" "$OUT/cvodeOnly"
# Note in campaign README
cat > "$OUT/README.md" <<EOF
# E17.2 guarded campaign \`${STAMP}\`

- **endTime:** ${E17_END_TIME}
- **cvodeOnly:** copied from \`${SRC_CVODE}\` (not re-run)
- **qssOnly / rlAdaptive:** QSS+guards / policy+guards, \`FOAM_SIGFPE\` ON

## Contour / usage fields

| Field | Meaning |
|-------|---------|
| \`solverFlag\` | Effective solver this write: **0 = CVODE**, **1 = QSS** (fallback counts as 0) |
| \`qssFallbackCount\` | Cumulative per-cell QSS→CVODE rescue count |
| \`yClipMass\` | Layer-1 clipped negative mass fraction |
| \`T\`, \`chemCpuTime\`, \`OH\` | thermo / cost / radical |

Packed under \`<mode>/fields/<time>/\`. Decisions CSV: \`<mode>/rl_decisions.csv\` (merged from ranks).

## Logs

\`<mode>/log.<mode>\` — residuals suppressed via \`DebugSwitches { SolverPerformance 0; }\`.
\`<mode>/progress.<mode>.log\` — quiet progress lines.
EOF

echo "Wrote $OUT/README.md"
echo "Starting qssOnly → rlAdaptive …"
# Use plain bash (not exec) so wrappers can run post/viz after return
bash "$ROOT/validation/zeroD/e17_remote/02_smoke_three_mode.sh"
echo "Campaign smoke finished → $OUT"
echo "$OUT" > "$OUT/../.e17_2_last_out" 2>/dev/null || echo "$OUT" > "$ROOT/validation/zeroD/e17_remote_runs/.e17_2_last_out"
