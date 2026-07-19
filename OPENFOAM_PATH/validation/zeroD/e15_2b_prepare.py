#!/usr/bin/env python3
"""E15.2b — T-freeze alone (epsmin stays 0.02) at attribution + timeout points.

Toggles:
  Tfreeze_on   — production conform candidate (default after rebuild)
  Tfreeze_off  — A/B control (pre-conform semantics)
  cvode_ref    — CVODE path must stay bit-usable / unchanged behavior

Conditions: NTC_lowT, MidT, high_T0, timeout_700_60_1, timeout_900_60_1.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "validation/zeroD/e15_conformance"
JOBS = OUT / "e15_2b_jobs.json"

POINTS = [
    dict(label="NTC_lowT", T0=700.0, p_atm=60.0, phi=0.5),
    dict(label="MidT", T0=800.0, p_atm=10.0, phi=1.0),
    dict(label="high_T0", T0=1000.0, p_atm=10.0, phi=1.0),
    dict(label="timeout_700_60_1", T0=700.0, p_atm=60.0, phi=1.0),
    dict(label="timeout_900_60_1", T0=900.0, p_atm=60.0, phi=1.0),
]

# One change at a time: Tfreeze only; epsmin remains 0.02
TOGGLES = [
    dict(name="Tfreeze_on", Tfreeze=True, epsmin=0.02),
    dict(name="Tfreeze_off", Tfreeze=False, epsmin=0.02),
]


def chem_dict(solver: str, tog: dict | None) -> str:
    if solver == "cvode":
        qss = """qssCoeffs
{
    epsmin          0.02;
    epsmax          100;
    dtmin           1e-12;
    dtmax           1e-06;
    abstol          1e-11;
    itermax         2;
    Tfreeze         true;
}
"""
    else:
        assert tog is not None
        tf = "true" if tog["Tfreeze"] else "false"
        qss = f"""qssCoeffs
{{
    epsmin          {tog['epsmin']};
    epsmax          100;
    dtmin           1e-12;
    dtmax           1e-06;
    abstol          1e-11;
    itermax         2;
    Tfreeze         {tf};
}}
"""
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
{qss}cvodeCoeffs
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


def tau_for(p: dict) -> float | None:
    pre = json.loads((OUT / "e15_presize.json").read_text())
    for row in pre["rows"]:
        if (
            abs(row["T0"] - p["T0"]) < 1e-9
            and abs(row["p_atm"] - p["p_atm"]) < 1e-9
            and abs(row["phi"] - p["phi"]) < 1e-9
        ):
            return float(row["tau_s"])
    return None


def main() -> int:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from e15_write_ic import write_ic

    ic_dir = OUT / "e15_2b_ics"
    chem_dir = OUT / "e15_2b_chem"
    ic_dir.mkdir(parents=True, exist_ok=True)
    chem_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    idx = 0
    for p in POINTS:
        tag = f"{p['label']}_T{p['T0']:.0f}_p{p['p_atm']:.0f}_phi{p['phi']:.1f}".replace(
            ".", "p"
        )
        ic = ic_dir / f"{tag}_initialConditions"
        write_ic(ic, p["T0"], p["p_atm"], p["phi"])
        tau = tau_for(p)
        t_end = 2.0 * float(tau) if tau else 0.01
        # Prior map QSS stalls hit 900 s; give headroom while still failing hard if stuck
        is_timeout = p["label"].startswith("timeout_")
        wall = 1800 if is_timeout else 900

        for tog in TOGGLES:
            chem_path = chem_dir / f"{tag}_{tog['name']}_chemistryProperties"
            chem_path.write_text(chem_dict("qss", tog))
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
                    wall_cap_s=wall,
                    ic_rel=str(ic.relative_to(ROOT)),
                    chem_rel=str(chem_path.relative_to(ROOT)),
                    out_rel=f"validation/zeroD/e15_conformance/e15_2b_runs/{tag}/{tog['name']}",
                    work_rel=f"validation/zeroD/e15_conformance/e15_2b_work/{tag}_{tog['name']}",
                    coeffs=tog,
                )
            )
            idx += 1

        # CVODE once per point (CVODE path must remain usable / bit-unchanged)
        chem_cv = chem_dir / f"{tag}_cvode_chemistryProperties"
        chem_cv.write_text(chem_dict("cvode", None))
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
                wall_cap_s=wall,
                ic_rel=str(ic.relative_to(ROOT)),
                chem_rel=str(chem_cv.relative_to(ROOT)),
                out_rel=f"validation/zeroD/e15_conformance/e15_2b_runs/{tag}/cvode_ref",
                work_rel=f"validation/zeroD/e15_conformance/e15_2b_work/{tag}_cvode_ref",
                coeffs=None,
            )
        )
        idx += 1

    tsv = OUT / "e15_2b_jobs.tsv"
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
    JOBS.write_text(json.dumps(dict(n=len(jobs), toggles=TOGGLES, points=POINTS, jobs=jobs), indent=2))
    print(f"Wrote {len(jobs)} E15.2b jobs → {JOBS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
