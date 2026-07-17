#!/usr/bin/env python3
"""Generate MidT T(t) trajectories (Python CVODE/QSS) and compare to OF."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MECH = ROOT / "mechanisms" / "n-dodecane.yaml"
OUTDIR = ROOT / "validation" / "zeroD" / "cvode_qss_compare"
IC = dict(label="MidT_MidP", T=800.0, P_atm=10.0, Z=0.062, dt=1e-6, t_end=3.5e-3)


def ignition_delay(t, T, T0=800.0, dT=400.0):
    target = T0 + dT
    for ti, Ti in zip(t, T):
        if Ti >= target:
            return float(ti)
    return float("nan")


def of_chemfoam_out(path: Path):
    t, T = [], []
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            t.append(float(parts[0]))
            T.append(float(parts[1]))
    return np.asarray(t), np.asarray(T)


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
    return np.asarray(t_hist), np.asarray(T_hist), cpu


def run_qss(mech, ic):
    # SundialsPy (declared by handoff) aborts on import under this OpenMPI
    # build when unused; stub it so create_qss_solver can load. QSS itself
    # only needs qss-integrator + Cantera.
    import sys
    import types

    if "SundialsPy" not in sys.modules:
        _sp = types.ModuleType("SundialsPy")
        _sp.cvode = types.ModuleType("SundialsPy.cvode")
        sys.modules["SundialsPy"] = _sp
        sys.modules["SundialsPy.cvode"] = _sp.cvode

    from solver_selection_handoff.utils import create_qss_solver
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
    return np.asarray(t_hist), np.asarray(T_hist), cpu


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print("Python CVODE...", flush=True)
    t_cv, T_cv, cpu_cv = run_cvode(MECH, IC)
    print("Python QSS...", flush=True)
    t_qs, T_qs, cpu_qs = run_qss(MECH, IC)

    of_cv = ROOT / "validation/zeroD/fix_verify/cvode/chemFoam.out"
    of_qs = ROOT / "validation/zeroD/fix_verify/qss/chemFoam.out"
    t_of_cv, T_of_cv = of_chemfoam_out(of_cv)
    t_of_qs, T_of_qs = of_chemfoam_out(of_qs)

    summary = {
        "ic": IC,
        "python": {
            "cvode": {"ign_s": ignition_delay(t_cv, T_cv), "T_end": float(T_cv[-1]), "cpu_s": cpu_cv},
            "qss": {"ign_s": ignition_delay(t_qs, T_qs), "T_end": float(T_qs[-1]), "cpu_s": cpu_qs},
        },
        "openfoam": {
            "cvode": {"ign_s": ignition_delay(t_of_cv, T_of_cv), "T_end": float(T_of_cv[-1])},
            "qss": {"ign_s": ignition_delay(t_of_qs, T_of_qs), "T_end": float(T_of_qs[-1])},
        },
    }
    # relative gaps
    py_cv = summary["python"]["cvode"]["ign_s"]
    summary["of_cvode_vs_py_cvode_pct"] = 100.0 * abs(summary["openfoam"]["cvode"]["ign_s"] - py_cv) / py_cv
    summary["py_qss_vs_py_cvode_pct"] = 100.0 * abs(summary["python"]["qss"]["ign_s"] - py_cv) / py_cv
    summary["of_qss_vs_py_cvode_pct"] = 100.0 * abs(summary["openfoam"]["qss"]["ign_s"] - py_cv) / py_cv
    (OUTDIR / "summary.json").write_text(json.dumps(summary, indent=2))

    np.savez_compressed(
        OUTDIR / "trajectories.npz",
        t_py_cvode=t_cv, T_py_cvode=T_cv,
        t_py_qss=t_qs, T_py_qss=T_qs,
        t_of_cvode=t_of_cv, T_of_cvode=T_of_cv,
        t_of_qss=t_of_qs, T_of_qss=T_of_qs,
    )

    # Main figure
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)

    ax = axes[0]
    ax.plot(t_cv * 1e3, T_cv, color="#1f77b4", lw=2.0, label="Python CVODE (Cantera)")
    ax.plot(t_qs * 1e3, T_qs, color="#ff7f0e", lw=2.0, ls="--", label="Python QSS (handoff)")
    ax.plot(t_of_cv * 1e3, T_of_cv, color="#2ca02c", lw=1.6, label="OpenFOAM CVODE")
    ax.plot(t_of_qs * 1e3, T_of_qs, color="#d62728", lw=1.6, ls="--", label="OpenFOAM QSS")
    ax.axhline(1200, color="0.5", ls=":", lw=0.8)
    ax.set_xlabel("t [ms]")
    ax.set_ylabel("T [K]")
    ax.set_title("MidT_MidP full history (800 K, 10 atm, Z=0.062)")
    ax.legend(fontsize=8, loc="lower right")
    ax.set_xlim(0, IC["t_end"] * 1e3)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    # Zoom around ignition
    t0, t1 = 1.7, 2.6
    ax.plot(t_cv * 1e3, T_cv, color="#1f77b4", lw=2.0, label="Python CVODE")
    ax.plot(t_qs * 1e3, T_qs, color="#ff7f0e", lw=2.0, ls="--", label="Python QSS")
    ax.plot(t_of_cv * 1e3, T_of_cv, color="#2ca02c", lw=1.6, label="OF CVODE")
    ax.plot(t_of_qs * 1e3, T_of_qs, color="#d62728", lw=1.6, ls="--", label="OF QSS")
    ax.axhline(1200, color="0.5", ls=":", lw=0.8)
    for name, ign, c in [
        ("Py CVODE", summary["python"]["cvode"]["ign_s"], "#1f77b4"),
        ("Py QSS", summary["python"]["qss"]["ign_s"], "#ff7f0e"),
        ("OF CVODE", summary["openfoam"]["cvode"]["ign_s"], "#2ca02c"),
        ("OF QSS", summary["openfoam"]["qss"]["ign_s"], "#d62728"),
    ]:
        ax.axvline(ign * 1e3, color=c, ls=":", lw=0.9, alpha=0.7)
    ax.set_xlabel("t [ms]")
    ax.set_title("Ignition window (τ_ign = T≥1200 K)")
    ax.set_xlim(t0, t1)
    ax.set_ylim(800, 2200)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.3)

    fig.suptitle(
        "CVODE vs QSS — OpenFOAM chemFoamDebug vs Python (Luo n-dodecane)",
        fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(OUTDIR / "cvode_qss_of_vs_python.png", dpi=160)
    fig.savefig(OUTDIR / "cvode_qss_of_vs_python.pdf")
    print("Wrote", OUTDIR / "cvode_qss_of_vs_python.png")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
