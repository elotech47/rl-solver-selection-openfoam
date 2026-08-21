#!/usr/bin/env bash
# Pack small artifacts from a production run for scp / thesis tables.
# Usage: bash production/scripts/30_extract_results.sh production/runs/<run_id>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BASE="${1:?path to production/runs/<id>}"
[[ -d "$BASE" ]] || { echo "missing $BASE" >&2; exit 1; }

PACK="$BASE/extract_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$PACK"

cp -f "$BASE/MANIFEST.txt" "$BASE/stage2_header.txt" "$BASE/freeze_time.txt" "$PACK/" 2>/dev/null || true
cp -f "$BASE/DONE.txt" "$BASE/failures.txt" "$PACK/" 2>/dev/null || true

python3 - <<PY
import json, re
from pathlib import Path
base = Path(r"$BASE")
pack = Path(r"$PACK")
summary = {"base": str(base), "modes": {}}
for mode_dir in sorted(base.iterdir()):
    if not mode_dir.is_dir() or mode_dir.name.startswith("case_") or mode_dir.name.startswith("extract_"):
        continue
    mode = mode_dir.name
    prog = mode_dir / f"progress.{mode}.log"
    if not prog.is_file():
        # try generic
        cands = list(mode_dir.glob("progress*.log"))
        prog = cands[0] if cands else None
    info = {"dir": str(mode_dir)}
    wall = mode_dir / "wall.txt"
    if wall.is_file():
        info["wall_txt"] = wall.read_text().strip()
    tmax = []
    last_usage = None
    if prog and prog.is_file():
        pack.joinpath(f"progress.{mode}.log").write_bytes(prog.read_bytes())
        for line in prog.read_text(errors="replace").splitlines():
            m = re.search(r"t=([0-9.eE+-]+) (?:maxT|Tmax)=([0-9.eE+-]+)", line)
            if m:
                tmax.append({"t": float(m.group(1)), "Tmax": float(m.group(2))})
            if line.startswith("rlUsage"):
                last_usage = line
        info["n_tmax"] = len(tmax)
        if tmax:
            info["Tmax_last"] = tmax[-1]
            info["Tmax_peak"] = max(tmax, key=lambda x: x["Tmax"])
        info["last_rlUsage"] = last_usage
    # ClockTime from foam log if present
    for log in mode_dir.glob("log.*"):
        if log.name.startswith("log.reconstruct"):
            continue
        clock = None
        end_ok = False
        with log.open(errors="replace") as f:
            for line in f:
                if "ClockTime =" in line:
                    clock = line.strip()
                if line.strip() == "End":
                    end_ok = True
        info["last_ClockTime"] = clock
        info["foam_End"] = end_ok
        # copy only first 2k lines + last 200 lines is huge; skip full log
        break
    summary["modes"][mode] = info
pack.joinpath("summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
PY

# Optional: reuse e17 extract pattern if present
if [[ -x "$ROOT/validation/zeroD/e17_remote/02_extract_results.sh" ]]; then
  echo "(e17 extract helper available but production uses summary.json above)"
fi

echo "PACK=$PACK"
tar -C "$BASE" -czf "$PACK.tgz" "$(basename "$PACK")"
echo "TGZ=$PACK.tgz"
