#!/usr/bin/env python3
"""Write OpenFOAM chemFoam initialConditions for given T0, p_atm, phi."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"


def write_ic(path: Path, T0: float, p_atm: float, phi: float) -> dict:
    import cantera as ct

    gas = ct.Solution(str(YAML))
    gas.set_equivalence_ratio(phi, "nc12h26:1.0", "o2:1.0, n2:3.76")
    gas.TP = T0, p_atm * ct.one_atm
    lines = []
    for name, x in zip(gas.species_names, gas.X):
        if x > 1e-16:
            lines.append(f"    {name}             {x:.16g};")
    text = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      initialConditions;
}}
constantProperty pressure;
fractionBasis   mole;
fractions
{{
{chr(10).join(lines)}
}}
p               {gas.P:.8g};
T               {T0:.8g};
"""
    path.write_text(text)
    return dict(
        T0=T0,
        p_atm=p_atm,
        phi=phi,
        Z=float(
            gas.mixture_fraction("nc12h26:1.0", "o2:1.0, n2:3.76", element="C")
        ),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--T0", type=float, required=True)
    ap.add_argument("--p-atm", type=float, required=True)
    ap.add_argument("--phi", type=float, required=True)
    ap.add_argument("-o", type=Path, required=True)
    args = ap.parse_args()
    args.o.parent.mkdir(parents=True, exist_ok=True)
    meta = write_ic(args.o, args.T0, args.p_atm, args.phi)
    print(meta)


if __name__ == "__main__":
    main()
