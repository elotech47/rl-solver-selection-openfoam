#!/usr/bin/env python3
"""Post-process metrics for RL chemistry 2D cases (RMSE, usage, speedup)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def rmse(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    return float(np.sqrt(np.mean((a - b) ** 2)))


def summarize(cvode_dir: Path, case_dir: Path, label: str) -> dict:
    """Expect numpy exports: T.npy, OH.npy, solverFlag.npy, wall_time.json."""
    out = {"label": label, "case": str(case_dir)}
    for name in ("T", "OH"):
        ref = cvode_dir / f"{name}.npy"
        run = case_dir / f"{name}.npy"
        if ref.is_file() and run.is_file():
            out[f"rmse_{name}"] = rmse(np.load(ref), np.load(run))
    sf = case_dir / "solverFlag.npy"
    if sf.is_file():
        flag = np.load(sf)
        out["cvode_fraction"] = float(np.mean(flag == 0))
        out["qss_fraction"] = float(np.mean(flag == 1))
    for d, key in ((cvode_dir, "wall_cvode"), (case_dir, "wall_case")):
        w = d / "wall_time.json"
        if w.is_file():
            out[key] = json.loads(w.read_text()).get("seconds")
    if out.get("wall_cvode") and out.get("wall_case"):
        out["speedup"] = out["wall_cvode"] / max(out["wall_case"], 1e-30)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cvode-dir", type=Path, required=True)
    ap.add_argument("--case-dir", type=Path, required=True)
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    s = summarize(args.cvode_dir, args.case_dir, args.label)
    print(json.dumps(s, indent=2))
    if args.out:
        args.out.write_text(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
