#!/usr/bin/env python3
"""Prepare E15 OF T-freeze remap: QSS-only (CVODE reused from of_runs/).

Config: chemistryProperties.template → Tfreeze=true, epsmin=0.02.
Outputs → of_runs_tfreeze / of_work_tfreeze (preserves pre-freeze of_runs/).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from e15_write_ic import write_ic  # noqa: E402

OUT = ROOT / "validation/zeroD/e15_conformance"
PRE = OUT / "e15_presize.json"
JOBS = OUT / "e15_of_tfreeze_jobs.json"
IC_DIR = OUT / "of_ics"
TEND_MULT = 2.0
WALL_CAP_S = 900


def main() -> int:
    pre = json.loads(PRE.read_text())
    IC_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for row in pre["rows"]:
        if row.get("skip"):
            continue
        T0, p_atm, phi = row["T0"], row["p_atm"], row["phi"]
        tag = f"T{T0:.0f}_p{p_atm:.0f}_phi{phi:.1f}".replace(".", "p")
        tau = float(row["tau_s"])
        t_end = TEND_MULT * tau
        ic_path = IC_DIR / f"{tag}_initialConditions"
        if not ic_path.is_file():
            write_ic(ic_path, T0, p_atm, phi)
        jobs.append(
            dict(
                tag=tag,
                solver="qss",
                T0=T0,
                p_atm=p_atm,
                phi=phi,
                Z=row["Z"],
                tau_cantera_s=tau,
                t_end_s=t_end,
                wall_cap_s=WALL_CAP_S,
                ic_rel=f"validation/zeroD/e15_conformance/of_ics/{tag}_initialConditions",
                y0_rel=f"validation/zeroD/e15_conformance/of_ics/{tag}_Y0.json",
                out_rel=f"validation/zeroD/e15_conformance/of_runs_tfreeze/{tag}/qss",
                work_rel=f"validation/zeroD/e15_conformance/of_work_tfreeze/{tag}_qss",
                cvode_out_rel=f"validation/zeroD/e15_conformance/of_runs/{tag}/cvode",
                old_qss_out_rel=f"validation/zeroD/e15_conformance/of_runs/{tag}/qss",
            )
        )
    payload = dict(
        campaign="E15_OF_signature_map_Tfreeze",
        config="Tfreeze=true epsmin=0.02",
        tend_mult=TEND_MULT,
        wall_cap_s=WALL_CAP_S,
        n_jobs=len(jobs),
        note="QSS-only; CVODE baselines reused from of_runs/ (CVODE path bit-unchanged)",
        jobs=jobs,
    )
    JOBS.write_text(json.dumps(payload, indent=2))
    tsv = OUT / "e15_of_tfreeze_jobs.tsv"
    with tsv.open("w") as f:
        f.write(
            "idx\ttag\tsolver\tT0\tp_atm\tphi\tt_end_s\twall_cap_s\t"
            "work_rel\tout_rel\tic_rel\ty0_rel\n"
        )
        for i, j in enumerate(jobs):
            f.write(
                f"{i}\t{j['tag']}\t{j['solver']}\t{j['T0']}\t{j['p_atm']}\t"
                f"{j['phi']}\t{j['t_end_s']:.10g}\t{j['wall_cap_s']}\t"
                f"{j['work_rel']}\t{j['out_rel']}\t{j['ic_rel']}\t{j['y0_rel']}\n"
            )
    print(f"Wrote {len(jobs)} QSS T-freeze jobs → {JOBS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
