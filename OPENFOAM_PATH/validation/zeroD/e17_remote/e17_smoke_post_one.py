#!/usr/bin/env python3
"""Per-mode E17 smoke metrics: chem imbalance, OOD, progress summary."""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def chem_stats_from_log(log: Path) -> dict:
    text = log.read_text(errors="ignore") if log.is_file() else ""
    times = [float(m.group(1)) for m in re.finditer(r"^Time = ([0-9.eE+-]+)", text, re.M)]
    tmax = [float(b) for a, b in re.findall(r"min/max\(T\) = ([0-9.eE+-]+), ([0-9.eE+-]+)", text)]
    ps = [(float(a), float(b)) for a, b in re.findall(r"propSanity: T ([0-9.eE+-]+) ([0-9.eE+-]+)", text)]
    wall = None
    m = re.search(r"wall_s=(\d+)", text)
    if not m and (log.parent / "wall.txt").is_file():
        m = re.search(r"wall_s=(\d+)", (log.parent / "wall.txt").read_text())
    if m:
        wall = int(m.group(1))
    n = max(len(times), 1)
    return {
        "n_steps": len(times),
        "last_Time": times[-1] if times else None,
        "max_field_T": max(tmax, default=None),
        "max_internal_T": max((b for _, b in ps), default=None),
        "wall_s": wall,
        "mean_s_per_step": (wall / n) if wall and n else None,
        "FOAM_FATAL": "FOAM FATAL" in text,
        "SIGFPE": "Floating point exception" in text or "Signal: Floating point exception" in text,
    }


def ood_fraction(decisions: Path) -> float | None:
    if not decisions.is_file():
        return None
    n = ood = 0
    with decisions.open() as f:
        r = csv.DictReader(f)
        for row in r:
            if "p" not in row:
                continue
            try:
                p = float(row["p"])
            except ValueError:
                continue
            n += 1
            if abs(p - 0.5) < 0.1:
                ood += 1
    return (ood / n) if n else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--mode", required=True)
    ap.add_argument("--end-time", type=float, default=5e-4)
    args = ap.parse_args()
    log = args.run_dir / f"log.{args.mode}"
    summary = chem_stats_from_log(log)
    summary["mode"] = args.mode
    summary["ood_frac"] = ood_fraction(args.run_dir / "rl_decisions.csv")
    summary["endTime_target"] = args.end_time
    (args.run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
