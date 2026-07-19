#!/usr/bin/env bash
# Run teacher-forced tool on MidT+NTC tapes inside Docker; write summary JSON.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export DOCKER_HOST="${DOCKER_HOST:-unix:///Users/el0tech/.colima/default/docker.sock}"
docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work --memory=7g \
  opencfd/openfoam-default:2312 \
  -lc 'set -e
       export LIBTORCH_DIR=/work/opt/libtorch
       export FOAM_USER_LIBBIN=/work/platforms/linuxARM64GccDPInt32Opt/lib
       export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$LIBTORCH_DIR/lib
       export LD_PRELOAD=$LIBTORCH_DIR/lib/libtorch_cpu.so:$LIBTORCH_DIR/lib/libc10.so:$LIBTORCH_DIR/lib/libomp-b8e5bcfb.so
       export TORCH_MKLDNN_ENABLED=0 OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE
       BIN=/work/platforms/linuxARM64GccDPInt32Opt/bin/e16_3b_teacher_forced
       ROOTR=/work/validation/e16_parity/e16_3b_runs
       for label in MidT NTC; do
         d=$ROOTR/${label}_python
         test -f $d/state_tape.csv
         $BIN --tape $d/state_tape.csv --mean $d/obs_rms_mean.txt \
           --var $d/obs_rms_var.txt --policy /work/policy/policy.ts \
           --out $ROOTR/${label}_teacher_forced.csv --conf 0.6
       done
       python3 - <<PY
import csv, json
from pathlib import Path
root = Path("/work/validation/e16_parity/e16_3b_runs")
summary = {"by_label": {}, "n_total": 0, "n_agree": 0}
for label in ("MidT", "NTC"):
    out = root / f"{label}_teacher_forced.csv"
    rows = list(csv.DictReader(out.open()))
    n = len(rows)
    agree = sum(1 for row in rows if row["agree"] == "1")
    mism = [row for row in rows if row["agree"] != "1"]
    mism_s = sorted(mism, key=lambda r: -float(r["margin"]))[:20]
    summary["by_label"][label] = {
        "n": n,
        "n_agree": agree,
        "n_mismatch": n - agree,
        "agree_pct": round(100.0 * agree / max(n, 1), 4),
        "mismatches": [
            {
                "step": int(float(m["step_index"])),
                "T": float(m["T"]),
                "of_flag": int(float(m["of_flag"])),
                "py_flag": int(float(m["py_flag"])),
                "of_p": float(m["of_p"]),
                "py_p": float(m["py_p"]),
                "margin": float(m["margin"]),
            }
            for m in mism_s
        ],
    }
    summary["n_total"] += n
    summary["n_agree"] += agree
summary["agree_pct"] = round(100.0 * summary["n_agree"] / max(summary["n_total"], 1), 4)
summary["pass"] = summary["agree_pct"] >= 99.0
(root / "teacher_forced_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
PY
       '
