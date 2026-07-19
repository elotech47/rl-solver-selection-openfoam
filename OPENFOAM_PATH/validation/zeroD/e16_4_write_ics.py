#!/usr/bin/env python3
"""Write OpenFOAM chemFoam initialConditions from paper Z-based conditions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
CONDS = ROOT / "validation/e16_parity/E16_4_CONDITIONS.json"
OUT_DIR = ROOT / "validation/e16_parity/e16_4_ics"
FUEL = "nc12h26:1.0"
OX = "o2:1.0, n2:3.76"


def write_ic_z(path: Path, T0: float, p_atm: float, Z: float) -> dict:
    import cantera as ct

    gas = ct.Solution(str(YAML))
    gas.set_mixture_fraction(Z, FUEL, OX)
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
    return {
        "T0": T0,
        "p_atm": p_atm,
        "Z": Z,
        "phi": float(gas.equivalence_ratio()),
        "path": str(path),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="Write all E16.4 ICs")
    ap.add_argument("--id", type=str, default=None)
    args = ap.parse_args()
    cfg = json.loads(CONDS.read_text())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    metas = []
    for c in cfg["conditions"]:
        if args.id and c["id"] != args.id and not args.all:
            continue
        if not args.all and not args.id:
            continue
        path = OUT_DIR / f"{c['id']}_{c['label']}_initialConditions"
        meta = write_ic_z(path, c["T0"], c["p_atm"], c["Z"])
        meta["id"] = c["id"]
        meta["label"] = c["label"]
        metas.append(meta)
        print(meta)
    if args.all or args.id:
        (OUT_DIR / "meta.json").write_text(json.dumps(metas, indent=2))


if __name__ == "__main__":
    main()
