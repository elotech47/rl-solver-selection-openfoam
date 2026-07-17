#!/usr/bin/env python3
"""0D ignition delay grid (rung c reference) matching handoff paper ICs."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MECH = ROOT / "mechanisms" / "n-dodecane.yaml"

ICS = [
    dict(label="LowT_LowP", T=650, P_atm=1, Z=0.062, dt=1e-5, t_end=0.12),
    dict(label="MidT_MidP", T=800, P_atm=10, Z=0.062, dt=1e-6, t_end=3.5e-3),
    dict(label="HighT_HighP", T=1000, P_atm=30, Z=0.042, dt=1e-6, t_end=3e-3),
    dict(label="LowT_VeryHighP", T=750, P_atm=60, Z=0.042, dt=1e-6, t_end=2.5e-3),
]


def ignition_delay(T_hist, t_hist, T0, dT=400.0):
    target = T0 + dT
    for t, T in zip(t_hist, T_hist):
        if T >= target:
            return float(t)
    return float("nan")


def run_cvode(mech, ic):
    import cantera as ct

    gas = ct.Solution(str(mech))
    gas.set_mixture_fraction(ic["Z"], "nc12h26:1.0", "o2:1.0, n2:3.76")
    gas.TP = ic["T"], ic["P_atm"] * ct.one_atm
    r = ct.IdealGasConstPressureReactor(gas)
    sim = ct.ReactorNet([r])
    sim.rtol = 1e-8
    sim.atol = 1e-12
    t_hist, T_hist = [0.0], [gas.T]
    t0 = time.perf_counter()
    while sim.time < ic["t_end"]:
        sim.advance(min(sim.time + ic["dt"], ic["t_end"]))
        t_hist.append(sim.time)
        T_hist.append(gas.T)
    cpu = time.perf_counter() - t0
    return dict(
        ign=ignition_delay(T_hist, t_hist, ic["T"]),
        cpu=cpu,
        T_end=gas.T,
        solver="CVODE",
    )


def run_qss(mech, ic):
    try:
        from solver_selection_handoff.utils import create_qss_solver
    except ImportError:
        return None
    import cantera as ct

    gas = ct.Solution(str(mech))
    gas.set_mixture_fraction(ic["Z"], "nc12h26:1.0", "o2:1.0, n2:3.76")
    gas.TP = ic["T"], ic["P_atm"] * ct.one_atm
    config = dict(
        epsmin=0.02, epsmax=100.0, dtmin=1e-12, dtmax=1e-6, itermax=2, abstol=1e-11
    )
    integ = create_qss_solver(gas, gas.P, config)
    t = 0.0
    t_hist, T_hist = [0.0], [gas.T]
    t0 = time.perf_counter()
    while t < ic["t_end"]:
        dt = min(ic["dt"], ic["t_end"] - t)
        y = np.concatenate([[gas.T], gas.Y])
        integ.setState(y.tolist(), 0.0)
        integ.integrateToTime(dt)
        yout = np.asarray(integ.y, dtype=float)
        gas.TPY = max(yout[0], 200.0), gas.P, np.maximum(yout[1:], 0)
        s = gas.Y.sum()
        if s > 0:
            gas.TPY = gas.T, gas.P, gas.Y / s
        t += dt
        t_hist.append(t)
        T_hist.append(gas.T)
    cpu = time.perf_counter() - t0
    return dict(
        ign=ignition_delay(T_hist, t_hist, ic["T"]),
        cpu=cpu,
        T_end=gas.T,
        solver="QSS",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mech", type=Path, default=MECH)
    ap.add_argument("--out", type=Path, default=ROOT / "validation" / "zeroD" / "zeroD_refs.json")
    args = ap.parse_args()

    try:
        import cantera as ct  # noqa
    except ImportError:
        print("need cantera", file=sys.stderr)
        return 1

    results = []
    for ic in ICS:
        print(f"Running {ic['label']} ...", flush=True)
        cv = run_cvode(args.mech, ic)
        qs = run_qss(args.mech, ic)
        row = {"ic": ic, "cvode": cv, "qss": qs}
        if qs and cv["cpu"] > 0:
            row["cpu_ratio_qss_over_cvode"] = qs["cpu"] / cv["cpu"]
        results.append(row)
        print(f"  CVODE ign={cv['ign']:.4e}s cpu={cv['cpu']:.3f}s")
        if qs:
            print(f"  QSS   ign={qs['ign']:.4e}s cpu={qs['cpu']:.3f}s")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
