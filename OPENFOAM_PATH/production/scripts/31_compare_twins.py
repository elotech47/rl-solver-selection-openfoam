#!/usr/bin/env python3
"""Compare production twin progress logs (ClockTime / Tmax) under a run directory.

Usage:
  python3 production/scripts/31_compare_twins.py production/runs/<run_id>
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def parse_progress(path: Path):
    rows, tmax = [], []
    text = path.read_text(errors="replace")
    for line in text.splitlines():
        m = re.search(
            r"rlUsage t=([0-9.eE+-]+) react=(\d+) CVODE=(\d+) QSS=(\d+) "
            r"fallbackCVODE=(\d+).*?cpu_tot(?:_sum)?=([0-9.eE+-]+)s"
            r"(?:.*?wall_chem=([0-9.eE+-]+)s)?",
            line,
        )
        if m:
            rows.append(
                {
                    "t": float(m.group(1)),
                    "CVODE": int(m.group(3)),
                    "QSS": int(m.group(4)),
                    "fb": int(m.group(5)),
                    "cpu_tot": float(m.group(6)),
                    "wall_chem": float(m.group(7)) if m.group(7) else None,
                }
            )
            continue
        m = re.search(r"t=([0-9.eE+-]+) (?:maxT|Tmax)=([0-9.eE+-]+)", line)
        if m:
            tmax.append((float(m.group(1)), float(m.group(2))))
    return rows, tmax


def first_cross(tmax, thresh: float):
    for t, T in tmax:
        if T >= thresh:
            return t, T
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--cut", type=float, default=None, help="compare through this sim time")
    args = ap.parse_args()
    base = args.run_dir
    modes = {}
    for d in sorted(base.iterdir()):
        if not d.is_dir() or d.name.startswith(("case_", "extract_")):
            continue
        progs = list(d.glob("progress*.log"))
        if not progs:
            continue
        rows, tmax = parse_progress(progs[0])
        if args.cut is not None:
            rows = [r for r in rows if r["t"] <= args.cut + 1e-12]
            tmax = [(t, T) for t, T in tmax if t <= args.cut + 1e-12]
        if not rows:
            continue
        modes[d.name] = {
            "last_t": rows[-1]["t"],
            "n_steps": len(rows),
            "cpu_tot_sum_h": sum(r["cpu_tot"] for r in rows) / 3600.0,
            "wall_chem_sum_h": (
                sum(r["wall_chem"] for r in rows if r["wall_chem"] is not None) / 3600.0
                if any(r["wall_chem"] is not None for r in rows)
                else None
            ),
            "mean_CVODE": sum(r["CVODE"] for r in rows) / len(rows),
            "mean_QSS": sum(r["QSS"] for r in rows) / len(rows),
            "fb_cellsteps": sum(r["fb"] for r in rows),
            "T_cross_1100": first_cross(tmax, 1100)[0],
            "T_peak": max((T for _, T in tmax), default=None),
            "T_last": tmax[-1][1] if tmax else None,
            "caveat": "rlUsage head-counts may disagree with solverFlag — see AGENTS.md",
        }

    out = {"run": str(base), "cut": args.cut, "modes": modes}
    if "cvodeOnly" in modes and "rlAdaptive" in modes:
        c, r = modes["cvodeOnly"], modes["rlAdaptive"]
        t_cut = min(c["last_t"], r["last_t"])
        out["note"] = (
            f"Shared last_t min={t_cut}; "
            f"cpu_sum ratio CVODE/RL={c['cpu_tot_sum_h']/r['cpu_tot_sum_h']:.2f}"
            if r["cpu_tot_sum_h"]
            else ""
        )
    print(json.dumps(out, indent=2))
    out_path = base / "compare_twins.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
