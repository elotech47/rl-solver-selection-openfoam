#!/usr/bin/env bash
# Write MANIFEST.md for E15 large run trees (SHA-256 per file + producing commit).
# Usage (from OPENFOAM_PATH or repo root):
#   bash validation/zeroD/e15_write_manifest.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONF="$ROOT/validation/zeroD/e15_conformance"
OUT="$CONF/MANIFEST.md"
COMMIT=$(git -C "$(cd "$ROOT/.." && pwd)" rev-parse HEAD 2>/dev/null || git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo UNKNOWN)
TAG_CANON=$(git -C "$(cd "$ROOT/.." && pwd)" rev-parse validation-baseline-v1^{commit} 2>/dev/null || echo "")
DATE_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

TREES=(
  "of_runs"
  "of_runs_tfreeze"
  "of_work"
  "of_work_tfreeze"
  "e15_2_runs"
  "e15_2b_runs"
  "e15_2c_runs"
  "rung_b_midt"
)

{
  echo "# E15 trajectory archive MANIFEST"
  echo ""
  echo "**Generated (UTC):** $DATE_UTC  "
  echo "**Producing commit (HEAD):** \`$COMMIT\`  "
  if [[ -n "$TAG_CANON" ]]; then
    echo "**Frozen baseline tag:** \`validation-baseline-v1\` → \`$TAG_CANON\`  "
    echo "**Alias tag:** \`e15-conform-baseline-v1\` (same commit)  "
  fi
  echo ""
  echo "Maps / gates / thesis tables are in git. These trees are **gitignored** (~GBs)"
  echo "and must live on durable storage (LONI project space or external drive)."
  echo "Sync helper: \`bash validation/zeroD/e15_sync_archives.sh \$DEST\`."
  echo ""
  echo "## Tree sizes"
  echo ""
  echo "| Tree | Exists | Size |"
  echo "|------|:------:|-----:|"
} > "$OUT"

for t in "${TREES[@]}"; do
  p="$CONF/$t"
  if [[ -d "$p" ]]; then
    sz=$(du -sh "$p" | awk '{print $1}')
    echo "| \`$t/\` | yes | $sz |" >> "$OUT"
  else
    echo "| \`$t/\` | no | — |" >> "$OUT"
  fi
done

{
  echo ""
  echo "## File SHA-256"
  echo ""
  echo "Paths relative to \`e15_conformance/\`. Empty / missing trees omitted."
  echo ""
  echo "| SHA-256 | Bytes | Path |"
  echo "|---------|------:|------|"
} >> "$OUT"

# Hash regular files under existing trees (skip enormous? hash all for reproducibility)
for t in "${TREES[@]}"; do
  p="$CONF/$t"
  [[ -d "$p" ]] || continue
  # Prefer shasum (macOS); fall back to sha256sum
  if command -v shasum >/dev/null 2>&1; then
    HASH_CMD=(shasum -a 256)
  else
    HASH_CMD=(sha256sum)
  fi
  # Find files; hash one-by-one to stream into markdown
  find "$p" -type f -print0 | sort -z | while IFS= read -r -d '' f; do
    rel="${f#"$CONF"/}"
    bytes=$(wc -c < "$f" | tr -d ' ')
    hash=$("${HASH_CMD[@]}" "$f" | awk '{print $1}')
    echo "| \`$hash\` | $bytes | \`$rel\` |"
  done >> "$OUT"
done

echo "" >> "$OUT"
echo "## Notes" >> "$OUT"
echo "" >> "$OUT"
echo "- \`chemFoam.out\` / field dumps are the thesis-figure backing data for the 38-condition maps." >> "$OUT"
echo "- After sync, verify with: \`shasum -a 256 -c <(awk ...)\` or re-run this script and diff." >> "$OUT"
echo "" >> "$OUT"
echo "Wrote $OUT"
wc -l "$OUT"
