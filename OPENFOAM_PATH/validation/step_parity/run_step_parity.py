#!/usr/bin/env python3
"""
Single-step parity (rung b): 1 µs advance with Cantera-CVODE and Cantera-QSS.
Writes reference trajectories for OF comparison.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MECH = ROOT / "mechanisms" / "n-dodecane.yaml"
DT = 1e-6


def hard_case():
    """Pele known hard case ~800 K, 10 atm, Z≈0.062."""
    return dict(T=800.0, P_atm=10.0, Z=0.062, label="hard_800K_10atm")


def make_gas(mech, T, P_atm, Z):
    import cantera as ct

    gas = ct.Solution(str(mech))
    fuel = "nc12h26:1.0"
    ox = "o2:1.0, n2:3.76"
    gas.set_mixture_fraction(Z, fuel, ox)
    gas.TP = T, P_atm * ct.one_atm
    return gas


def step_cvode(gas, dt, rtol=1e-8, atol=1e-12):
    import cantera as ct

    r = ct.IdealGasConstPressureReactor(gas)
    sim = ct.ReactorNet([r])
    sim.rtol = rtol
    sim.atol = atol
    T0, Y0 = gas.T, gas.Y.copy()
    sim.advance(dt)
    return dict(T=gas.T, Y=gas.Y.copy(), T0=T0, Y0=Y0)


def step_qss(gas, dt):
    """Use handoff CanteraQSSODE + qss_integrator if available."""
    try:
        from solver_selection_handoff.utils import create_qss_solver
    except ImportError:
        return None

    import cantera as ct

    y = np.concatenate([[gas.T], gas.Y])
    config = dict(
        epsmin=0.02,
        epsmax=100.0,
        dtmin=1e-12,
        dtmax=1e-6,
        itermax=2,
        abstol=1e-11,
    )
    integ = create_qss_solver(gas, gas.P, config)
    integ.setState(y.tolist(), 0.0)
    ret = integ.integrateToTime(dt)
    yout = np.asarray(integ.y, dtype=float)
    gas.TPY = max(yout[0], 200.0), gas.P, np.maximum(yout[1:], 0.0)
    t_done = float(getattr(integ, "tn", dt))
    return dict(T=gas.T, Y=gas.Y.copy(), ret=int(ret), t_integrated=t_done)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mech", type=Path, default=MECH)
    ap.add_argument("--out", type=Path, default=ROOT / "validation" / "step_parity" / "step_refs.json")
    args = ap.parse_args()

    try:
        import cantera as ct  # noqa
    except ImportError:
        print("need cantera", file=sys.stderr)
        return 1

    cases = [
        hard_case(),
        dict(T=1000.0, P_atm=30.0, Z=0.042, label="highT_30atm"),
        dict(T=750.0, P_atm=60.0, Z=0.042, label="lowT_60atm"),
        dict(T=650.0, P_atm=1.0, Z=0.062, label="lowT_1atm"),
    ]
    # Extra random pins
    rng = np.random.default_rng(1)
    for i in range(46):
        cases.append(
            dict(
                T=float(rng.uniform(700, 1400)),
                P_atm=float(rng.choice([1, 10, 30, 60])),
                Z=float(rng.uniform(0.03, 0.12)),
                label=f"rand_{i}",
            )
        )

    refs = []
    for c in cases:
        gas = make_gas(args.mech, c["T"], c["P_atm"], c["Z"])
        Y0 = gas.Y.copy()
        T0 = gas.T
        P = gas.P
        gas_c = make_gas(args.mech, c["T"], c["P_atm"], c["Z"])
        cv = step_cvode(gas_c, DT)
        gas_q = make_gas(args.mech, c["T"], c["P_atm"], c["Z"])
        qs = step_qss(gas_q, DT)
        refs.append(
            {
                **c,
                "dt": DT,
                "P": P,
                "Y0": Y0.tolist(),
                "T0": T0,
                "cvode": {"T": cv["T"], "Y": cv["Y"].tolist()},
                "qss": None
                if qs is None
                else {"T": qs["T"], "Y": qs["Y"].tolist(), "ret": qs.get("ret")},
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"dt": DT, "n": len(refs), "refs": refs}, indent=2))
    n_qss = sum(1 for r in refs if r["qss"] is not None)
    print(f"Wrote {args.out} n={len(refs)} qss_ok={n_qss}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
