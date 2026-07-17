#!/usr/bin/env python3
"""Plot solverFlag maps / space-time composites from exported numpy fields."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solver-flag", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("solver_map.png"))
    args = ap.parse_args()
    flag = np.load(args.solver_flag)
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib missing; wrote nothing")
        return
    plt.figure(figsize=(6, 4))
    if flag.ndim == 1:
        plt.plot(flag, lw=0.5)
        plt.ylabel("solverFlag (0=CVODE,1=QSS)")
    else:
        plt.imshow(flag, aspect="auto", origin="lower", cmap="coolwarm")
        plt.colorbar(label="solverFlag")
    plt.tight_layout()
    plt.savefig(args.out, dpi=150)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
