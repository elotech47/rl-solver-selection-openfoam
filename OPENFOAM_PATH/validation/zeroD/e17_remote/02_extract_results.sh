#!/usr/bin/env bash
# Pack E17 run logs + a compact summary.json for scp off the machine.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="${E17_OUT:?set E17_OUT to the run directory}"
# allow relative to ROOT
[[ "$OUT" = /* ]] || OUT="$ROOT/$OUT"
EX="$OUT/extract"
mkdir -p "$EX"

echo "[extract] $OUT"

python3 - <<PY
import json, re, csv
from pathlib import Path
out = Path("$OUT")
ex = Path("$EX")
log = out / "log.reactingFoam"
text = log.read_text(errors="ignore") if log.is_file() else ""
times = [float(m.group(1)) for m in re.finditer(r"^Time = ([0-9.eE+-]+)", text, re.M)]
tmax = [(float(a), float(b)) for a, b in re.findall(r"min/max\(T\) = ([0-9.eE+-]+), ([0-9.eE+-]+)", text)]
ps = [(float(a), float(b)) for a, b in re.findall(r"propSanity: T ([0-9.eE+-]+) ([0-9.eE+-]+)", text)]
wall = None
wt = out / "wall.txt"
if wt.is_file():
    m = re.search(r"wall_s=(\d+)", wt.read_text())
    if m:
        wall = int(m.group(1))
fatal = "FOAM FATAL" in text
ended = bool(re.search(r"^End\s*$", text, re.M))
summary = {
    "out": str(out),
    "wall_s": wall,
    "n_time_prints": len(times),
    "last_Time": times[-1] if times else None,
    "last_field_Tmax": tmax[-1][1] if tmax else None,
    "max_field_Tmax": max((b for _, b in tmax), default=None),
    "max_internal_T_propSanity": max((b for _, b in ps), default=None),
    "last_internal_T_propSanity": ps[-1][1] if ps else None,
    "FOAM_FATAL": fatal,
    "End": ended,
    "latest_time_dir": (out / "latest_time.txt").read_text().strip() if (out / "latest_time.txt").is_file() else None,
}
(ex / "summary.json").write_text(json.dumps(summary, indent=2))
# T trace CSV
with (ex / "T_trace.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["time", "field_Tmin", "field_Tmax", "prop_Tmin", "prop_Tmax"])
    # align loosely by order
    n = max(len(times), len(tmax), len(ps))
    for i in range(n):
        t = times[i] if i < len(times) else ""
        ft = tmax[i] if i < len(tmax) else ("", "")
        pt = ps[i] if i < len(ps) else ("", "")
        w.writerow([t, ft[0] if ft else "", ft[1] if ft else "", pt[0] if pt else "", pt[1] if pt else ""])
print(json.dumps(summary, indent=2))
PY

# bundle
cp -f "$OUT/log.reactingFoam" "$OUT/wall.txt" "$OUT/run_banner.txt" "$EX/" 2>/dev/null || true
cp -f "$OUT/controlDict" "$OUT/chemistryProperties" "$OUT/decomposeParDict" "$EX/" 2>/dev/null || true
cp -f "$OUT/log.blockMesh" "$OUT/log.decomposePar" "$EX/" 2>/dev/null || true
tar -C "$OUT" -czf "$EX/bundle.tgz" extract log.reactingFoam wall.txt run_banner.txt \
  controlDict chemistryProperties decomposeParDict fields 2>/dev/null \
  || tar -C "$EX" -czf "$EX/bundle.tgz" .
ls -la "$EX"
echo "[extract] DONE → $EX/bundle.tgz"
echo "scp -r <remote>:$EX ./e17_bringback/"
