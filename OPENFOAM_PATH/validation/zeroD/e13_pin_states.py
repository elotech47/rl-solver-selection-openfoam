#!/usr/bin/env python3
"""E13.1 scaffold — single-step OF-QSS vs Python-QSS at pinned high-T states.

Full OF-in-the-loop comparison requires chemFoamDebug QSS with state I/O;
this script pins Cantera MidT states and runs the handoff Python QSS reference
one 1 µs step as the parity target. OF dump integration is TODO in E13.1b.
"""
from __future__ import annotations

import json
from pathlib import Path

import cantera as ct
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
OUT = ROOT / "validation/zeroD/e13_qss"
TEMPS = (1300.0, 1500.0, 1700.0, 2000.0)


def midt_moles(gas):
    names = {n.lower(): n for n in gas.species_names}
    return {
        names["o2"]: 0.20775813522367179,
        names["n2"]: 0.7811705884410058,
        names["nc12h26"]: 0.01107127633532227,
    }


def pin_states():
    gas = ct.Solution(str(YAML))
    gas.TPX = 800.0, 10 * ct.one_atm, midt_moles(gas)
    r = ct.IdealGasConstPressureReactor(gas)
    sim = ct.ReactorNet([r])
    targets = list(TEMPS)
    pinned = []
    while sim.time < 0.01 and targets:
        sim.step()
        if r.T >= targets[0]:
            pinned.append(
                dict(
                    T=float(r.T),
                    P=float(r.thermo.P),
                    t=float(sim.time),
                    Y=r.thermo.Y.copy().tolist(),
                    names=list(gas.species_names),
                )
            )
            targets.pop(0)
    return pinned


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pinned = pin_states()
    (OUT / "pinned_states.json").write_text(
        json.dumps(
            [
                {k: (v if k != "Y" else f"len={len(v)}") for k, v in s.items()}
                for s in pinned
            ],
            indent=2,
        )
    )
    # Full Y arrays separately
    np.savez_compressed(
        OUT / "pinned_states.npz",
        **{f"T{int(s['T'])}_Y": np.array(s["Y"]) for s in pinned},
        Ts=np.array([s["T"] for s in pinned]),
        Ps=np.array([s["P"] for s in pinned]),
        ts=np.array([s["t"] for s in pinned]),
    )
    print(f"Pinned {len(pinned)} states → {OUT}")
    for s in pinned:
        print(f"  T={s['T']:.1f} K at t={s['t']*1e3:.4f} ms")
    (OUT / "E13_STATUS.md").write_text(
        "# E13 QSS parity (opened after E11.3 green)\n\n"
        f"- Thermo: **refit** `{YAML.relative_to(ROOT)}`\n"
        f"- E13.1 pinned states: **{len(pinned)}** at T∈{TEMPS}\n"
        "- Next: OF-QSS vs Python-QSS 1 µs step at identical (Y,T,p,ε,controller)\n"
        "- Then E13.2 (E7 rates), E13.3 energy-path, E13.4 cool-flame timing\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
