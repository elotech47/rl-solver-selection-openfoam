#!/usr/bin/env python3
"""E11.2 — Kinetic invariance: original YAML vs refit YAML."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cantera as ct
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def ignition_delay(yaml: Path, T0: float, P: float, X: dict, T_thresh: float = 400.0) -> float:
    gas = ct.Solution(str(yaml))
    gas.TPX = T0, P, X
    r = ct.IdealGasConstPressureReactor(gas)
    sim = ct.ReactorNet([r])
    t_end = 0.1
    T_ign = T0 + T_thresh
    while sim.time < t_end and r.T < T_ign:
        sim.step()
    if r.T < T_ign:
        return float("nan")
    return float(sim.time)


def midt_moles() -> dict:
    return {
        "o2": 0.20775813522367179,
        "n2": 0.7811705884410058,
        "nc12h26": 0.01107127633532227,
    }


def rate_spot_check(yaml0: Path, yaml1: Path, n: int = 50, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    g0 = ct.Solution(str(yaml0))
    g1 = ct.Solution(str(yaml1))
    assert g0.n_reactions == g1.n_reactions
    X = midt_moles()
    # Burnt-ish and mid states: mix fresh + equilibrium
    g0.TPX = 800.0, 10 * ct.one_atm, X
    g0.equilibrate("HP")
    Y_eq = g0.Y.copy()
    g0.TPX = 800.0, 10 * ct.one_atm, X
    Y_fresh = g0.Y.copy()

    max_fwd = 0.0
    max_rev = 0.0
    max_Kc = 0.0
    worst = None
    for _ in range(n):
        T = float(rng.uniform(800.0, 2800.0))
        a = float(rng.uniform(0.0, 1.0))
        Y = a * Y_eq + (1 - a) * Y_fresh
        Y = np.maximum(Y, 0)
        Y /= Y.sum()
        P = 10 * ct.one_atm
        g0.TPY = T, P, Y
        g1.TPY = T, P, Y
        kf0, kf1 = g0.forward_rate_constants, g1.forward_rate_constants
        kr0, kr1 = g0.reverse_rate_constants, g1.reverse_rate_constants
        Kc0, Kc1 = g0.equilibrium_constants, g1.equilibrium_constants
        for arr0, arr1, label, bucket in (
            (kf0, kf1, "fwd", "max_fwd"),
            (kr0, kr1, "rev", "max_rev"),
            (Kc0, Kc1, "Kc", "max_Kc"),
        ):
            denom = np.maximum(np.abs(arr0), 1e-30)
            rel = np.abs(arr1 - arr0) / denom
            i = int(np.argmax(rel))
            if rel[i] > {"max_fwd": max_fwd, "max_rev": max_rev, "max_Kc": max_Kc}[bucket]:
                if bucket == "max_fwd":
                    max_fwd = float(rel[i])
                elif bucket == "max_rev":
                    max_rev = float(rel[i])
                else:
                    max_Kc = float(rel[i])
                worst = dict(
                    kind=label,
                    T=T,
                    i=i,
                    rel=float(rel[i]),
                    reaction=g0.reaction(i).equation,
                )
    return dict(max_fwd=max_fwd, max_rev=max_rev, max_Kc=max_Kc, worst=worst)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--orig",
        type=Path,
        default=ROOT / "mechanisms/n-dodecane.yaml",
    )
    ap.add_argument(
        "--refit",
        type=Path,
        default=ROOT / "mechanisms/refit/n-dodecane_refit.yaml",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "mechanisms/refit/e11_2_kinetic",
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    X = midt_moles()
    grid = []
    for T0 in (750.0, 800.0, 1000.0):
        for p_atm in (10.0, 30.0, 60.0):
            P = p_atm * ct.one_atm
            t0 = ignition_delay(args.orig, T0, P, X)
            t1 = ignition_delay(args.refit, T0, P, X)
            drel = (t1 - t0) / t0 if t0 == t0 and t0 > 0 else float("nan")
            grid.append(
                dict(T0=T0, p_atm=p_atm, tau_orig=t0, tau_refit=t1, drel=drel)
            )
            print(
                f"T0={T0:g} p={p_atm:g}atm  τ_orig={t0*1e3:.4f}ms  "
                f"τ_refit={t1*1e3:.4f}ms  Δ={100*drel:+.4f}%"
            )

    rates = rate_spot_check(args.orig, args.refit)
    print(
        f"rate spot: max|Δkf|/kf={100*rates['max_fwd']:.4f}%  "
        f"max|Δkr|/kr={100*rates['max_rev']:.4f}%  "
        f"max|ΔKc|/Kc={100*rates['max_Kc']:.4f}%"
    )

    max_drel = max(abs(r["drel"]) for r in grid)
    gate_ign = max_drel <= 0.005
    report = dict(
        grid=grid,
        max_abs_drel_ign=max_drel,
        gate_ign_0p5pct=gate_ign,
        rates=rates,
    )
    (args.out / "summary.json").write_text(json.dumps(report, indent=2))

    lines = [
        "# E11.2 kinetic invariance\n\n",
        f"|Δτ_ign|_max = **{100*max_drel:.4f}%**  gate ≤0.5%: "
        f"**{'PASS' if gate_ign else 'FAIL'}**\n\n",
        "| T0 [K] | p [atm] | τ_orig [ms] | τ_refit [ms] | Δ |\n",
        "|-------:|--------:|------------:|-------------:|--:|\n",
    ]
    for r in grid:
        lines.append(
            f"| {r['T0']:g} | {r['p_atm']:g} | {r['tau_orig']*1e3:.4f} | "
            f"{r['tau_refit']*1e3:.4f} | {100*r['drel']:+.4f}% |\n"
        )
    lines.append(
        f"\nRate spot (50 states): max fwd {100*rates['max_fwd']:.4f}%, "
        f"rev {100*rates['max_rev']:.4f}%, Kc {100*rates['max_Kc']:.4f}%\n"
    )
    (args.out / "SUMMARY.md").write_text("".join(lines))
    print("".join(lines))
    return 0 if gate_ign else 2


if __name__ == "__main__":
    raise SystemExit(main())
