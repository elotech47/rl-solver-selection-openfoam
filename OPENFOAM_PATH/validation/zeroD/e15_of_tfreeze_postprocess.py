#!/usr/bin/env python3
"""Post-process E15 OF T-freeze QSS map vs reused CVODE + Python + pre-freeze OF-QSS."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import e15_of_postprocess as ofpp  # noqa: E402

OUT = ROOT / "validation/zeroD/e15_conformance"
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"


def fmt(x, prec=3):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    if isinstance(x, str):
        return x
    return f"{x:.{prec}g}"


def as_float_or_none(x):
    """QA maps may store delta_Teq as UNAVAILABLE(...) strings."""
    if x is None:
        return None
    if isinstance(x, str):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def main() -> int:
    import cantera as ct

    tf_jobs = json.loads((OUT / "e15_of_tfreeze_jobs.json").read_text())
    gas = ct.Solution(str(YAML))

    # Analyze new QSS (tfreeze) + reused CVODE
    rows_qs = []
    rows_cv = []
    for j in tf_jobs["jobs"]:
        qs_job = dict(j)
        rows_qs.append(ofpp.analyze_one(qs_job, gas))
        cv_job = dict(j)
        cv_job["solver"] = "cvode"
        cv_job["out_rel"] = j["cvode_out_rel"]
        rows_cv.append(ofpp.analyze_one(cv_job, gas))

    (OUT / "e15_signature_map_of_tfreeze_raw.json").write_text(
        json.dumps(dict(n=len(rows_qs) + len(rows_cv), qss=rows_qs, cvode=rows_cv), indent=2)
    )

    of_pairs = ofpp.pair_condition(rows_cv, rows_qs)
    # Mark unreliable Teq on QSS/CVODE failures (match QA practice for timeouts)
    for r in of_pairs:
        qs_f = r["of_qss"]["failure"]
        cv_f = r["of_cvode"]["failure"]
        if qs_f != "ok" or cv_f != "ok":
            r["delta_Teq"] = float("nan")
            if qs_f != "ok":
                r["delta_Teq_baseline"] = f"UNAVAILABLE(qss_failure={qs_f})"
            else:
                r["delta_Teq_baseline"] = f"UNAVAILABLE(cvode_failure={cv_f})"
        else:
            r["delta_Teq_baseline"] = r["delta_Teq"]

    of_report = dict(
        campaign="E15_signature_map_OF_Tfreeze",
        config=tf_jobs.get("config"),
        markers="tau_main=argmax(dT/dt); tau_first=first qualifying dT/dt peak",
        tend_mult=tf_jobs.get("tend_mult", 2.0),
        wall_cap_s=tf_jobs.get("wall_cap_s", 900),
        n_conditions=len(of_pairs),
        note="QSS=Tfreeze on; CVODE reused from of_runs/",
        results=of_pairs,
    )
    (OUT / "e15_signature_map_of_tfreeze.json").write_text(json.dumps(of_report, indent=2, default=str))

    # Python reference
    py = json.loads((OUT / "e15_signature_map_python.json").read_text())
    py_by = {}
    for r in py["results"]:
        if "py_qss" in r:
            py_by[(r["T0"], r["p_atm"], r["phi"])] = r

    # Pre-freeze OF map (for before/after)
    old = json.loads((OUT / "e15_signature_map_of.json").read_text())
    old_by = {(r["T0"], r["p_atm"], r["phi"]): r for r in old["results"]}

    diffs = []
    before_after = []
    for r in of_pairs:
        key = (r["T0"], r["p_atm"], r["phi"])
        py_r = py_by.get(key)
        old_r = old_by.get(key)
        of_dT = as_float_or_none(r.get("delta_Teq"))
        py_dT = as_float_or_none(py_r.get("delta_Teq") if py_r else None)
        of_dZ = as_float_or_none(r["of_qss"].get("maxAbs_dZ"))
        py_dZ = as_float_or_none(py_r["py_qss"].get("maxAbs_dZ") if py_r else None)
        of_tau = as_float_or_none(r["of_qss"].get("tau_main_s"))
        py_tau = as_float_or_none(py_r["py_qss"].get("tau_main_s") if py_r else None)
        diffs.append(
            dict(
                T0=r["T0"],
                p_atm=r["p_atm"],
                phi=r["phi"],
                delta_tau_main_ratio_OF_over_Py=ofpp.safe_div(of_tau, py_tau),
                delta_Teq_ratio_OF_over_Py=ofpp.safe_div(of_dT, py_dT),
                drift_ratio_OF_over_Py=ofpp.safe_div(of_dZ, py_dZ),
                of_delta_Teq=of_dT if of_dT is not None else r.get("delta_Teq_baseline"),
                py_delta_Teq=py_dT,
                of_maxAbs_dZ=of_dZ,
                py_maxAbs_dZ=py_dZ,
                of_failure=r.get("failure"),
                py_failure=(py_r or {}).get("failure"),
            )
        )
        old_dT = as_float_or_none(old_r.get("delta_Teq") if old_r else None)
        old_tau = as_float_or_none(old_r["of_qss"].get("tau_main_s") if old_r else None)
        old_fail = old_r.get("failure") if old_r else None
        before_after.append(
            dict(
                T0=r["T0"],
                p_atm=r["p_atm"],
                phi=r["phi"],
                old_dTeq=old_dT,
                new_dTeq=of_dT,
                py_dTeq=py_dT,
                old_tau_ms=(old_tau * 1e3) if old_tau is not None else None,
                new_tau_ms=(of_tau * 1e3) if of_tau is not None else None,
                py_tau_ms=(py_tau * 1e3) if py_tau is not None else None,
                old_failure=old_fail,
                new_failure=r.get("failure"),
                dteq_sign_match_py=(
                    of_dT is not None and py_dT is not None and of_dT * py_dT > 0
                ),
            )
        )

    (OUT / "e15_of_vs_py_diffs_tfreeze.json").write_text(
        json.dumps(dict(n=len(diffs), results=diffs), indent=2, default=str)
    )
    (OUT / "e15_of_before_after_tfreeze.json").write_text(
        json.dumps(dict(n=len(before_after), results=before_after), indent=2, default=str)
    )

    # Markdown: OF Tfreeze map
    of_md = [
        "# E15 OF signature map — T-freeze ON (`epsmin=0.02`)",
        "",
        "QSS remapped with corrector T-freeze (handoff CanteraQSSODE). "
        "CVODE baselines reused from pre-freeze `of_runs/` (CVODE path unchanged).",
        "",
        "| T0 | p | φ | τ_main,Q [ms] | Teq,Q | ΔTeq [K] | max\\|dZ\\| Q | wall Q [s] | failure |",
        "|---:|--:|--:|--------------:|------:|---------:|------------:|----------:|---------|",
    ]
    for r in of_pairs:
        qs = r["of_qss"]
        dteq = as_float_or_none(r.get("delta_Teq"))
        tm = as_float_or_none(qs.get("tau_main_s"))
        of_md.append(
            f"| {r['T0']:.0f} | {r['p_atm']:.0f} | {r['phi']:.1f} | "
            f"{fmt(tm * 1e3 if tm is not None else None)} | "
            f"{fmt(as_float_or_none(qs.get('Teq')),1)} | {fmt(dteq,1)} | "
            f"{fmt(as_float_or_none(qs.get('maxAbs_dZ')))} | "
            f"{fmt(as_float_or_none(qs.get('wall_s')),1)} | {r.get('failure') or 'ok'} |"
        )
    (OUT / "E15_SIGNATURE_MAP_OF_TFREEZE.md").write_text("\n".join(of_md) + "\n")

    # Diffs vs Py
    diff_md = [
        "# E15 OF (T-freeze) vs Python difference map",
        "",
        "| T0 | p | φ | Δτ_main OF/Py | ΔTeq OF/Py | drift OF/Py | OF ΔTeq | Py ΔTeq |",
        "|---:|--:|--:|--------------:|-----------:|------------:|--------:|--------:|",
    ]
    for d in diffs:
        of_d = d["of_delta_Teq"]
        of_s = fmt(of_d, 1) if isinstance(of_d, (int, float)) else str(of_d)
        diff_md.append(
            f"| {d['T0']:.0f} | {d['p_atm']:.0f} | {d['phi']:.1f} | "
            f"{fmt(d['delta_tau_main_ratio_OF_over_Py'])} | "
            f"{fmt(d['delta_Teq_ratio_OF_over_Py'])} | "
            f"{fmt(d['drift_ratio_OF_over_Py'])} | "
            f"{of_s} | {fmt(d['py_delta_Teq'],1)} |"
        )
    (OUT / "E15_OF_VS_PY_DIFFS_TFREEZE.md").write_text("\n".join(diff_md) + "\n")

    # Before/after summary
    n_sign_old = sum(
        1
        for b in before_after
        if b["old_dTeq"] is not None
        and b["py_dTeq"] is not None
        and b["old_dTeq"] * b["py_dTeq"] > 0
    )
    n_sign_new = sum(1 for b in before_after if b["dteq_sign_match_py"])
    n_dteq = sum(
        1
        for b in before_after
        if b["py_dTeq"] is not None and b["new_dTeq"] is not None
    )
    n_ok_new = sum(1 for b in before_after if not b["new_failure"] or b["new_failure"] == "ok" or (isinstance(b["new_failure"], str) and "qss=ok" in b["new_failure"] and "cvode=ok" in b["new_failure"].replace(";", " ")))
    # simpler ok count
    n_qss_ok = sum(1 for r in rows_qs if r["failure"] == "ok")
    n_qss_to = sum(1 for r in rows_qs if r["failure"] == "wall_timeout")

    ba_md = [
        "# E15 before/after — OF-QSS freeze OFF → ON",
        "",
        f"- QSS ok: **{n_qss_ok}/38**; wall_timeout: **{n_qss_to}**",
        f"- ΔTeq sign match vs Py (where both finite): freeze-off **{n_sign_old}**, freeze-on **{n_sign_new}** (of {n_dteq} comparable)",
        "",
        "| T0 | p | φ | old ΔTeq | new ΔTeq | Py ΔTeq | old τ [ms] | new τ | Py τ | old fail | new fail |",
        "|---:|--:|--:|---------:|---------:|--------:|-----------:|------:|-----:|----------|----------|",
    ]
    for b in before_after:
        ba_md.append(
            f"| {b['T0']:.0f} | {b['p_atm']:.0f} | {b['phi']:.1f} | "
            f"{fmt(b['old_dTeq'],1)} | {fmt(b['new_dTeq'],1)} | {fmt(b['py_dTeq'],1)} | "
            f"{fmt(b['old_tau_ms'])} | {fmt(b['new_tau_ms'])} | {fmt(b['py_tau_ms'])} | "
            f"{b['old_failure'] or '—'} | {b['new_failure'] or 'ok'} |"
        )
    (OUT / "E15_BEFORE_AFTER_TFREEZE.md").write_text("\n".join(ba_md) + "\n")

    # Drift vs dTeq plot
    try:
        ofpp.plot_drift_vs_dteq(
            of_pairs,
            [r for r in py["results"] if "py_qss" in r],
            OUT / "e15_drift_vs_dTeq_tfreeze.png",
        )
    except Exception as e:  # noqa: BLE001
        print(f"plot skip: {e}")

    print(
        f"Wrote T-freeze map + diffs; QSS ok={n_qss_ok}/38 timeouts={n_qss_to}; "
        f"ΔTeq sign match Py: {n_sign_old}→{n_sign_new}"
    )
    print(f"  {OUT / 'E15_SIGNATURE_MAP_OF_TFREEZE.md'}")
    print(f"  {OUT / 'E15_OF_VS_PY_DIFFS_TFREEZE.md'}")
    print(f"  {OUT / 'E15_BEFORE_AFTER_TFREEZE.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
