#!/usr/bin/env python3
"""E15.2 postprocess → attribution table + conform-config candidate."""
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
    y0_from_json,
)

OUT = ROOT / "validation/zeroD/e15_conformance"
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
ELEMS = ("C", "H", "O")


def analyze(job, gas):
    out = ROOT / job["out_rel"]
    fail = parse_failure(out)
    t, T = load_chemfoam_out(out / "chemFoam.out")
    m = ignition_metrics(t, T) if len(t) else dict(
        tau_main_s=float("nan"), tau_first_s=float("nan"), Teq=float("nan"), T_max=float("nan")
    )
    unreliable = is_unreliable_teq(fail, m.get("Teq", float("nan")), m.get("T_max", float("nan")))
    # Y0 from IC via cantera at point
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


def main() -> int:
    import cantera as ct

    jobs = json.loads((OUT / "e15_2_jobs.json").read_text())["jobs"]
    gas = ct.Solution(str(YAML))
    rows = [analyze(j, gas) for j in jobs]
    (OUT / "e15_2_raw.json").write_text(json.dumps({"n": len(rows), "runs": rows}, indent=2))

    # Py reference from signature map
    py = json.loads((OUT / "e15_signature_map_python.json").read_text())
    py_by = {}
    for r in py["results"]:
        if "py_qss" in r:
            py_by[(r["T0"], r["p_atm"], r["phi"])] = r

    attr = json.loads((OUT / "e15_2_attribution_points.json").read_text())["points"]
    table = []
    conform_scores = {t["name"]: [] for t in json.loads((OUT / "e15_2_jobs.json").read_text())["toggles"]}

    lines = [
        "# E15.2 Attribution table",
        "",
        "Per-knob full-trajectory toggles at NTC_lowT → MidT → high_T0.",
        "Success (conform): OF-QSS matches Py-QSS τ (few %), ΔTeq sign+magnitude family, "
        "drift ~1×; optionally clears QSS timeouts.",
        "",
    ]

    for p in attr:
        key = (p["T0"], p["p_atm"], p["phi"])
        pref = f"{p['label']}_T{p['T0']:.0f}_p{p['p_atm']:.0f}_phi{p['phi']:.1f}".replace(".", "p")
        point_rows = [r for r in rows if r["point"] == p["label"]]
        base = next((r for r in point_rows if r["toggle"] == "baseline" and r["reliable"]), None)
        cv = next((r for r in point_rows if r["toggle"] == "cvode_ref" and r["reliable"]), None)
        py_r = py_by.get(key)
        py_q = py_r["py_qss"] if py_r else None
        py_c = py_r["py_cvode"] if py_r else None

        lines += [f"## {p['label']} (T={p['T0']:.0f}, p={p['p_atm']:.0f}, φ={p['phi']:.1f})", ""]
        lines += [
            "| toggle | τ_main [ms] | Δτ vs base | Teq | ΔTeq vs CVODE | ΔZ_C | ΔZ_H | ΔZ_O | wall [s] | fail |",
            "|--------|------------:|-----------:|----:|-------------:|-----:|-----:|-----:|---------:|------|",
        ]
        for r in point_rows:
            dtau = None
            if base and r["reliable"] and np.isfinite(r["tau_main_s"]) and np.isfinite(base["tau_main_s"]):
                dtau = (r["tau_main_s"] - base["tau_main_s"]) / base["tau_main_s"]
            dteq = None
            if cv and r["reliable"] and r["Teq"] is not None and cv["Teq"] is not None:
                dteq = r["Teq"] - cv["Teq"]
            lines.append(
                f"| {r['toggle']} | "
                f"{fmt(r['tau_main_s']*1e3 if r['tau_main_s'] and np.isfinite(r['tau_main_s']) else None)} | "
                f"{fmt(dtau)} | {fmt(r['Teq'],1)} | {fmt(dteq,1)} | "
                f"{fmt(r.get('dZ_C'))} | {fmt(r.get('dZ_H'))} | {fmt(r.get('dZ_O'))} | "
                f"{fmt(r.get('wall_s'),1)} | {r['failure']} |"
            )
            # score vs Py-QSS
            if r["toggle"] in conform_scores and r["reliable"] and py_q and cv:
                score = 0.0
                if np.isfinite(r["tau_main_s"]) and np.isfinite(py_q["tau_main_s"]) and py_q["tau_main_s"] > 0:
                    # late-signed few %: prefer OF τ close to Py
                    err = abs(r["tau_main_s"] / py_q["tau_main_s"] - 1.0)
                    score += max(0.0, 1.0 - err / 0.05)  # 1 if within 5%
                if r["Teq"] is not None and cv["Teq"] is not None and py_c:
                    of_d = r["Teq"] - cv["Teq"]
                    py_d = py_q["Teq"] - py_c["Teq"]
                    if np.isfinite(of_d) and np.isfinite(py_d) and abs(py_d) > 1:
                        # same sign and magnitude family (within 2×)
                        if of_d * py_d > 0 and abs(of_d) / abs(py_d) < 2.5:
                            score += 1.0
                        elif of_d * py_d > 0:
                            score += 0.4
                if r.get("maxAbs_dZ") and py_q.get("maxAbs_dZ"):
                    ratio = r["maxAbs_dZ"] / py_q["maxAbs_dZ"]
                    if 0.5 <= ratio <= 2.0:
                        score += 1.0
                conform_scores[r["toggle"]].append(score)
                table.append(
                    dict(
                        point=p["label"],
                        toggle=r["toggle"],
                        score=score,
                        tau_main_s=r["tau_main_s"],
                        delta_Teq=dteq,
                        dZ_C=r.get("dZ_C"),
                        dZ_H=r.get("dZ_H"),
                        dZ_O=r.get("dZ_O"),
                        wall_s=r.get("wall_s"),
                        failure=r["failure"],
                    )
                )
        if py_q:
            lines.append(
                f"| *Py-QSS ref* | {fmt(py_q['tau_main_s']*1e3)} | — | {fmt(py_q['Teq'],1)} | "
                f"{fmt(py_q['Teq']-py_c['Teq'],1) if py_c else 'N/A'} | "
                f"{fmt(py_q.get('dZ_C'))} | {fmt(py_q.get('dZ_H'))} | {fmt(py_q.get('dZ_O'))} | "
                f"{fmt(py_q.get('wall_s'),1)} | — |"
            )
        lines.append("")

    # Rank toggles
    ranked = []
    for name, scores in conform_scores.items():
        if not scores:
            continue
        ranked.append((name, float(np.mean(scores)), scores))
    ranked.sort(key=lambda x: -x[1])
    lines += ["## Conform-config candidate", ""]
    if ranked:
        best = ranked[0]
        lines.append(
            f"**Candidate: `{best[0]}`** (mean conform score {best[1]:.2f} across points)."
        )
        lines.append("")
        lines.append("| toggle | mean score | per-point scores |")
        lines.append("|--------|-----------:|------------------|")
        for name, mu, sc in ranked:
            lines.append(f"| {name} | {mu:.2f} | {sc} |")
    else:
        lines.append("No complete toggle results yet — run `e15_2_toggle_host.sh` first.")

    lines += [
        "",
        "## E15.3 recommendation",
        "",
        "Provisional: **CONFORM** — signature map shows OF-QSS ≠ trained Py-QSS family "
        "(ΔTeq amplitude, drift, timeouts). Adopt-accurate without conform would invalidate "
        "the trained policy. Advisor decision required after reviewing this attribution table.",
        "",
    ]
    (OUT / "E15_2_ATTRIBUTION.md").write_text("\n".join(lines) + "\n")
    (OUT / "e15_2_attribution_table.json").write_text(
        json.dumps(dict(rows=table, ranked=[{"toggle": n, "mean": m, "scores": s} for n, m, s in ranked]), indent=2)
    )
    print("Wrote", OUT / "E15_2_ATTRIBUTION.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
