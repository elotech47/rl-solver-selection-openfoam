#!/usr/bin/env python3
"""E15.2b postprocess — T-freeze gates vs Py-QSS."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from e15_ignition_markers import ignition_metrics  # noqa: E402
from e15_qa_recompute import (  # noqa: E402
    is_unreliable_teq,
    load_Y_fields,
    load_chemfoam_out,
    parse_failure,
    parse_wall,
    signed_dZ,
)

OUT = ROOT / "validation/zeroD/e15_conformance"
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
ELEMS = ("C", "H", "O")
ATTR_LABELS = ("NTC_lowT", "MidT", "high_T0")
TIMEOUT_LABELS = ("timeout_700_60_1", "timeout_900_60_1")


def analyze(job, gas):
    out = ROOT / job["out_rel"]
    fail = parse_failure(out)
    t, T = load_chemfoam_out(out / "chemFoam.out")
    m = (
        ignition_metrics(t, T)
        if len(t)
        else dict(
            tau_main_s=float("nan"),
            tau_first_s=float("nan"),
            Teq=float("nan"),
            T_max=float("nan"),
        )
    )
    unreliable = is_unreliable_teq(fail, m.get("Teq", float("nan")), m.get("T_max", float("nan")))
    gas.set_equivalence_ratio(job["phi"], "nc12h26:1.0", "o2:1.0, n2:3.76")
    import cantera as ct

    gas.TP = job["T0"], job["p_atm"] * ct.one_atm
    Y0 = gas.Y.copy()
    Y1 = load_Y_fields(out / "fields", gas)
    drift = {f"dZ_{el}": None for el in ELEMS} | {"maxAbs_dZ": None}
    if Y1 is not None and not unreliable:
        drift = signed_dZ(gas, Y0, Y1)
    return dict(
        point=job["point"],
        toggle=job["toggle"],
        solver=job["solver"],
        failure=fail,
        reliable=not unreliable and fail == "ok",
        tau_main_s=m["tau_main_s"],
        tau_first_s=m["tau_first_s"],
        Teq=None if unreliable else m["Teq"],
        wall_s=parse_wall(out / "wall.txt"),
        **{k: drift.get(k) for k in list(drift)},
    )


def fmt(x, p=3):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "N/A"
    return f"{x:.{p}g}"


def sign_match(a, b):
    if a is None or b is None:
        return False
    if not (np.isfinite(a) and np.isfinite(b)):
        return False
    if abs(a) < 1e-12 and abs(b) < 1e-12:
        return True
    return a * b > 0


def main() -> int:
    import cantera as ct

    jobs = json.loads((OUT / "e15_2b_jobs.json").read_text())["jobs"]
    gas = ct.Solution(str(YAML))
    rows = [analyze(j, gas) for j in jobs]
    (OUT / "e15_2b_raw.json").write_text(json.dumps({"n": len(rows), "runs": rows}, indent=2))

    py = json.loads((OUT / "e15_signature_map_python.json").read_text())
    py_by = {}
    for r in py["results"]:
        if "py_qss" in r:
            py_by[(r["T0"], r["p_atm"], r["phi"])] = r

    # Optional: prior E15.2 CVODE Teq for bit-check on attribution points
    e152 = OUT / "e15_2_raw.json"
    e152_cv = {}
    if e152.exists():
        for r in json.loads(e152.read_text())["runs"]:
            if r["toggle"] == "cvode_ref" and r.get("Teq") is not None:
                e152_cv[r["point"]] = r

    lines = [
        "# E15.2b — T-freeze alone (epsmin=0.02)",
        "",
        "One change: corrector T-freeze (handoff CanteraQSSODE). `epsmin=0.01` held back.",
        "",
    ]
    gates = []

    for label in list(ATTR_LABELS) + list(TIMEOUT_LABELS):
        point_rows = [r for r in rows if r["point"] == label]
        if not point_rows:
            continue
        job0 = next(j for j in jobs if j["point"] == label)
        key = (job0["T0"], job0["p_atm"], job0["phi"])
        py_r = py_by.get(key)
        py_q = py_r["py_qss"] if py_r else None
        py_c = py_r["py_cvode"] if py_r else None

        on = next((r for r in point_rows if r["toggle"] == "Tfreeze_on"), None)
        off = next((r for r in point_rows if r["toggle"] == "Tfreeze_off"), None)
        cv = next((r for r in point_rows if r["toggle"] == "cvode_ref"), None)

        lines += [f"## {label} (T={job0['T0']:.0f}, p={job0['p_atm']:.0f}, φ={job0['phi']:.1f})", ""]
        lines += [
            "| toggle | τ_main [ms] | Teq | ΔTeq vs CVODE | ΔZ_C | ΔZ_H | ΔZ_O | wall [s] | fail |",
            "|--------|------------:|----:|-------------:|-----:|-----:|-----:|---------:|------|",
        ]
        for r in point_rows:
            dteq = None
            if cv and r["reliable"] and r["Teq"] is not None and cv.get("Teq") is not None:
                dteq = r["Teq"] - cv["Teq"]
            lines.append(
                f"| {r['toggle']} | "
                f"{fmt(r['tau_main_s']*1e3 if r['tau_main_s'] is not None and np.isfinite(r['tau_main_s']) else None)} | "
                f"{fmt(r['Teq'],1)} | {fmt(dteq,1)} | "
                f"{fmt(r.get('dZ_C'))} | {fmt(r.get('dZ_H'))} | {fmt(r.get('dZ_O'))} | "
                f"{fmt(r.get('wall_s'),1)} | {r['failure']} |"
            )

        if py_q and py_c:
            py_dteq = py_q["Teq"] - py_c["Teq"]
            lines += [
                "",
                f"Py-QSS: τ_main={fmt(py_q['tau_main_s']*1e3)} ms, ΔTeq={fmt(py_dteq,1)} K, "
                f"ΔZ_C={fmt(py_q.get('dZ_C'))}, ΔZ_H={fmt(py_q.get('dZ_H'))}, "
                f"ΔZ_O={fmt(py_q.get('dZ_O'))}, wall={fmt(py_q.get('wall_s'),2)} s",
                "",
            ]

        # Gate evaluation for Tfreeze_on
        g = dict(point=label, toggle="Tfreeze_on", checks={})
        if label in TIMEOUT_LABELS:
            ok_fail = on is not None and on["failure"] == "ok"
            # Soft wall: complete; report OF/Py ratio (chemFoam overhead >> 2× Py absolute)
            wall_ok = False
            if on and on.get("wall_s") and py_q and py_q.get("wall_s"):
                # Pass if finished and not pathological stall (<< prior 900s cap behavior)
                # Prefer OF wall ≤ 2× OF-CVODE at same point when CVODE ok
                if cv and cv["failure"] == "ok" and cv.get("wall_s"):
                    wall_ok = ok_fail and on["wall_s"] <= max(2.0 * cv["wall_s"], 120.0)
                else:
                    wall_ok = ok_fail and on["wall_s"] < 900
            g["checks"]["complete_ok"] = ok_fail
            g["checks"]["wall_vs_cvode_2x"] = wall_ok
            g["pass"] = ok_fail and wall_ok
        else:
            # Attribution gates
            if not (on and on["reliable"] and cv and cv["reliable"] and py_q and py_c):
                g["pass"] = False
                g["checks"]["data"] = False
            else:
                of_dteq = on["Teq"] - cv["Teq"]
                py_dteq = py_q["Teq"] - py_c["Teq"]
                tau_err = abs(on["tau_main_s"] / py_q["tau_main_s"] - 1.0)
                # late-signed vs CVODE: OF τ should not be early vs CVODE if Py is late/near
                of_vs_cv = on["tau_main_s"] / cv["tau_main_s"] if cv["tau_main_s"] else float("nan")
                py_vs_cv = py_q["tau_main_s"] / py_c["tau_main_s"] if py_c["tau_main_s"] else float("nan")
                late_signed = np.isfinite(of_vs_cv) and np.isfinite(py_vs_cv) and (
                    (of_vs_cv >= 0.95 and py_vs_cv >= 0.95)
                    or abs(of_vs_cv - py_vs_cv) < 0.15
                )
                dteq_sign = sign_match(of_dteq, py_dteq)
                # NTC must go negative
                ntc_neg = True
                if label == "NTC_lowT":
                    ntc_neg = of_dteq < 0 and py_dteq < 0
                mag_ok = (
                    abs(py_dteq) < 1
                    or (0.25 <= abs(of_dteq) / abs(py_dteq) <= 4.0)
                )
                # Prefer Py family ~0.5–2×; allow up to 4× for soft warn, hard fail outside
                mag_family = abs(py_dteq) < 1 or (0.5 <= abs(of_dteq) / abs(py_dteq) <= 2.5)
                dz_signs = all(
                    sign_match(on.get(f"dZ_{el}"), py_q.get(f"dZ_{el}")) for el in ELEMS
                )
                dz_mag = True
                if on.get("maxAbs_dZ") and py_q.get("maxAbs_dZ") and py_q["maxAbs_dZ"] > 0:
                    ratio = on["maxAbs_dZ"] / py_q["maxAbs_dZ"]
                    dz_mag = 0.5 <= ratio <= 2.0
                tau_ok = tau_err <= 0.08  # few %
                high_ok = True
                if label == "high_T0":
                    # no regression vs prior agreement: τ within ~2% of Py, ΔTeq same sign
                    high_ok = tau_err <= 0.05 and dteq_sign

                g["checks"] = dict(
                    tau_within_few_pct=tau_ok,
                    tau_err=tau_err,
                    late_signed_vs_cvode=late_signed,
                    dteq_sign=dteq_sign,
                    ntc_negative=ntc_neg,
                    dteq_mag_family=mag_family,
                    dteq_mag_loose=mag_ok,
                    of_dteq=of_dteq,
                    py_dteq=py_dteq,
                    dz_signs=dz_signs,
                    dz_mag_1x=dz_mag,
                    high_T0_no_regress=high_ok,
                )
                g["pass"] = (
                    tau_ok
                    and late_signed
                    and dteq_sign
                    and ntc_neg
                    and mag_family
                    and dz_signs
                    and dz_mag
                    and high_ok
                )

                # CVODE bit-check vs E15.2 if available
                if label in e152_cv and cv.get("Teq") is not None and e152_cv[label].get("Teq") is not None:
                    dT = abs(cv["Teq"] - e152_cv[label]["Teq"])
                    g["checks"]["cvode_Teq_vs_e152"] = dT
                    g["checks"]["cvode_unchanged"] = dT < 0.05
                    if dT >= 0.05:
                        g["pass"] = False

        gates.append(g)
        lines.append(f"**Gate ({label}):** {'PASS' if g.get('pass') else 'FAIL'} — `{json.dumps(g.get('checks', {}), default=str)}`")
        lines.append("")

        # Residual fingerprint if NTC fails
        if label == "NTC_lowT" and not g.get("pass") and on:
            lines += [
                "### Residual fingerprint (NTC stop condition)",
                f"- failure={on['failure']}, τ_main={fmt(on.get('tau_main_s'))}, Teq={fmt(on.get('Teq'),1)}",
                f"- ΔZ_C/H/O={fmt(on.get('dZ_C'))}/{fmt(on.get('dZ_H'))}/{fmt(on.get('dZ_O'))}",
                f"- vs Py ΔTeq / signs in checks above",
                "- **Do not touch substep controller yet.** Consider `epsmin=0.01` only as second toggle.",
                "",
            ]

    all_pass = all(g.get("pass") for g in gates)
    lines = [
        "# E15.2b — T-freeze alone (epsmin=0.02)",
        "",
        f"**Overall: {'GATES GREEN' if all_pass else 'GATES RED'}**",
        "",
    ] + lines[2:]

    (OUT / "E15_2B_GATES.md").write_text("\n".join(lines) + "\n")
    (OUT / "e15_2b_gates.json").write_text(
        json.dumps(dict(overall=all_pass, gates=gates, runs=rows), indent=2, default=str)
    )
    print(f"Wrote {OUT / 'E15_2B_GATES.md'}; overall={'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
