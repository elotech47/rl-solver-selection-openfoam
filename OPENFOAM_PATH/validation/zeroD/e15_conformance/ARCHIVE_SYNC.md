# E15 trajectory archive — sync status

**Canonical baseline tag:** `validation-baseline-v1` → `823b1c2`  
**Alias:** `e15-conform-baseline-v1` (same commit)

## What’s on disk (laptop)

| Tree               | Approx size | Role                      |
| --------------------| ------------:| ---------------------------|
| `of_runs/`         | 575M        | Pre–T-freeze 38-map       |
| `of_runs_tfreeze/` | 92M         | Production CONFORM map    |
| `of_work*`         | ~160M       | Scratch worktrees         |
| `e15_2b_runs/`     | 1.2G        | T-freeze alone campaign   |
| `e15_2{,c}_runs/`  | ~57M        | Coeff / epsmin campaigns  |
| `rung_b_midt/`     | small       | Frozen rung (b) MidT 1 µs |

All of the above are **gitignored**. Maps, gates, and `MANIFEST.md` (SHA-256 catalog) are tracked or regenerable.

## Sync (do this before September figures)

**Synced 2026-07-19 → Lexar SD:**

```
/Volumes/Lexar/solver_selection_archives/e15_conformance/validation-baseline-v1/ac647e1/
```

(Includes run trees, `MANIFEST.md`, freeze docs, and tag/commit pointers.)

To refresh or copy elsewhere:

```bash
export E15_ARCHIVE_DEST=/Volumes/Lexar/solver_selection_archives/e15_conformance
# or another path (LONI, second drive, …)

cd OPENFOAM_PATH
bash validation/zeroD/e15_write_manifest.sh   # refresh SHA-256 catalog
bash validation/zeroD/e15_sync_archives.sh    # rsync trees + MANIFEST + freeze docs
```

Layout written:

```
$E15_ARCHIVE_DEST/validation-baseline-v1/<commit-short>/{of_runs,of_runs_tfreeze,...}/
$E15_ARCHIVE_DEST/validation-baseline-v1/<commit-short>/MANIFEST.md
$E15_ARCHIVE_DEST/validation-baseline-v1/<commit-short>/PRODUCING_COMMIT.txt
```

## Thesis citation

- Code freeze: tag **`validation-baseline-v1`**
- Envelope: `FROZEN_VALIDATION_BASELINE_v1.md`
- **0D acceptance table:** `FROZEN_RUNG_BC_ACCEPTANCE.md`
