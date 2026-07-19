#!/usr/bin/env python3
"""E16.3b — decisions vs progress variable T (OF vs Python)."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "validation/e16_parity/e16_3b_runs"


def load_py(label: str):
    p = RUNS / f"{label}_python" / "decisions.csv"
    rows = np.genfromtxt(p, delimiter=",", names=True, dtype=None, encoding=None)
    return rows["T"], rows["executed_action"], rows["p"]


def load_of(label: str):
    p = RUNS / f"{label}_rlAdaptive" / "rl_decisions.csv"
    rows = np.genfromtxt(p, delimiter=",", names=True, dtype=None, encoding=None)
    return rows["T"], rows["flag"], rows["p"]


def plot_one(label: str, out: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    # Python
    if (RUNS / f"{label}_python" / "decisions.csv").is_file():
        T, a, p = load_py(label)
        axes[0].scatter(T, a, c=p, cmap="coolwarm", vmin=0, vmax=1, s=18, label="Py")
        axes[0].set_ylabel("action (0=CVODE,1=QSS)")
        axes[0].set_title(f"{label} — Python AdaptiveRL")
        axes[0].set_yticks([0, 1])
    # OF
    if (RUNS / f"{label}_rlAdaptive" / "rl_decisions.csv").is_file():
        T, a, p = load_of(label)
        sc = axes[1].scatter(T, a, c=p, cmap="coolwarm", vmin=0, vmax=1, s=18, label="OF")
        axes[1].set_ylabel("action (0=CVODE,1=QSS)")
        axes[1].set_xlabel("T [K] (progress variable)")
        axes[1].set_title(f"{label} — OpenFOAM rlAdaptive")
        axes[1].set_yticks([0, 1])
        fig.colorbar(sc, ax=axes, label="p = P(QSS)", fraction=0.03)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", choices=["MidT", "NTC", "both"], default="both")
    args = ap.parse_args()
    labels = ["MidT", "NTC"] if args.label == "both" else [args.label]
    for lab in labels:
        plot_one(lab, RUNS / f"{lab}_decisions_vs_T.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
