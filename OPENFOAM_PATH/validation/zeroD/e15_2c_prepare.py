#!/usr/bin/env python3
"""E15.2c — second toggle: epsmin=0.01 ON TOP of T-freeze (epsmin alone already measured in E15.2).

Jobs: QSS only at the 5 gate points. CVODE reused from e15_2b_runs.
No Tfreeze_off (those timeout controls cost ~1800 s and already measured).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "validation/zeroD/e15_conformance"
JOBS = OUT / "e15_2c_jobs.json"

POINTS = [
    dict(label="NTC_lowT", T0=700.0, p_atm=60.0, phi=0.5),
    dict(label="MidT", T0=800.0, p_atm=10.0, phi=1.0),
    dict(label="high_T0", T0=1000.0, p_atm=10.0, phi=1.0),
    dict(label="timeout_700_60_1", T0=700.0, p_atm=60.0, phi=1.0),
    dict(label="timeout_900_60_1", T0=900.0, p_atm=60.0, phi=1.0),
]

TOGGLE = dict(name="Tfreeze_epsmin_0p01", Tfreeze=True, epsmin=0.01)


def chem_dict(tog: dict) -> str:
    return f"""FoamFile
{{
    version         2;
    format          ascii;
    class           dictionary;
    object          chemistryProperties;
}}
chemistryType
{{
    solver          qss;
}}
chemistry       on;
initialChemicalTimeStep 1e-07;
qssCoeffs
{{
    epsmin          {tog['epsmin']};
    epsmax          100;
    dtmin           1e-12;
    dtmax           1e-06;
    abstol          1e-11;
    itermax         2;
    Tfreeze         true;
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

    ic_dir = OUT / "e15_2c_ics"
    chem_dir = OUT / "e15_2c_chem"
    ic_dir.mkdir(parents=True, exist_ok=True)
    chem_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    for idx, p in enumerate(POINTS):
        tag = f"{p['label']}_T{p['T0']:.0f}_p{p['p_atm']:.0f}_phi{p['phi']:.1f}".replace(
            ".", "p"
        )
        ic = ic_dir / f"{tag}_initialConditions"
        write_ic(ic, p["T0"], p["p_atm"], p["phi"])
        tau = tau_for(p)
        t_end = 2.0 * float(tau) if tau else 0.01
        is_timeout = p["label"].startswith("timeout_")
        wall = 900 if is_timeout else 900  # Tfreeze should finish fast; 900 is plenty
        tog = TOGGLE
        chem_path = chem_dir / f"{tag}_{tog['name']}_chemistryProperties"
        chem_path.write_text(chem_dict(tog))
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
                out_rel=f"validation/zeroD/e15_conformance/e15_2c_runs/{tag}/{tog['name']}",
                work_rel=f"validation/zeroD/e15_conformance/e15_2c_work/{tag}_{tog['name']}",
                coeffs=tog,
                # CVODE / Tfreeze_on baseline from E15.2b
                cvode_out_rel=f"validation/zeroD/e15_conformance/e15_2b_runs/{tag}/cvode_ref",
                tfreeze_out_rel=f"validation/zeroD/e15_conformance/e15_2b_runs/{tag}/Tfreeze_on",
            )
        )

    tsv = OUT / "e15_2c_jobs.tsv"
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
    JOBS.write_text(
        json.dumps(dict(n=len(jobs), toggle=TOGGLE, points=POINTS, jobs=jobs), indent=2)
    )
    print(f"Wrote {len(jobs)} E15.2c jobs → {JOBS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
