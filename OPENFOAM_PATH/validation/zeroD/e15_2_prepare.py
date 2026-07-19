#!/usr/bin/env python3
"""E15.2 — per-knob OF-QSS toggles at 3 attribution points (full trajectory).

Knobs from E15.1 (coefficient toggles first; T-freeze needs code rebuild):
  baseline OF qssCoeffs → each one-at-a-time toward handoff CanteraQSSODE

Measures vs baseline OF-QSS and vs Py-QSS at the same point:
  Δτ_main, ΔTeq, signed ΔZ_C/H/O, wall.

Usage:
  # prepare job list + IC (host)
  python validation/zeroD/e15_2_prepare.py
  # run inside docker (host launcher)
  bash validation/zeroD/e15_2_toggle_host.sh
  # postprocess
  python validation/zeroD/e15_2_postprocess.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "validation/zeroD/e15_conformance"
ATTR = OUT / "e15_2_attribution_points.json"
JOBS = OUT / "e15_2_jobs.json"

# Baseline = current OF production coeffs; toggle = handoff-like value
TOGGLES = [
    dict(name="baseline", epsmin=0.02, epsmax=100.0, dtmin=1e-12, abstol=1e-11),
    dict(name="epsmin_0p01", epsmin=0.01, epsmax=100.0, dtmin=1e-12, abstol=1e-11),
    dict(name="epsmax_20", epsmin=0.02, epsmax=20.0, dtmin=1e-12, abstol=1e-11),
    dict(name="dtmin_1e-15", epsmin=0.02, epsmax=100.0, dtmin=1e-15, abstol=1e-11),
    dict(name="abstol_1e-8", epsmin=0.02, epsmax=100.0, dtmin=1e-12, abstol=1e-8),
    # Combined conform candidate (handoff-like coeffs)
    dict(name="conform_coeffs", epsmin=0.01, epsmax=20.0, dtmin=1e-15, abstol=1e-8),
]


def chem_dict(solver: str, tog: dict) -> str:
    return f"""FoamFile
{{
    version         2;
    format          ascii;
    class           dictionary;
    object          chemistryProperties;
}}
chemistryType
{{
    solver          {solver};
}}
chemistry       on;
initialChemicalTimeStep 1e-07;
qssCoeffs
{{
    epsmin          {tog['epsmin']};
    epsmax          {tog['epsmax']};
    dtmin           {tog['dtmin']};
    dtmax           1e-06;
    abstol          {tog['abstol']};
    itermax         2;
}}
cvodeCoeffs
{{
    relTol          1e-08;
    absTol          1e-12;
    maxSteps        100000;
}}
odeCoeffs
{{
    solver          seulex;
    absTol          1e-12;
    relTol          1e-08;
}}
"""


def main() -> int:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from e15_write_ic import write_ic

    pts = json.loads(ATTR.read_text())["points"]
    # Prefer NTC first in job order
    order = {"NTC_lowT": 0, "MidT": 1, "high_T0": 2}
    pts = sorted(pts, key=lambda p: order.get(p["label"], 9))

    ic_dir = OUT / "e15_2_ics"
    chem_dir = OUT / "e15_2_chem"
    ic_dir.mkdir(parents=True, exist_ok=True)
    chem_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    idx = 0
    for p in pts:
        tag = f"{p['label']}_T{p['T0']:.0f}_p{p['p_atm']:.0f}_phi{p['phi']:.1f}".replace(
            ".", "p"
        )
        ic = ic_dir / f"{tag}_initialConditions"
        write_ic(ic, p["T0"], p["p_atm"], p["phi"])
        # endTime from Cantera τ in of_jobs if present else 2*presize
        pre = json.loads((OUT / "e15_presize.json").read_text())
        tau = None
        for row in pre["rows"]:
            if (
                abs(row["T0"] - p["T0"]) < 1e-9
                and abs(row["p_atm"] - p["p_atm"]) < 1e-9
                and abs(row["phi"] - p["phi"]) < 1e-9
            ):
                tau = row.get("tau_s")
                break
        t_end = 2.0 * float(tau) if tau else 0.01
        for tog in TOGGLES:
            chem_path = chem_dir / f"{tag}_{tog['name']}_chemistryProperties"
            chem_path.write_text(chem_dict("qss", tog))
            # also one CVODE baseline per point (shared)
            jobs.append(
                dict(
                    idx=idx,
                    point=p["label"],
                    tag=tag,
                    toggle=tog["name"],
                    solver="qss",
                    T0=p["T0"],
                    p_atm=p["p_atm"],
                    phi=p["phi"],
                    t_end_s=t_end,
                    wall_cap_s=900 if "1000_p1" not in tag else 3600,
                    ic_rel=str(ic.relative_to(ROOT)),
                    chem_rel=str(chem_path.relative_to(ROOT)),
                    out_rel=f"validation/zeroD/e15_conformance/e15_2_runs/{tag}/{tog['name']}",
                    work_rel=f"validation/zeroD/e15_conformance/e15_2_work/{tag}_{tog['name']}",
                    coeffs=tog,
                )
            )
            idx += 1
        # CVODE reference once per point
        chem_cv = chem_dir / f"{tag}_cvode_chemistryProperties"
        chem_cv.write_text(chem_dict("cvode", TOGGLES[0]))
        jobs.append(
            dict(
                idx=idx,
                point=p["label"],
                tag=tag,
                toggle="cvode_ref",
                solver="cvode",
                T0=p["T0"],
                p_atm=p["p_atm"],
                phi=p["phi"],
                t_end_s=t_end,
                wall_cap_s=3600 if p["T0"] >= 1000 and p["p_atm"] <= 1 else 900,
                ic_rel=str(ic.relative_to(ROOT)),
                chem_rel=str(chem_cv.relative_to(ROOT)),
                out_rel=f"validation/zeroD/e15_conformance/e15_2_runs/{tag}/cvode_ref",
                work_rel=f"validation/zeroD/e15_conformance/e15_2_work/{tag}_cvode_ref",
                coeffs=TOGGLES[0],
            )
        )
        idx += 1

    # TSV for container (no python)
    tsv = OUT / "e15_2_jobs.tsv"
    with tsv.open("w") as f:
        f.write(
            "idx\ttag\ttoggle\tsolver\tt_end_s\twall_cap_s\twork_rel\tout_rel\tic_rel\tchem_rel\n"
        )
        for j in jobs:
            f.write(
                f"{j['idx']}\t{j['tag']}\t{j['toggle']}\t{j['solver']}\t"
                f"{j['t_end_s']:.10g}\t{j['wall_cap_s']}\t{j['work_rel']}\t"
                f"{j['out_rel']}\t{j['ic_rel']}\t{j['chem_rel']}\n"
            )
    JOBS.write_text(json.dumps(dict(n=len(jobs), toggles=TOGGLES, jobs=jobs), indent=2))
    print(f"Wrote {len(jobs)} E15.2 jobs → {JOBS}")
    print("Order: NTC_lowT toggles first, then MidT, then high_T0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
