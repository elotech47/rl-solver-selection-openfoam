#!/usr/bin/env python3
"""E15 signature map — Py-CVODE / Py-QSS on pre-sized grid (OF separate).

Metrics per condition: τ_ign (dT=+400), Teq, ΔTeq, max|dZ|, wall.
"""
from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent / "handoff" / "src"))
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
OUT = ROOT / "validation/zeroD/e15_conformance"
PRE = OUT / "e15_presize.json"
ELEMS = ("C", "H", "O", "N")


def stub_sundials():
    if "SundialsPy" not in sys.modules:
        sp = types.ModuleType("SundialsPy")
        sp.cvode = types.ModuleType("SundialsPy.cvode")
        sys.modules["SundialsPy"] = sp
        sys.modules["SundialsPy.cvode"] = sp.cvode


def elemental_dZ(gas, Y0, Y1):
    W = gas.molecular_weights
    dmax = 0.0
    for el in ELEMS:
        Wi = gas.atomic_weight(el)
        z0 = z1 = 0.0
        for i in range(gas.n_species):
            n = gas.n_atoms(i, el)
            if n:
                z0 += Y0[i] * (n * Wi / W[i])
                z1 += Y1[i] * (n * Wi / W[i])
        dmax = max(dmax, abs(z1 - z0))
    return float(dmax)


def ign_and_teq(t, T, T0, dT=400.0):
    tau = float("nan")
    for ti, Ti in zip(t, T):
        if Ti >= T0 + dT:
            tau = float(ti)
            break
    return tau, float(T[-1])


def run_cvode(gas, T0, P, phi, t_end, dt=1e-6):
    import cantera as ct

    gas.set_equivalence_ratio(phi, "nc12h26:1.0", "o2:1.0, n2:3.76")
    gas.TP = T0, P
    Y0 = gas.Y.copy()
    r = ct.IdealGasConstPressureReactor(gas)
    sim = ct.ReactorNet([r])
    sim.rtol, sim.atol = 1e-8, 1e-12
    t_h, T_h = [0.0], [gas.T]
    t0 = time.perf_counter()
    while sim.time < t_end:
        sim.advance(min(sim.time + dt, t_end))
        t_h.append(sim.time)
        T_h.append(gas.T)
    wall = time.perf_counter() - t0
    tau, Teq = ign_and_teq(t_h, T_h, T0)
    return dict(
        tau_s=tau,
        Teq=Teq,
        maxAbs_dZ=elemental_dZ(gas, Y0, gas.Y),
        wall_s=wall,
        n_steps=len(t_h) - 1,
    )


def run_qss(gas, T0, P, phi, t_end, dt=1e-6):
    stub_sundials()
    from solver_selection_handoff.utils import create_qss_solver
    import cantera as ct

    gas.set_equivalence_ratio(phi, "nc12h26:1.0", "o2:1.0, n2:3.76")
    gas.TP = T0, P
    Y0 = gas.Y.copy()
    cfg = dict(
        epsmin=0.02, epsmax=100.0, dtmin=1e-12, dtmax=1e-6, itermax=2, abstol=1e-11
    )
    integ = create_qss_solver(gas, gas.P, cfg)
    t = 0.0
    t_h, T_h = [0.0], [gas.T]
    t0 = time.perf_counter()
    while t < t_end:
        dti = min(dt, t_end - t)
        y = np.concatenate([[gas.T], gas.Y])
        integ.setState(y.tolist(), 0.0)
        integ.integrateToTime(dti)
        yout = np.asarray(integ.y, dtype=float)
        gas.TPY = max(yout[0], 200.0), gas.P, np.maximum(yout[1:], 0.0)
        s = gas.Y.sum()
        if s > 0:
            gas.TPY = gas.T, gas.P, gas.Y / s
        t += dti
        t_h.append(t)
        T_h.append(gas.T)
    wall = time.perf_counter() - t0
    tau, Teq = ign_and_teq(t_h, T_h, T0)
    return dict(
        tau_s=tau,
        Teq=Teq,
        maxAbs_dZ=elemental_dZ(gas, Y0, gas.Y),
        wall_s=wall,
        n_steps=len(t_h) - 1,
    )


def main() -> int:
    import cantera as ct

    pre = json.loads(PRE.read_text())
    gas = ct.Solution(str(YAML))
    results = []
    for row in pre["rows"]:
        if row["skip"]:
            results.append({**row, "status": "skipped"})
            continue
        T0, p_atm, phi = row["T0"], row["p_atm"], row["phi"]
        P = p_atm * ct.one_atm
        tau_ct = row["tau_s"]
        t_end = min(0.05, max(3.5e-3, 3.0 * tau_ct))
        print(f"RUN T={T0:.0f} p={p_atm:.0f} φ={phi:.1f} t_end={t_end*1e3:.1f} ms")
        cv = run_cvode(gas, T0, P, phi, t_end)
        qs = run_qss(gas, T0, P, phi, t_end)
        results.append(
            dict(
                T0=T0,
                p_atm=p_atm,
                phi=phi,
                Z=row["Z"],
                tau_cantera_s=tau_ct,
                t_end_s=t_end,
                status="ok",
                py_cvode=cv,
                py_qss=qs,
                delta_Teq=qs["Teq"] - cv["Teq"],
                tau_ratio_qss_over_cvode=(
                    qs["tau_s"] / cv["tau_s"]
                    if cv["tau_s"] and qs["tau_s"] and cv["tau_s"] > 0
                    else None
                ),
                wall_ratio_cvode_over_qss=(
                    cv["wall_s"] / qs["wall_s"] if qs["wall_s"] > 0 else None
                ),
            )
        )
        print(
            f"  ΔTeq={qs['Teq']-cv['Teq']:+.1f} K  "
            f"dZ_qss={qs['maxAbs_dZ']:.2e} dZ_cv={cv['maxAbs_dZ']:.2e}  "
            f"wall cv/qss={cv['wall_s']/max(qs['wall_s'],1e-12):.1f}×"
        )

    report = dict(campaign="E15_signature_map_python", n=len(results), results=results)
    (OUT / "e15_signature_map_python.json").write_text(json.dumps(report, indent=2))
    # compact table
    lines = [
        "# E15 Python signature map",
        "",
        "| T0 | p [atm] | φ | ΔTeq [K] | τ_QSS/τ_CV | max\\|dZ\\| QSS | wall CV/QSS |",
        "|---:|--------:|--:|---------:|-----------:|-------------:|------------:|",
    ]
    for r in results:
        if r.get("status") != "ok":
            continue
        tr = r.get("tau_ratio_qss_over_cvode")
        wr = r.get("wall_ratio_cvode_over_qss")
        lines.append(
            f"| {r['T0']:.0f} | {r['p_atm']:.0f} | {r['phi']:.1f} | "
            f"{r['delta_Teq']:+.1f} | "
            f"{tr:.3f} | {r['py_qss']['maxAbs_dZ']:.2e} | {wr:.1f} |"
            if tr and wr
            else f"| {r['T0']:.0f} | {r['p_atm']:.0f} | {r['phi']:.1f} | "
            f"{r['delta_Teq']:+.1f} | — | {r['py_qss']['maxAbs_dZ']:.2e} | — |"
        )
    (OUT / "E15_SIGNATURE_MAP_PYTHON.md").write_text("\n".join(lines) + "\n")
    print("Wrote", OUT / "E15_SIGNATURE_MAP_PYTHON.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
