#!/usr/bin/env python3
"""E15 signature map — Py-CVODE / Py-QSS with T0-robust ignition markers.

Per condition (presize RUN set):
  endTime = 2.0 × Cantera-presized main τ
  τ_main  = global max dT/dt
  τ_first = first qualifying dT/dt peak
  Teq, ΔTeq vs same-framework CVODE, max|ΔZ|, wall, steps, failure mode
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent / "handoff" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from e15_ignition_markers import ignition_metrics  # noqa: E402

YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
OUT = ROOT / "validation/zeroD/e15_conformance"
PRE = OUT / "e15_presize.json"
ELEMS = ("C", "H", "O", "N")
TEND_MULT = 2.0
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


def stub_sundials():
    if "SundialsPy" not in sys.modules:
        sp = types.ModuleType("SundialsPy")
        sp.cvode = types.ModuleType("SundialsPy.cvode")
        sys.modules["SundialsPy"] = sp
        sys.modules["SundialsPy.cvode"] = sp.cvode


def elemental_Z(gas, Y):
    W = gas.molecular_weights
    out = {}
    for el in ELEMS:
        Wi = gas.atomic_weight(el)
        z = 0.0
        for i in range(gas.n_species):
            n = gas.n_atoms(i, el)
            if n:
                z += Y[i] * (n * Wi / W[i])
        out[el] = float(z)
    return out


def signed_dZ(gas, Y0, Y):
    z0 = elemental_Z(gas, Y0)
    z1 = elemental_Z(gas, Y)
    d = {f"dZ_{el}": z1[el] - z0[el] for el in ELEMS}
    d["maxAbs_dZ"] = float(max(abs(d[f"dZ_{el}"]) for el in ELEMS))
    return d


def max_abs_dZ(gas, Y0, Y):
    return signed_dZ(gas, Y0, Y)["maxAbs_dZ"]


def run_cvode(gas, T0, P, phi, t_end, dt=1e-6):
    import cantera as ct

    gas.set_equivalence_ratio(phi, "nc12h26:1.0", "o2:1.0, n2:3.76")
    gas.TP = T0, P
    Y0 = gas.Y.copy()
    r = ct.IdealGasConstPressureReactor(gas)
    sim = ct.ReactorNet([r])
    sim.rtol, sim.atol = 1e-8, 1e-12
    t_h, T_h = [0.0], [float(gas.T)]
    dZ = {f"dZ_{el}": 0.0 for el in ELEMS}
    dZ_max = 0.0
    n = 0
    fail = None
    t0 = time.perf_counter()
    try:
        while sim.time < t_end:
            sim.advance(min(sim.time + dt, t_end))
            t_h.append(sim.time)
            T_h.append(float(gas.T))
            n += 1
            if n % 50 == 0:
                s = signed_dZ(gas, Y0, gas.Y)
                for el in ELEMS:
                    if abs(s[f"dZ_{el}"]) >= abs(dZ[f"dZ_{el}"]):
                        dZ[f"dZ_{el}"] = s[f"dZ_{el}"]
                dZ_max = max(dZ_max, s["maxAbs_dZ"])
        s = signed_dZ(gas, Y0, gas.Y)
        for el in ELEMS:
            dZ[f"dZ_{el}"] = s[f"dZ_{el}"]
        dZ_max = s["maxAbs_dZ"]
    except Exception as exc:  # noqa: BLE001
        fail = f"exception:{type(exc).__name__}"
        s = signed_dZ(gas, Y0, gas.Y)
        dZ = {k: s[k] for k in dZ}
        dZ_max = s["maxAbs_dZ"]
    wall = time.perf_counter() - t0
    m = ignition_metrics(t_h, T_h)
    if fail is None and not np.isfinite(m["tau_main_s"]):
        fail = "no_ignition"
    return dict(
        tau_main_s=m["tau_main_s"],
        tau_first_s=m["tau_first_s"],
        Teq=m["Teq"],
        T_max=m["T_max"],
        maxAbs_dZ=dZ_max,
        dZ_C=dZ["dZ_C"],
        dZ_H=dZ["dZ_H"],
        dZ_O=dZ["dZ_O"],
        dZ_N=dZ["dZ_N"],
        wall_s=wall,
        n_steps=max(0, len(t_h) - 1),
        failure=fail,
        status="ok" if fail is None else fail,
    )


def run_qss(gas, T0, P, phi, t_end, dt=1e-6):
    stub_sundials()
    from solver_selection_handoff.utils import create_qss_solver

    gas.set_equivalence_ratio(phi, "nc12h26:1.0", "o2:1.0, n2:3.76")
    gas.TP = T0, P
    Y0 = gas.Y.copy()
    cfg = dict(
        epsmin=0.02, epsmax=100.0, dtmin=1e-12, dtmax=1e-6, itermax=2, abstol=1e-11
    )
    integ = create_qss_solver(gas, gas.P, cfg)
    t = 0.0
    t_h, T_h = [0.0], [float(gas.T)]
    dZ = {f"dZ_{el}": 0.0 for el in ELEMS}
    dZ_max = 0.0
    n = 0
    fail = None
    t0 = time.perf_counter()
    try:
        while t < t_end:
            dti = min(dt, t_end - t)
            y = np.concatenate([[gas.T], gas.Y])
            integ.setState(y.tolist(), 0.0)
            integ.integrateToTime(dti)
            yout = np.asarray(integ.y, dtype=float)
            gas.TPY = max(yout[0], 200.0), gas.P, np.maximum(yout[1:], 0.0)
            ssum = gas.Y.sum()
            if ssum > 0:
                gas.TPY = gas.T, gas.P, gas.Y / ssum
            t += dti
            t_h.append(t)
            T_h.append(float(gas.T))
            n += 1
            if n % 50 == 0:
                s = signed_dZ(gas, Y0, gas.Y)
                for el in ELEMS:
                    if abs(s[f"dZ_{el}"]) >= abs(dZ[f"dZ_{el}"]):
                        dZ[f"dZ_{el}"] = s[f"dZ_{el}"]
                dZ_max = max(dZ_max, s["maxAbs_dZ"])
        s = signed_dZ(gas, Y0, gas.Y)
        for el in ELEMS:
            dZ[f"dZ_{el}"] = s[f"dZ_{el}"]
        dZ_max = s["maxAbs_dZ"]
    except Exception as exc:  # noqa: BLE001
        fail = f"exception:{type(exc).__name__}"
        s = signed_dZ(gas, Y0, gas.Y)
        dZ = {k: s[k] for k in dZ}
        dZ_max = s["maxAbs_dZ"]
    wall = time.perf_counter() - t0
    m = ignition_metrics(t_h, T_h)
    if fail is None and not np.isfinite(m["tau_main_s"]):
        fail = "no_ignition"
    return dict(
        tau_main_s=m["tau_main_s"],
        tau_first_s=m["tau_first_s"],
        Teq=m["Teq"],
        T_max=m["T_max"],
        maxAbs_dZ=dZ_max,
        dZ_C=dZ["dZ_C"],
        dZ_H=dZ["dZ_H"],
        dZ_O=dZ["dZ_O"],
        dZ_N=dZ["dZ_N"],
        wall_s=wall,
        n_steps=max(0, len(t_h) - 1),
        failure=fail,
        status="ok" if fail is None else fail,
    )



def main() -> int:
    import cantera as ct

    pre = json.loads(PRE.read_text())
    gas = ct.Solution(str(YAML))
    results = []
    for row in pre["rows"]:
        if row["skip"]:
            results.append(
                {
                    **{
                        k: row[k]
                        for k in ("T0", "p_atm", "phi", "Z", "tau_s", "skip_reason")
                    },
                    "status": "skipped_presize",
                    "failure": row.get("skip_reason") or "skipped_presize",
                }
            )
            continue
        T0, p_atm, phi = row["T0"], row["p_atm"], row["phi"]
        P = p_atm * ct.one_atm
        tau_ct = float(row["tau_s"])
        t_end = TEND_MULT * tau_ct
        print(
            f"RUN T={T0:.0f} p={p_atm:.0f} φ={phi:.1f} "
            f"t_end={t_end*1e3:.2f} ms (2×τ={tau_ct*1e3:.2f})",
            flush=True,
        )
        try:
            cv = run_cvode(gas, T0, P, phi, t_end)
        except BaseException as exc:  # noqa: BLE001
            cv = dict(
                tau_main_s=float("nan"),
                tau_first_s=float("nan"),
                Teq=float("nan"),
                T_max=float("nan"),
                maxAbs_dZ=float("nan"),
                wall_s=float("nan"),
                n_steps=0,
                failure=f"crash:{type(exc).__name__}:{exc}",
                status="crash",
            )
        try:
            qs = run_qss(gas, T0, P, phi, t_end)
        except BaseException as exc:  # noqa: BLE001
            qs = dict(
                tau_main_s=float("nan"),
                tau_first_s=float("nan"),
                Teq=float("nan"),
                T_max=float("nan"),
                maxAbs_dZ=float("nan"),
                wall_s=float("nan"),
                n_steps=0,
                failure=f"crash:{type(exc).__name__}:{exc}",
                status="crash",
            )
        dTeq = (
            qs["Teq"] - cv["Teq"]
            if np.isfinite(qs["Teq"]) and np.isfinite(cv["Teq"])
            else float("nan")
        )
        tau_ratio = None
        if (
            cv["tau_main_s"]
            and qs["tau_main_s"]
            and np.isfinite(cv["tau_main_s"])
            and np.isfinite(qs["tau_main_s"])
            and cv["tau_main_s"] > 0
        ):
            tau_ratio = qs["tau_main_s"] / cv["tau_main_s"]
        fail = None
        if cv["failure"] or qs["failure"]:
            fail = f"cvode={cv['failure']};qss={qs['failure']}"
        results.append(
            dict(
                T0=T0,
                p_atm=p_atm,
                phi=phi,
                Z=row["Z"],
                tau_cantera_s=tau_ct,
                t_end_s=t_end,
                tend_mult=TEND_MULT,
                status="ok" if fail is None else "partial_fail",
                failure=fail,
                py_cvode=cv,
                py_qss=qs,
                delta_Teq=dTeq,
                tau_ratio_qss_over_cvode=tau_ratio,
                drift_ratio_qss_over_cvode=(
                    qs["maxAbs_dZ"] / cv["maxAbs_dZ"]
                    if cv["maxAbs_dZ"] and cv["maxAbs_dZ"] > 0
                    else None
                ),
                wall_ratio_cvode_over_qss=(
                    cv["wall_s"] / qs["wall_s"] if qs["wall_s"] > 0 else None
                ),
            )
        )
        print(
            f"  ΔTeq={dTeq:+.1f} K  τ_main Q/C={tau_ratio}  "
            f"dZ_qss={qs['maxAbs_dZ']:.2e} dZ_cv={cv['maxAbs_dZ']:.2e}  "
            f"τ_first qss={qs['tau_first_s']}",
            flush=True,
        )
        # Incremental checkpoint (survive hard aborts)
        report = dict(
            campaign="E15_signature_map_python",
            markers="tau_main=argmax(dT/dt); tau_first=first qualifying dT/dt peak",
            tend_mult=TEND_MULT,
            n=len(results),
            results=results,
            partial=True,
        )
        (OUT / "e15_signature_map_python.json").write_text(json.dumps(report, indent=2))

    report = dict(
        campaign="E15_signature_map_python",
        markers="tau_main=argmax(dT/dt); tau_first=first qualifying dT/dt peak",
        tend_mult=TEND_MULT,
        n=len(results),
        results=results,
        partial=False,
    )
    (OUT / "e15_signature_map_python.json").write_text(json.dumps(report, indent=2))
    print(f"  checkpoint n={len(results)}", flush=True)

    # final markdown after all rows
    lines = [
        "# E15 Python signature map",
        "",
        "Markers: **τ_main** = global max dT/dt; **τ_first** = first qualifying dT/dt peak.",
        f"endTime = {TEND_MULT}× Cantera-presized main τ.",
        "",
        "| T0 | p [atm] | φ | τ_main,Q [ms] | τ_first,Q [ms] | ΔTeq [K] | τ_Q/τ_C | max\\|dZ\\| QSS | failure |",
        "|---:|--------:|--:|--------------:|---------------:|---------:|--------:|-------------:|---------|",
    ]
    for r in results:
        if r.get("status") == "skipped_presize":
            continue
        if "py_qss" not in r:
            continue
        qs = r["py_qss"]
        tr = r.get("tau_ratio_qss_over_cvode")
        tf = qs["tau_first_s"]
        tf_ms = tf * 1e3 if np.isfinite(tf) else float("nan")
        tr_s = f"{tr:.3f}" if tr else "—"
        lines.append(
            f"| {r['T0']:.0f} | {r['p_atm']:.0f} | {r['phi']:.1f} | "
            f"{qs['tau_main_s']*1e3:.3f} | {tf_ms:.3f} | "
            f"{r['delta_Teq']:+.1f} | {tr_s} | "
            f"{qs['maxAbs_dZ']:.2e} | {r.get('failure') or '—'} |"
        )
    (OUT / "E15_SIGNATURE_MAP_PYTHON.md").write_text("\n".join(lines) + "\n")
    print("Wrote", OUT / "E15_SIGNATURE_MAP_PYTHON.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
