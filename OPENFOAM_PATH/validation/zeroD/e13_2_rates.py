#!/usr/bin/env python3
"""E13.2 — High-T rate parity: original vs refit Cantera (E7 closure on refit thermo).

Samples ~100 burnt/igniting MidT states at T∈[1500, 2900] K and compares forward,
reverse, and equilibrium constants between n-dodecane.yaml and n-dodecane_refit.yaml.
Gate: max relative error ≤ 0.1% for each of fwd, rev, Kc.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cantera as ct
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "validation/zeroD/e13_qss"
GATE = 0.001  # 0.1%


def midt_moles() -> dict[str, float]:
    return {
        "o2": 0.20775813522367179,
        "n2": 0.7811705884410058,
        "nc12h26": 0.01107127633532227,
    }


def sample_high_t_states(gas: ct.Solution, n: int, seed: int) -> list[tuple[float, float, np.ndarray]]:
    rng = np.random.default_rng(seed)
    X = midt_moles()
    gas.TPX = 800.0, 10 * ct.one_atm, X
    gas.equilibrate("HP")
    Y_eq = gas.Y.copy()
    gas.TPX = 800.0, 10 * ct.one_atm, X
    Y_fresh = gas.Y.copy()

    # Partially ignited trajectories for realistic burnt/igniting compositions
    partial: list[np.ndarray] = []
    for _ in range(max(n // 4, 10)):
        gas.TPX = 800.0, 10 * ct.one_atm, X
        r = ct.IdealGasConstPressureReactor(gas)
        sim = ct.ReactorNet([r])
        target_t = float(rng.uniform(1.5e-3, 2.8e-3))
        while sim.time < target_t and r.T < 2900:
            sim.step()
        if 1500 <= r.T <= 2900:
            partial.append(gas.Y.copy())

    states: list[tuple[float, float, np.ndarray]] = []
    P = 10 * ct.one_atm
    while len(states) < n:
        T = float(rng.uniform(1500.0, 2900.0))
        if partial and rng.random() < 0.6:
            Y = partial[rng.integers(len(partial))].copy()
        else:
            a = float(rng.uniform(0.3, 1.0))
            Y = a * Y_eq + (1 - a) * Y_fresh
        Y = np.maximum(Y, 0.0)
        Y /= Y.sum()
        states.append((T, P, Y))
    return states[:n]


def rate_parity(yaml0: Path, yaml1: Path, states: list) -> dict:
    g0 = ct.Solution(str(yaml0))
    g1 = ct.Solution(str(yaml1))
    assert g0.n_reactions == g1.n_reactions

    max_fwd = max_rev = max_Kc = 0.0
    worst = {"fwd": None, "rev": None, "Kc": None}

    for T, P, Y in states:
        g0.TPY = T, P, Y
        g1.TPY = T, P, Y
        pairs = (
            ("fwd", g0.forward_rate_constants, g1.forward_rate_constants),
            ("rev", g0.reverse_rate_constants, g1.reverse_rate_constants),
            ("Kc", g0.equilibrium_constants, g1.equilibrium_constants),
        )
        for kind, arr0, arr1 in pairs:
            denom = np.maximum(np.abs(arr0), 1e-30)
            rel = np.abs(arr1 - arr0) / denom
            i = int(np.argmax(rel))
            r = float(rel[i])
            bucket = f"max_{kind}" if kind != "Kc" else "max_Kc"
            cur = {"fwd": max_fwd, "rev": max_rev, "Kc": max_Kc}[kind]
            if r > cur:
                if kind == "fwd":
                    max_fwd = r
                elif kind == "rev":
                    max_rev = r
                else:
                    max_Kc = r
                worst[kind] = dict(
                    T=T,
                    i=i,
                    rel=r,
                    reaction=g0.reaction(i).equation,
                    k0=float(arr0[i]),
                    k1=float(arr1[i]),
                )

    return dict(
        n_states=len(states),
        max_fwd=max_fwd,
        max_rev=max_rev,
        max_Kc=max_Kc,
        worst=worst,
        gate_0p1pct=all(x <= GATE for x in (max_fwd, max_rev, max_Kc)),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--orig", type=Path, default=ROOT / "mechanisms/n-dodecane.yaml")
    ap.add_argument("--refit", type=Path, default=ROOT / "mechanisms/refit/n-dodecane_refit.yaml")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    gas = ct.Solution(str(args.refit))
    states = sample_high_t_states(gas, args.n, args.seed)
    Ts = np.array([s[0] for s in states])
    report = rate_parity(args.orig, args.refit, states)
    report["T_range"] = [float(Ts.min()), float(Ts.max())]
    report["mechanisms"] = dict(orig=str(args.orig.relative_to(ROOT)), refit=str(args.refit.relative_to(ROOT)))
    report["gate_threshold"] = GATE
    report["note"] = (
        "Cantera original vs Cantera-refit at identical (T,P,Y). "
        "OF rate export uses chemkin path; OF-vs-Cantera deferred to E7 chemkin dump."
    )

    (OUT / "e13_2_rates.json").write_text(json.dumps(report, indent=2))
    print(
        f"E13.2 rates ({report['n_states']} states, T∈[{report['T_range'][0]:.0f},{report['T_range'][1]:.0f}] K):\n"
        f"  max|Δkf|/kf = {100*report['max_fwd']:.6f}%\n"
        f"  max|Δkr|/kr = {100*report['max_rev']:.6f}%\n"
        f"  max|ΔKc|/Kc = {100*report['max_Kc']:.6f}%\n"
        f"  gate ≤0.1%: {'PASS' if report['gate_0p1pct'] else 'FAIL'}"
    )
    for kind in ("fwd", "rev", "Kc"):
        w = report["worst"][kind]
        if w:
            print(f"  worst {kind}: {100*w['rel']:.6f}% @ T={w['T']:.1f} K  {w['reaction']}")
    return 0 if report["gate_0p1pct"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
