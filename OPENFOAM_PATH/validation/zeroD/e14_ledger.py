#!/usr/bin/env python3
"""E14.2 — Post-process e14_invariants.csv MidT ledgers (qss + cvode).

Decision table (Campaign 4):
  1. ΔY_applied vs ΔY_RR inconsistent → RR/YEqn bookkeeping bug
  2. dIntegratedHeat vs −Σ Hc·ΔY_RR inconsistent → Qdot/Hc path bug
  3. −Σ Hc·ΔY_int (ODE stash) vs −Σ Hc·ΔY_RR diverge with nSub>1 → subcycle
  4. All consistent but Teq(QSS)−Teq(CVODE) still ≫2 K → escalate / E14.3
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "validation/zeroD/e14_ledger"


def load_csv(path: Path) -> dict:
    rows = []
    with path.open() as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.strip().split(",")
            # last two fields may be species names
            if len(parts) < 18:
                continue
            rows.append(
                dict(
                    t=float(parts[0]),
                    dt=float(parts[1]),
                    rho=float(parts[2]),
                    T_cell=float(parts[3]),
                    T0_ode=float(parts[4]),
                    T_int=float(parts[5]),
                    T_newton=float(parts[6]),
                    nSub=int(float(parts[7])),
                    sumRR=float(parts[8]),
                    Qdot=float(parts[9]),
                    dIH=float(parts[10]),
                    negHc_RR=float(parts[11]),
                    negHc_app=float(parts[12]),
                    negHc_int=float(parts[13]),
                    max_dY_RR=float(parts[14]),
                    max_dY_RR_name=parts[15],
                    max_dY_diff=float(parts[16]),
                    max_dY_diff_name=parts[17],
                )
            )
    if not rows:
        raise SystemExit(f"No data rows in {path}")
    return {k: np.array([r[k] for r in rows]) for k in rows[0]}


def summarize(tag: str, d: dict) -> dict:
    # Round-off relative to CVODE control: use abs tolerances on mass fractions
    max_dy_diff = float(np.max(d["max_dY_diff"]))
    # Heat ledger: dIH should match negHc_RR by construction
    heat_resid = d["dIH"] - d["negHc_RR"]
    max_heat_resid = float(np.max(np.abs(heat_resid)))
    # Applied vs RR Hc
    app_resid = d["negHc_app"] - d["negHc_RR"]
    max_app_resid = float(np.max(np.abs(app_resid)))
    # Integrator stash vs RR (first-substep only approximation when nSub>1)
    int_resid = d["negHc_int"] - d["negHc_RR"]
    mask_n1 = d["nSub"] <= 1
    max_int_resid_n1 = (
        float(np.max(np.abs(int_resid[mask_n1]))) if mask_n1.any() else float("nan")
    )
    T_end = float(d["T_cell"][-1])
    T_int_end = float(d["T_int"][-1])
    T_newton_end = float(d["T_newton"][-1])
    return dict(
        tag=tag,
        n_steps=int(len(d["t"])),
        T_end=T_end,
        T_int_end=T_int_end,
        T_newton_end=T_newton_end,
        max_abs_dY_diff=max_dy_diff,
        max_abs_heat_resid_dIH_vs_negHcRR=max_heat_resid,
        max_abs_negHc_app_vs_RR=max_app_resid,
        max_abs_negHc_int_vs_RR_nSub1=max_int_resid_n1,
        frac_nSub_gt1=float(np.mean(d["nSub"] > 1)),
        integratedHeat_total=float(np.sum(d["dIH"])),
        PASS_dY=(max_dy_diff < 1e-12),
        PASS_heat=(max_heat_resid < 1e-6),  # J/kg per step
        PASS_app=(max_app_resid < 1e-6),
    )


def end_ledger_vs_Y(case_out: Path, tag: str) -> dict:
    """integratedHeat_total vs −Σ Hc_i (Y_end − Y_0) if Y dumps exist."""
    # Optional: chemFoam doesn't dump full Y trajectory by default.
    return {}


def branch(qss: dict, cvode: dict) -> dict:
    teq = qss["T_end"] - cvode["T_end"]
    rows = [
        {
            "row": 1,
            "test": "ΔY_applied vs ΔY_RR",
            "qss_pass": qss["PASS_dY"],
            "cvode_pass": cvode["PASS_dY"],
            "action_if_fail": "RR/YEqn bookkeeping",
        },
        {
            "row": 2,
            "test": "dIH vs −Σ Hc·ΔY_RR",
            "qss_pass": qss["PASS_heat"],
            "cvode_pass": cvode["PASS_heat"],
            "action_if_fail": "Qdot/Hc path",
        },
        {
            "row": 3,
            "test": "−Σ Hc·ΔY_app vs RR",
            "qss_pass": qss["PASS_app"],
            "cvode_pass": cvode["PASS_app"],
            "action_if_fail": "YEqn vs RR inconsistency",
        },
        {
            "row": 4,
            "test": "Teq(QSS)−Teq(CVODE) ≤ 2 K",
            "qss_pass": abs(teq) <= 2.0,
            "cvode_pass": True,
            "teq_K": teq,
            "action_if_fail": "escalate if 1–3 green; else E14.3 thermo-range",
        },
    ]
    fix_scope = None
    if not (qss["PASS_dY"] and cvode["PASS_dY"]):
        fix_scope = "RR/Δt/ρ/YEqn bookkeeping"
    elif not (qss["PASS_heat"] and cvode["PASS_heat"]):
        fix_scope = "Qdot/Hc energy accounting"
    elif not (qss["PASS_app"] and cvode["PASS_app"]):
        fix_scope = "ΔY_applied vs RR"
    elif abs(teq) > 2.0:
        fix_scope = "escalate_or_E14.3_thermo_range"
    else:
        fix_scope = "E14 green"
    return dict(teq_K=teq, rows=rows, fix_scope=fix_scope)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base",
        type=Path,
        default=ROOT / "validation/zeroD/e14_midt",
    )
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    summaries = {}
    for tag in ("cvode", "qss"):
        csv = args.base / tag / "e14_invariants.csv"
        if not csv.is_file():
            print(f"MISSING {csv}")
            continue
        d = load_csv(csv)
        s = summarize(tag, d)
        summaries[tag] = s
        print(
            f"{tag}: Tend={s['T_end']:.2f}  max|dYdiff|={s['max_abs_dY_diff']:.3e}  "
            f"heatResid={s['max_abs_heat_resid_dIH_vs_negHcRR']:.3e}  "
            f"PASS_dY={s['PASS_dY']} PASS_heat={s['PASS_heat']}"
        )

    report = dict(campaign="E14.2", summaries=summaries)
    if "qss" in summaries and "cvode" in summaries:
        report["branch"] = branch(summaries["qss"], summaries["cvode"])
        print("fix_scope:", report["branch"]["fix_scope"])
        print(f"Teq(QSS)-Teq(CVODE) = {report['branch']['teq_K']:.2f} K")

    out = OUT / "e14_2_ledger.json"
    out.write_text(json.dumps(report, indent=2))
    print("Wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
