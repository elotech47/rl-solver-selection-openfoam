#!/usr/bin/env python3
"""E15.2c postprocess — Tfreeze + epsmin=0.01 vs Py-QSS (CVODE from e15_2b)."""
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


def analyze_out(out: Path, job_meta: dict, gas):
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
    gas.set_equivalence_ratio(job_meta["phi"], "nc12h26:1.0", "o2:1.0, n2:3.76")
    import cantera as ct

    gas.TP = job_meta["T0"], job_meta["p_atm"] * ct.one_atm
    Y0 = gas.Y.copy()
    Y1 = load_Y_fields(out / "fields", gas)
    drift = {f"dZ_{el}": None for el in ELEMS} | {"maxAbs_dZ": None}
    if Y1 is not None and not unreliable:
        drift = signed_dZ(gas, Y0, Y1)
    return dict(
        point=job_meta["point"],
        failure=fail,
        reliable=not unreliable and fail == "ok",
        tau_main_s=m["tau_main_s"],
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

    jobs = json.loads((OUT / "e15_2c_jobs.json").read_text())["jobs"]
    gas = ct.Solution(str(YAML))

    py = json.loads((OUT / "e15_signature_map_python.json").read_text())
    py_by = {}
    for r in py["results"]:
        if "py_qss" in r:
            py_by[(r["T0"], r["p_atm"], r["phi"])] = r

    lines = [
        "# E15.2c — T-freeze + epsmin=0.01",
        "",
        "Second toggle on top of T-freeze. CVODE and Tfreeze_on(epsmin=0.02) from E15.2b.",
        "",
    ]
    gates = []
    runs = []

    for job in jobs:
        label = job["point"]
        cand = analyze_out(ROOT / job["out_rel"], job, gas)
        cand["toggle"] = job["toggle"]
        cv = analyze_out(ROOT / job["cvode_out_rel"], {**job, "point": label}, gas)
        cv["toggle"] = "cvode_ref"
        prev = analyze_out(ROOT / job["tfreeze_out_rel"], {**job, "point": label}, gas)
        prev["toggle"] = "Tfreeze_on_eps0p02"
        runs.extend([cand, cv, prev])

        key = (job["T0"], job["p_atm"], job["phi"])
        py_r = py_by.get(key)
        py_q = py_r["py_qss"] if py_r else None
        py_c = py_r["py_cvode"] if py_r else None

        lines += [f"## {label} (T={job['T0']:.0f}, p={job['p_atm']:.0f}, φ={job['phi']:.1f})", ""]
        lines += [
            "| toggle | τ_main [ms] | Teq | ΔTeq vs CVODE | ΔZ_C | ΔZ_H | ΔZ_O | wall [s] | fail |",
            "|--------|------------:|----:|-------------:|-----:|-----:|-----:|---------:|------|",
        ]
        for r in (prev, cand, cv):
            dteq = None
            if cv["reliable"] and r["reliable"] and r["Teq"] is not None and cv["Teq"] is not None:
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
                f"ΔZ_O={fmt(py_q.get('dZ_O'))}",
                "",
            ]

        g = dict(point=label, toggle=cand["toggle"], checks={})
        if label in TIMEOUT_LABELS:
            ok_fail = cand["failure"] == "ok"
            wall_ok = False
            if ok_fail and cand.get("wall_s") and cv["failure"] == "ok" and cv.get("wall_s"):
                wall_ok = cand["wall_s"] <= max(2.0 * cv["wall_s"], 120.0)
            g["checks"] = dict(complete_ok=ok_fail, wall_vs_cvode_2x=wall_ok)
            g["pass"] = ok_fail and wall_ok
        else:
            if not (cand["reliable"] and cv["reliable"] and py_q and py_c):
                g["pass"] = False
                g["checks"] = dict(data=False)
            else:
                of_dteq = cand["Teq"] - cv["Teq"]
                py_dteq = py_q["Teq"] - py_c["Teq"]
                tau_err = abs(cand["tau_main_s"] / py_q["tau_main_s"] - 1.0)
                of_vs_cv = cand["tau_main_s"] / cv["tau_main_s"] if cv["tau_main_s"] else float("nan")
                py_vs_cv = py_q["tau_main_s"] / py_c["tau_main_s"] if py_c["tau_main_s"] else float("nan")
                late_signed = np.isfinite(of_vs_cv) and np.isfinite(py_vs_cv) and (
                    (of_vs_cv >= 0.95 and py_vs_cv >= 0.95) or abs(of_vs_cv - py_vs_cv) < 0.15
                )
                dteq_sign = sign_match(of_dteq, py_dteq)
                ntc_neg = True if label != "NTC_lowT" else (of_dteq < 0 and py_dteq < 0)
                mag_family = abs(py_dteq) < 1 or (0.5 <= abs(of_dteq) / abs(py_dteq) <= 2.5)
                dz_signs = all(
                    sign_match(cand.get(f"dZ_{el}"), py_q.get(f"dZ_{el}")) for el in ELEMS
                )
                dz_mag = True
                if cand.get("maxAbs_dZ") and py_q.get("maxAbs_dZ") and py_q["maxAbs_dZ"] > 0:
                    dz_mag = 0.5 <= cand["maxAbs_dZ"] / py_q["maxAbs_dZ"] <= 2.0
                tau_ok = tau_err <= 0.08
                high_ok = True
                if label == "high_T0":
                    high_ok = tau_ok and dteq_sign
                # NTC must not regress vs T-freeze alone
                ntc_hold = True
                if label == "NTC_lowT" and prev["reliable"] and prev["Teq"] is not None:
                    prev_d = prev["Teq"] - cv["Teq"]
                    ntc_hold = of_dteq < 0 and abs(of_dteq - py_dteq) <= abs(prev_d - py_dteq) + 15

                g["checks"] = dict(
                    tau_within_few_pct=tau_ok,
                    tau_err=tau_err,
                    late_signed_vs_cvode=late_signed,
                    dteq_sign=dteq_sign,
                    ntc_negative=ntc_neg,
                    dteq_mag_family=mag_family,
                    of_dteq=of_dteq,
                    py_dteq=py_dteq,
                    dz_signs=dz_signs,
                    dz_mag_1x=dz_mag,
                    high_T0_no_regress=high_ok,
                    ntc_hold_vs_tfreeze=ntc_hold,
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
                    and ntc_hold
                )
        gates.append(g)
        lines.append(
            f"**Gate ({label}):** {'PASS' if g.get('pass') else 'FAIL'} — "
            f"`{json.dumps(g.get('checks', {}), default=str)}`"
        )
        lines.append("")

        if label == "NTC_lowT" and not g.get("pass"):
            lines += [
                "### Residual fingerprint (NTC stop)",
                f"- failure={cand['failure']}, τ={fmt(cand.get('tau_main_s'))}, "
                f"ΔTeq={fmt((cand['Teq']-cv['Teq']) if cand.get('Teq') and cv.get('Teq') else None,1)}",
                f"- ΔZ={fmt(cand.get('dZ_C'))}/{fmt(cand.get('dZ_H'))}/{fmt(cand.get('dZ_O'))}",
                "- Do **not** touch substep controller yet.",
                "",
            ]

    all_pass = all(g.get("pass") for g in gates)
    lines = [
        "# E15.2c — T-freeze + epsmin=0.01",
        "",
        f"**Overall: {'GATES GREEN' if all_pass else 'GATES RED'}**",
        "",
    ] + lines[2:]

    (OUT / "E15_2C_GATES.md").write_text("\n".join(lines) + "\n")
    (OUT / "e15_2c_gates.json").write_text(
        json.dumps(dict(overall=all_pass, gates=gates, runs=runs), indent=2, default=str)
    )
    print(f"Wrote {OUT / 'E15_2C_GATES.md'}; overall={'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
