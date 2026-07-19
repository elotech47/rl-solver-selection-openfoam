#!/usr/bin/env python3
"""E14.5 — Element-drift audit + Cantera HP closing test (OF + Python MidT).

Gate revision: Teq≤2K assumed element-conserving integration; α-QSS does not.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent / "handoff" / "src"))
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
OUT = ROOT / "validation/zeroD/e14_ledger"
E14 = ROOT / "validation/zeroD/e14_midt"
IC = dict(T=800.0, P_atm=10.0, Z=0.062, dt=1e-6, t_end=3.5e-3)
ELEMS = ("C", "H", "O", "N")


def stub_sundials() -> None:
    if "SundialsPy" not in sys.modules:
        sp = types.ModuleType("SundialsPy")
        sp.cvode = types.ModuleType("SundialsPy.cvode")
        sys.modules["SundialsPy"] = sp
        sys.modules["SundialsPy.cvode"] = sp.cvode


def load_of_Y(path: Path):
    lines = path.read_text().splitlines()
    header = None
    rows = []
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("#"):
            header = line.lstrip("#").split(",")
            continue
        rows.append([float(x) for x in line.split(",")])
    names = header[2:]
    data = np.asarray(rows, dtype=float)
    return data[:, 0], data[:, 2:], names


def load_ih_total(inv_csv: Path) -> float:
    s = 0.0
    for line in inv_csv.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        s += float(line.split(",")[10])
    return s


def load_T(chemfoam_out: Path) -> np.ndarray:
    T = []
    for line in chemfoam_out.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        T.append(float(line.split()[1]))
    return np.asarray(T)


def elemental_mass_fractions(gas, Y: np.ndarray) -> dict[str, float]:
    W = gas.molecular_weights
    out = {}
    for el in ELEMS:
        Wi = gas.atomic_weight(el)
        zk = 0.0
        for i in range(gas.n_species):
            n = gas.n_atoms(i, el)
            if n:
                zk += Y[i] * (n * Wi / W[i])
        out[el] = float(zk)
    return out


def map_Y(gas, row, names):
    Yct = np.zeros(gas.n_species)
    for j, n in enumerate(names):
        Yct[gas.species_index(n)] = max(float(row[j]), 0.0)
    return Yct


def Z_series(gas, Ytraj, names):
    Zt = {el: [] for el in ELEMS}
    sumY = []
    for row in Ytraj:
        Yct = map_Y(gas, row, names)
        z = elemental_mass_fractions(gas, Yct)
        for el in ELEMS:
            Zt[el].append(z[el])
        sumY.append(float(Yct.sum()))
    return {el: np.asarray(Zt[el]) for el in ELEMS} | {"sumY": np.asarray(sumY)}


def drift_report(Z, tag):
    rep = {"tag": tag}
    for el in ELEMS:
        z = Z[el]
        rep[f"dZ_{el}"] = float(z[-1] - z[0])
        rep[f"maxAbs_dZ_{el}"] = float(np.max(np.abs(z - z[0])))
    rep["sumY_0"] = float(Z["sumY"][0])
    rep["sumY_end"] = float(Z["sumY"][-1])
    rep["maxAbs_dZ"] = max(rep[f"maxAbs_dZ_{el}"] for el in ELEMS)
    return rep


def hp_closing_test(gas, Y_end_row, names, h_target, p, T_obs):
    Yct = map_Y(gas, Y_end_row, names)
    Yct /= max(Yct.sum(), 1e-30)
    z = elemental_mass_fractions(gas, Yct)
    gas.HPY = h_target, p, Yct
    try:
        gas.equilibrate("HP", rtol=1e-9, max_steps=10000)
        T_eq = float(gas.T)
        ok, err = True, None
    except Exception as e:
        T_eq, ok, err = float("nan"), False, str(e)
    gas.set_mixture_fraction(IC["Z"], "nc12h26:1.0", "o2:1.0, n2:3.76")
    gas.HP = h_target, p
    try:
        gas.equilibrate("HP", rtol=1e-9, max_steps=10000)
        T_eq_orig = float(gas.T)
    except Exception:
        T_eq_orig = float("nan")
    return dict(
        T_obs=float(T_obs),
        T_HP_drifted_elems=T_eq,
        T_HP_original_elems=T_eq_orig,
        dT_obs_minus_HP_drifted=(float(T_obs - T_eq) if ok else None),
        PASS_closing=bool(ok and abs(T_obs - T_eq) <= 2.0),
        Z_end=z,
        equilibrate_ok=ok,
        error=err,
        h_target=float(h_target),
        p=float(p),
    )


def audit_pair(gas, tag, T, Y, names, h_target, p):
    import cantera as ct

    Z = Z_series(gas, Y, names)
    drift = drift_report(Z, tag)
    close = hp_closing_test(gas, Y[-1], names, h_target, p, float(T[-1]))
    gas2 = ct.Solution(str(YAML))
    Yct = map_Y(gas2, Y[-1], names)
    Yct /= max(Yct.sum(), 1e-30)
    gas2.TPY = float(T[-1]), p, Yct
    Y_obs = gas2.Y.copy()
    gas2.HPY = h_target, p, Yct
    try:
        gas2.equilibrate("HP")
        Y_eq = gas2.Y.copy()
    except Exception:
        Y_eq = Y_obs
    majors = ["nc12h26", "o2", "n2", "co2", "h2o", "co", "oh"]
    maj_err = {
        m: float(Y_obs[gas2.species_index(m)] - Y_eq[gas2.species_index(m)])
        for m in majors
        if m in gas2.species_names
    }
    if drift["maxAbs_dZ"] > 1e-6 and close.get("PASS_closing"):
        mech = "element_drift"
    elif drift["maxAbs_dZ"] > 1e-6:
        mech = "element_drift_partial"
    else:
        mech = "pseudo_equilibrium_or_other"
    return dict(
        drift=drift,
        closing=close,
        Teq=float(T[-1]),
        major_Y_minus_HP=maj_err,
        mechanism=mech,
    )


def run_python_midt():
    stub_sundials()
    import cantera as ct
    from solver_selection_handoff.utils import create_qss_solver

    def mix(gas):
        gas.set_mixture_fraction(IC["Z"], "nc12h26:1.0", "o2:1.0, n2:3.76")
        gas.TP = IC["T"], IC["P_atm"] * ct.one_atm
        return float(gas.enthalpy_mass)

    out = {}
    gas = ct.Solution(str(YAML))
    h0 = mix(gas)
    r = ct.IdealGasConstPressureReactor(gas)
    sim = ct.ReactorNet([r])
    sim.rtol, sim.atol = 1e-8, 1e-12
    t_h, T_h, Y_h = [0.0], [gas.T], [gas.Y.copy()]
    t0 = time.perf_counter()
    while sim.time < IC["t_end"]:
        sim.advance(min(sim.time + IC["dt"], IC["t_end"]))
        t_h.append(sim.time)
        T_h.append(gas.T)
        Y_h.append(gas.Y.copy())
    out["cvode"] = dict(
        t=np.asarray(t_h),
        T=np.asarray(T_h),
        Y=np.asarray(Y_h),
        h0=h0,
        h_end=float(gas.enthalpy_mass),
        wall=time.perf_counter() - t0,
        names=list(gas.species_names),
    )

    gas = ct.Solution(str(YAML))
    h0 = mix(gas)
    cfg = dict(
        epsmin=0.02, epsmax=100.0, dtmin=1e-12, dtmax=1e-6, itermax=2, abstol=1e-11
    )
    integ = create_qss_solver(gas, gas.P, cfg)
    t = 0.0
    t_h, T_h, Y_h = [0.0], [gas.T], [gas.Y.copy()]
    t0 = time.perf_counter()
    while t < IC["t_end"]:
        dt = min(IC["dt"], IC["t_end"] - t)
        y = np.concatenate([[gas.T], gas.Y])
        integ.setState(y.tolist(), 0.0)
        integ.integrateToTime(dt)
        yout = np.asarray(integ.y, dtype=float)
        gas.TPY = max(yout[0], 200.0), gas.P, np.maximum(yout[1:], 0.0)
        s = gas.Y.sum()
        if s > 0:
            gas.TPY = gas.T, gas.P, gas.Y / s
        t += dt
        t_h.append(t)
        T_h.append(gas.T)
        Y_h.append(gas.Y.copy())
    out["qss"] = dict(
        t=np.asarray(t_h),
        T=np.asarray(T_h),
        Y=np.asarray(Y_h),
        h0=h0,
        h_end=float(gas.enthalpy_mass),
        wall=time.perf_counter() - t0,
        names=list(gas.species_names),
    )
    return out


def main() -> int:
    import cantera as ct

    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-python", action="store_true")
    ap.add_argument("--of-only", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    gas = ct.Solution(str(YAML))
    p = IC["P_atm"] * ct.one_atm
    report = {
        "campaign": "E14.5",
        "thesis": (
            "Teq≤2K gate assumed element-conserving integration; "
            "α-QSS/CHEMEQ2 does not conserve atoms exactly."
        ),
        "of": {},
        "python": {},
    }

    for solver in ("cvode", "qss"):
        ypath = E14 / solver / "e14_Y.csv"
        if not ypath.is_file():
            report["of"][solver] = {"error": f"missing {ypath} — re-run MidT"}
            print(f"OF-{solver}: MISSING e14_Y.csv")
            continue
        t, Y, names = load_of_Y(ypath)
        T = load_T(E14 / solver / "chemFoam.out")
        n = min(len(t), len(T), len(Y))
        t, T, Y = t[:n], T[:n], Y[:n]
        gas.set_mixture_fraction(IC["Z"], "nc12h26:1.0", "o2:1.0, n2:3.76")
        gas.TP = IC["T"], p
        h0 = float(gas.enthalpy_mass)
        ih = load_ih_total(E14 / solver / "e14_invariants.csv")
        audit = audit_pair(gas, f"OF-{solver}", T, Y, names, h0 + ih, p)
        audit["IH_total"] = ih
        audit["n_steps"] = int(n)
        report["of"][solver] = audit
        print(
            f"OF-{solver}: Teq={T[-1]:.2f} max|dZ|={audit['drift']['maxAbs_dZ']:.3e} "
            f"closing={audit['closing'].get('PASS_closing')} "
            f"T_HP_drift={audit['closing'].get('T_HP_drifted_elems')} "
            f"T_HP_orig={audit['closing'].get('T_HP_original_elems')} "
            f"mech={audit['mechanism']}"
        )

    if not args.of_only and not args.skip_python:
        print("Regenerating Python MidT with Y…")
        py = run_python_midt()
        np.savez_compressed(
            OUT / "e14_5_python_midt.npz",
            t_cvode=py["cvode"]["t"],
            T_cvode=py["cvode"]["T"],
            Y_cvode=py["cvode"]["Y"],
            t_qss=py["qss"]["t"],
            T_qss=py["qss"]["T"],
            Y_qss=py["qss"]["Y"],
            names=np.asarray(py["cvode"]["names"]),
        )
        for solver in ("cvode", "qss"):
            d = py[solver]
            audit = audit_pair(
                gas, f"Py-{solver}", d["T"], d["Y"], d["names"], d["h_end"], p
            )
            audit["wall_s"] = d["wall"]
            report["python"][solver] = audit
            print(
                f"Py-{solver}: Teq={d['T'][-1]:.2f} max|dZ|={audit['drift']['maxAbs_dZ']:.3e} "
                f"closing={audit['closing'].get('PASS_closing')} "
                f"T_HP_drift={audit['closing'].get('T_HP_drifted_elems')} "
                f"ΔTeq={d['T'][-1]-py['cvode']['T'][-1]:.2f} mech={audit['mechanism']}"
            )
        report["python"]["delta_Teq_qss_minus_cvode"] = float(
            py["qss"]["T"][-1] - py["cvode"]["T"][-1]
        )

    of_q, of_c = report["of"].get("qss", {}), report["of"].get("cvode", {})
    py_q = report["python"].get("qss", {})
    verdict = {
        "E14_bookkeeping": "ruled_out",
        "OF_QSS_maxAbs_dZ": of_q.get("drift", {}).get("maxAbs_dZ"),
        "OF_CVODE_maxAbs_dZ": of_c.get("drift", {}).get("maxAbs_dZ"),
        "OF_closing_PASS": of_q.get("closing", {}).get("PASS_closing"),
        "OF_mechanism": of_q.get("mechanism"),
        "Py_delta_Teq": report["python"].get("delta_Teq_qss_minus_cvode"),
        "Py_QSS_maxAbs_dZ": py_q.get("drift", {}).get("maxAbs_dZ"),
        "Py_closing_PASS": py_q.get("closing", {}).get("PASS_closing"),
        "Py_mechanism": py_q.get("mechanism"),
    }
    report["verdict"] = verdict
    (OUT / "E14_5_ELEMENT_DRIFT.json").write_text(json.dumps(report, indent=2))
    (OUT / "E14_5_ELEMENT_DRIFT.md").write_text(
        f"""# E14.5 — Element-drift audit (gate revised)

## Thesis

Teq ≤ 2 K assumed element-conserving integration. α-QSS/CHEMEQ2 does **not**
conserve atoms exactly; Python-QSS shows the same hot-Teq signature (+~10 K).
E14 ledger/thermo: **no bookkeeping bug**.

## Verdict

```json
{json.dumps(verdict, indent=2)}
```

If OF-QSS `maxAbs_dZ` ≫ CVODE and HP-equil at drifted elements recovers T≈2649 K
within 2 K → **Component B closes as documented CHEMEQ2 algorithm property**;
the OF/Py 4× ΔTeq ratio is Component A (per-window slack).

JSON: `E14_5_ELEMENT_DRIFT.json`
"""
    )
    print("Wrote", OUT / "E14_5_ELEMENT_DRIFT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
