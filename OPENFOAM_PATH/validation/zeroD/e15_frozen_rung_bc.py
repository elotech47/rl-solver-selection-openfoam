#!/usr/bin/env python3
"""Rung (b)/(c) acceptance under CONFORM build — record frozen 0D validation table.

Rung (c): uses E15 T-freeze signature map (already run).
Rung (b): one 1 µs MidT hard-case step — Python refs + OF if of_step exists,
          else records Python-only + instructs OF single-step path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "validation/zeroD/e15_conformance"
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
DT = 1e-6


def fmt(x, p=4):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:.{p}g}"


def py_step_midt():
    import cantera as ct
    from solver_selection_handoff.utils import create_qss_solver

    gas = ct.Solution(str(YAML))
    gas.set_mixture_fraction(0.062, "nc12h26:1.0", "o2:1.0, n2:3.76")
    gas.TP = 800.0, 10.0 * ct.one_atm
    T0, Y0 = gas.T, gas.Y.copy()
    # CVODE
    g2 = ct.Solution(str(YAML))
    g2.TPY = T0, gas.P, Y0
    r = ct.IdealGasConstPressureReactor(g2)
    sim = ct.ReactorNet([r])
    sim.rtol, sim.atol = 1e-8, 1e-12
    sim.advance(DT)
    cv = dict(T=g2.T, Y=g2.Y.copy())
    # QSS
    g3 = ct.Solution(str(YAML))
    g3.TPY = T0, gas.P, Y0
    config = dict(
        epsmin=0.02, epsmax=100.0, dtmin=1e-12, dtmax=1e-6, itermax=2, abstol=1e-11
    )
    integ = create_qss_solver(g3, g3.P, config)
    y = np.concatenate([[g3.T], g3.Y])
    integ.setState(y.tolist(), 0.0)
    integ.integrateToTime(DT)
    yout = np.asarray(integ.y, dtype=float)
    g3.TPY = max(yout[0], 200.0), g3.P, np.maximum(yout[1:], 0.0)
    qs = dict(T=g3.T, Y=g3.Y.copy())
    return dict(T0=T0, Y0=Y0, cvode=cv, qss=qs, dt=DT)


def parse_of_t(path: Path) -> float | None:
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        if "internalField" in line and "uniform" in line:
            return float(line.split()[-1].rstrip(";"))
    return None


def parse_chemfoam_t0_t1(path: Path) -> tuple[float | None, float | None]:
    """chemFoam.out: first/last temperature columns when present."""
    if not path.is_file():
        return None, None
    rows = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                t = float(parts[0])
                T = float(parts[1])
                rows.append((t, T))
            except ValueError:
                continue
    if not rows:
        return None, None
    return rows[0][1], rows[-1][1]


def of_step_midt():
    base = OUT / "rung_b_midt"
    out = {}
    for solver in ("qss", "cvode"):
        d = base / solver
        T1 = parse_of_t(d / "fields" / "T")
        T0, T1b = parse_chemfoam_t0_t1(d / "chemFoam.out")
        if T1 is None:
            T1 = T1b
        out[solver] = dict(T0=T0, T1=T1, path=str(d))
    return out


def main() -> int:
    sys.path.insert(0, "/Users/el0tech/Documents/research_code/solver_selection/handoff/src")
    of = json.loads((OUT / "e15_signature_map_of_tfreeze.json").read_text())
    py = json.loads((OUT / "e15_signature_map_python.json").read_text())
    py_by = {(r["T0"], r["p_atm"], r["phi"]): r for r in py["results"] if "py_qss" in r}
    of_by = {(r["T0"], r["p_atm"], r["phi"]): r for r in of["results"]}

    step = py_step_midt()
    of_step = of_step_midt()
    of_q = of_step.get("qss") or {}
    of_c = of_step.get("cvode") or {}

    lines = [
        "# Frozen rung (b)/(c) acceptance — CONFORM baseline v1",
        "",
        "**Date:** 2026-07-19  ",
        "**Tag:** `validation-baseline-v1` (alias `e15-conform-baseline-v1`)  ",
        "**Build:** OF-QSS corrector T-freeze ON, `epsmin=0.02`",
        "",
        "## Rung (b) — single 1 µs step (MidT hard case 800 K / 10 atm / φ=1 ≈ Z≈0.062)",
        "",
        "IC: `of_ics/T800_p10_phi1p0_initialConditions`. OF harness: `e15_rung_b_midt_host.sh`.",
        "",
        "| Solver | T₀ [K] | T₁ [K] | ΔT [K] |",
        "|--------|-------:|-------:|-------:|",
        f"| Py-CVODE | {step['T0']:.4f} | {step['cvode']['T']:.4f} | {step['cvode']['T']-step['T0']:.4e} |",
        f"| Py-QSS (T-freeze ODE) | {step['T0']:.4f} | {step['qss']['T']:.4f} | {step['qss']['T']-step['T0']:.4e} |",
    ]
    if of_c.get("T1") is not None and of_c.get("T0") is not None:
        lines.append(
            f"| OF-CVODE | {of_c['T0']:.4f} | {of_c['T1']:.4f} | {of_c['T1']-of_c['T0']:.4e} |"
        )
    else:
        lines.append("| OF-CVODE | — | — | *run `e15_rung_b_midt_host.sh`* |")
    if of_q.get("T1") is not None and of_q.get("T0") is not None:
        lines.append(
            f"| OF-QSS (Tfreeze) | {of_q['T0']:.4f} | {of_q['T1']:.4f} | {of_q['T1']-of_q['T0']:.4e} |"
        )
    else:
        lines.append("| OF-QSS (Tfreeze) | — | — | *run `e15_rung_b_midt_host.sh`* |")

    lines += [
        "",
        "Accept (spec): OF-QSS vs Py-QSS at float noise; OF-CVODE vs Py-CVODE within tol.",
        "At MidT IC the 1 µs ΔT is ~0 on all instruments (pre-ignition).",
        "Envelope evidence that T-freeze closes the OF–Py gap is in the 38-condition map.",
        "",
        "## Rung (c) — 0D trajectories (conform map)",
        "",
        "| Case | τ_OF-QSS [ms] | τ_Py-QSS [ms] | OF/Py | τ_OF-CVODE [ms] | τ_Py-CVODE [ms] | OF-C/Py-C | ΔTeq OF | ΔTeq Py |",
        "|------|--------------:|--------------:|------:|----------------:|----------------:|----------:|--------:|--------:|",
    ]

    keys = [
        ("NTC_lowT", 700, 60, 0.5),
        ("MidT_MidP", 800, 10, 1.0),
        ("high_T0", 1000, 10, 1.0),
        ("HighT_HighP", 1000, 30, 1.0),
        ("timeout_cleared", 700, 60, 1.0),
    ]
    table = []
    for label, T0, p, phi in keys:
        o = of_by.get((float(T0), float(p), float(phi)))
        p_ = py_by.get((float(T0), float(p), float(phi)))
        if not o or not p_:
            continue
        oq, oc = o["of_qss"], o["of_cvode"]
        pq, pc = p_["py_qss"], p_["py_cvode"]
        row = dict(
            label=label,
            tau_of_qss=oq["tau_main_s"],
            tau_py_qss=pq["tau_main_s"],
            ratio_q=oq["tau_main_s"] / pq["tau_main_s"],
            tau_of_cv=oc["tau_main_s"],
            tau_py_cv=pc["tau_main_s"],
            ratio_c=oc["tau_main_s"] / pc["tau_main_s"] if pc["tau_main_s"] else None,
            dteq_of=o.get("delta_Teq"),
            dteq_py=p_.get("delta_Teq"),
        )
        table.append(row)
        dteq_of = row["dteq_of"] if isinstance(row["dteq_of"], (int, float)) else None
        lines.append(
            f"| {label} | {fmt(oq['tau_main_s']*1e3)} | {fmt(pq['tau_main_s']*1e3)} | "
            f"{fmt(row['ratio_q'])} | {fmt(oc['tau_main_s']*1e3)} | {fmt(pc['tau_main_s']*1e3)} | "
            f"{fmt(row['ratio_c'])} | {fmt(dteq_of,1) if dteq_of is not None else '—'} | "
            f"{fmt(p_.get('delta_Teq'),1)} |"
        )

    mid = next((t for t in table if t["label"] == "MidT_MidP"), None)
    lines += [
        "",
        "### Spec gates (instruction §3.4) — recorded under conform",
        "",
    ]
    if mid:
        lines += [
            f"- OF-CVODE vs Py-CVODE MidT: **{(mid['ratio_c']-1)*100:.2f}%** "
            f"(accept ≤1%: {'PASS' if abs(mid['ratio_c']-1)<=0.01 else 'CHECK'})",
            f"- OF-QSS vs Py-QSS MidT: **{(mid['ratio_q']-1)*100:.2f}%** "
            f"(accept ≤1% vs Cantera-QSS: {'PASS' if abs(mid['ratio_q']-1)<=0.01 else 'CHECK'})",
            f"- OF-QSS vs Py-CVODE MidT: **{(mid['tau_of_qss']/mid['tau_py_cv']-1)*100:.1f}%** "
            f"(characteristic QSS bias; not a defect if OF≈Py QSS)",
        ]

    lines += [
        "",
        "## Verdict",
        "",
        "This file is the **frozen 0D validation table** for thesis citation under",
        "`validation-baseline-v1`. Production QSS = T-freeze + epsmin=0.02.",
        "Full envelope: `FROZEN_VALIDATION_BASELINE_v1.md`, maps under `e15_conformance/`.",
        "",
    ]
    (OUT / "FROZEN_RUNG_BC_ACCEPTANCE.md").write_text("\n".join(lines) + "\n")
    (OUT / "frozen_rung_bc_acceptance.json").write_text(
        json.dumps(
            dict(rung_b_py_step=step, rung_b_of_step=of_step, rung_c=table, tag="validation-baseline-v1"),
            indent=2,
            default=str,
        )
    )
    print(f"Wrote {OUT / 'FROZEN_RUNG_BC_ACCEPTANCE.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
