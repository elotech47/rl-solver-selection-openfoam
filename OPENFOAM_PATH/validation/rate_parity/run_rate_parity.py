#!/usr/bin/env python3
"""
Rate parity (rung a): Cantera net ω̇ and FR progress rates at pinned states.
Also writes OF-ready JSON dump for container-side comparison.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MECH = ROOT / "mechanisms" / "n-dodecane.yaml"


def sample_states(gas, n: int, rng: np.random.Generator):
    """Sample T, P, mixture states including partially-burnt from 0D."""
    import cantera as ct

    states = []
    fuel = "nc12h26:1.0"
    ox = "o2:1.0, n2:3.76"
    # Grid spanning plan ranges
    for _ in range(n // 2):
        T = rng.uniform(600, 2800)
        P = rng.uniform(1, 60) * ct.one_atm
        Z = rng.uniform(0.01, 0.2)
        gas.set_equivalence_ratio(Z / (1 - Z) * 0.0 + 1.0, fuel, ox)  # reset
        gas.TP = T, P
        # Use mixture fraction via unburnt mixing
        gas.set_mixture_fraction(Z, fuel, ox)
        gas.TP = T, P
        states.append((T, P, gas.Y.copy(), "fresh"))

    # Partially burnt: short 0D integration
    for _ in range(n - len(states)):
        T0 = rng.uniform(700, 1200)
        P = rng.choice([1, 10, 30, 60]) * ct.one_atm
        Z = rng.choice([0.042, 0.062, 0.1])
        gas.set_mixture_fraction(Z, fuel, ox)
        gas.TP = T0, P
        r = ct.IdealGasConstPressureReactor(gas)
        sim = ct.ReactorNet([r])
        try:
            sim.advance(rng.uniform(1e-5, 5e-4))
        except Exception:
            pass
        states.append((gas.T, gas.P, gas.Y.copy(), "partial"))
    return states


def eval_rates(gas):
    """Return net production, creation, destruction, and FR progress arrays."""
    net = gas.net_production_rates.copy()  # kmol/m3/s
    create = gas.creation_rates.copy()
    destroy = gas.destruction_rates.copy()
    # Per-reaction forward/reverse
    fwd = gas.forward_rates_of_progress.copy()
    rev = gas.reverse_rates_of_progress.copy()
    return {
        "net": net,
        "creation": create,
        "destruction": destroy,
        "qf": fwd,
        "qr": rev,
        "T": gas.T,
        "P": gas.P,
        "Y": gas.Y.copy(),
        "species": gas.species_names,
    }


def rel_err(a, b, eps=1e-30):
    return np.abs(a - b) / (np.maximum(np.abs(b), eps))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-states", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--mech", type=Path, default=MECH)
    ap.add_argument(
        "--of-dump",
        type=Path,
        default=ROOT / "validation" / "rate_parity" / "of_states.json",
        help="States for OpenFOAM-side recompute",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "validation" / "rate_parity" / "rate_parity_report.json",
    )
    args = ap.parse_args()

    try:
        import cantera as ct
    except ImportError:
        print("Need cantera (pip install -e handoff / rlEnv)", file=sys.stderr)
        return 1

    if not args.mech.is_file():
        print(f"Missing mechanism {args.mech}", file=sys.stderr)
        return 1

    gas = ct.Solution(str(args.mech))
    rng = np.random.default_rng(args.seed)
    states = sample_states(gas, args.n_states, rng)

    # Cantera self-consistency: creation - destruction ≈ net
    max_net_split = 0.0
    outliers = []
    dump = []
    for T, P, Y, tag in states:
        gas.TPY = T, P, Y
        r = eval_rates(gas)
        split_net = r["creation"] - r["destruction"]
        err = rel_err(split_net, r["net"])
        # Meaningful nets; skip thermo-edge states (NASA polys ~300–3000 K)
        mask = (np.abs(r["net"]) > 1e-8) & (T <= 2800.0) & (T >= 600.0)
        if mask.any():
            m = float(np.max(err[mask]))
            max_net_split = max(max_net_split, m)
            if m > 1e-3:
                outliers.append(
                    {
                        "tag": tag,
                        "T": T,
                        "P": P,
                        "max_rel_creation_minus_destruction_vs_net": m,
                    }
                )
        dump.append(
            {
                "T": float(T),
                "P": float(P),
                "Y": Y.tolist(),
                "tag": tag,
                "cantera_net": r["net"].tolist(),
                "cantera_qf": r["qf"].tolist(),
                "cantera_qr": r["qr"].tolist(),
            }
        )

    report = {
        "n_states": len(states),
        "mechanism": str(args.mech),
        "n_species": gas.n_species,
        "n_reactions": gas.n_reactions,
        "max_rel_err_creation_minus_destruction_vs_net": max_net_split,
        "n_outliers_gt_0.1pct": len(outliers),
        "outliers_sample": outliers[:10],
        "acceptance": {
            "target": "OF vs Cantera rates ≤ 0.1% relative",
            "note": (
                "This script validates Cantera oracle self-consistency and "
                "writes states for OF comparison. Run of_rate_dump utility "
                "in Docker and compare with compare_of_cantera.py."
            ),
            "cantera_qd_self_consistent": max_net_split <= 1e-3,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    args.of_dump.write_text(json.dumps({"states": dump[:50]}, indent=2))  # cap size
    print(json.dumps(report["acceptance"], indent=2))
    print(f"Wrote {args.out}")
    return 0 if report["acceptance"]["cantera_qd_self_consistent"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
