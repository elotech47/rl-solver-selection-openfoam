#!/usr/bin/env bash
# Sync gitignored E15 trajectory trees to durable storage.
#
# Usage:
#   export E15_ARCHIVE_DEST=/path/to/LONI_or_external/e15_conformance_archives
#   bash validation/zeroD/e15_sync_archives.sh
#   # or:
#   bash validation/zeroD/e15_sync_archives.sh /path/to/dest
#
# Destination layout:
#   $DEST/validation-baseline-v1/<commit-short>/of_runs/...
#   $DEST/validation-baseline-v1/<commit-short>/MANIFEST.md
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONF="$ROOT/validation/zeroD/e15_conformance"
REPO="$(cd "$ROOT/.." && pwd)"
COMMIT=$(git -C "$REPO" rev-parse --short HEAD)
DEST_ROOT="${1:-${E15_ARCHIVE_DEST:-}}"

if [[ -z "$DEST_ROOT" ]]; then
  cat <<EOF
ERROR: no destination.

Set E15_ARCHIVE_DEST or pass a path, e.g.:
  # LONI (example — replace with your project allocation path)
  export E15_ARCHIVE_DEST=/work/\$USER/solver_selection_archives/e15_conformance
  # External drive
  export E15_ARCHIVE_DEST=/Volumes/BACKUP/solver_selection/e15_conformance

Then:
  bash validation/zeroD/e15_write_manifest.sh
  bash validation/zeroD/e15_sync_archives.sh
EOF
  exit 2
fi

DEST="$DEST_ROOT/validation-baseline-v1/$COMMIT"
mkdir -p "$DEST"

echo "Syncing E15 trees → $DEST"
TREES=(of_runs of_runs_tfreeze of_work of_work_tfreeze e15_2_runs e15_2b_runs e15_2c_runs rung_b_midt)
for t in "${TREES[@]}"; do
  src="$CONF/$t"
  if [[ -d "$src" ]]; then
    echo "  rsync $t/"
    rsync -a --stats "$src/" "$DEST/$t/"
  else
    echo "  skip missing $t/"
  fi
done

# Manifest + frozen docs snapshot (small)
[[ -f "$CONF/MANIFEST.md" ]] || bash "$ROOT/validation/zeroD/e15_write_manifest.sh"
cp -f "$CONF/MANIFEST.md" "$DEST/MANIFEST.md"
cp -f "$CONF/FROZEN_VALIDATION_BASELINE_v1.md" "$DEST/" 2>/dev/null || true
cp -f "$CONF/FROZEN_RUNG_BC_ACCEPTANCE.md" "$DEST/" 2>/dev/null || true
echo "$COMMIT" > "$DEST/PRODUCING_COMMIT.txt"
git -C "$REPO" rev-parse validation-baseline-v1^{commit} > "$DEST/TAG_validation-baseline-v1.txt" 2>/dev/null || true

echo "Done. Verify sizes:"
du -sh "$DEST"/* 2>/dev/null | head -20
echo "Archive root: $DEST"
