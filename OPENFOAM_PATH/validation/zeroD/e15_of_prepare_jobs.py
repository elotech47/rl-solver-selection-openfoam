#!/usr/bin/env python3
"""Prepare E15 OF job manifest + per-condition initialConditions + Y0."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from e15_write_ic import write_ic  # noqa: E402

OUT = ROOT / "validation/zeroD/e15_conformance"
PRE = OUT / "e15_presize.json"
JOBS = OUT / "e15_of_jobs.json"
IC_DIR = OUT / "of_ics"
TEND_MULT = 2.0
WALL_CAP_S = 900
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"


def main() -> int:
    import cantera as ct

    pre = json.loads(PRE.read_text())
    gas = ct.Solution(str(YAML))
    IC_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for row in pre["rows"]:
        if row["skip"]:
            continue
        T0, p_atm, phi = row["T0"], row["p_atm"], row["phi"]
        tag = f"T{T0:.0f}_p{p_atm:.0f}_phi{phi:.1f}".replace(".", "p")
        tau = float(row["tau_s"])
        t_end = TEND_MULT * tau
        ic_path = IC_DIR / f"{tag}_initialConditions"
        write_ic(ic_path, T0, p_atm, phi)
        gas.set_equivalence_ratio(phi, "nc12h26:1.0", "o2:1.0, n2:3.76")
        gas.TP = T0, p_atm * ct.one_atm
        y0 = {n: float(y) for n, y in zip(gas.species_names, gas.Y) if y > 0}
        (IC_DIR / f"{tag}_Y0.json").write_text(json.dumps(y0, indent=2))
        for solver in ("cvode", "qss"):
            jobs.append(
                dict(
                    tag=tag,
                    solver=solver,
                    T0=T0,
                    p_atm=p_atm,
                    phi=phi,
                    Z=row["Z"],
                    tau_cantera_s=tau,
                    t_end_s=t_end,
                    wall_cap_s=WALL_CAP_S,
                    ic_rel=f"validation/zeroD/e15_conformance/of_ics/{tag}_initialConditions",
                    y0_rel=f"validation/zeroD/e15_conformance/of_ics/{tag}_Y0.json",
                    out_rel=f"validation/zeroD/e15_conformance/of_runs/{tag}/{solver}",
                    work_rel=f"validation/zeroD/e15_conformance/of_work/{tag}_{solver}",
                )
            )
    payload = dict(
        campaign="E15_OF_signature_map",
        tend_mult=TEND_MULT,
        wall_cap_s=WALL_CAP_S,
        n_jobs=len(jobs),
        jobs=jobs,
    )
    JOBS.write_text(json.dumps(payload, indent=2))
    tsv = OUT / "e15_of_jobs.tsv"
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
    print(f"Wrote {len(jobs)} jobs → {JOBS} and {tsv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
