#!/usr/bin/env python3
"""Convert Luo n-dodecane YAML → Chemkin (Cantera) → fix for chemkinToFoam."""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path

import cantera as ct

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_YAML = ROOT / "mechanisms" / "n-dodecane.yaml"
OUT_DIR = ROOT / "mechanisms" / "chemkin"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_therm_of(gas: ct.Solution, path: Path) -> None:
    lines = ["THERMO ALL\n", "   300.000  1000.000  5000.000\n"]
    for sp in gas.species():
        name = sp.name[:18]
        elems = list(sp.composition.items())
        while len(elems) < 4:
            elems.append(("", 0))
        elem_str = "".join(
            f"{el.upper():<2}{int(n):3d}" if el else "     " for el, n in elems[:4]
        )
        th = sp.thermo
        Tmin, Tmid, Tmax = th.min_temp, float(th.coeffs[0]), th.max_temp
        c = th.coeffs
        high, low = list(c[1:8]), list(c[8:15])
        date = "L 1/00"
        body = (
            f"{name:<18}{date:<6}{elem_str}G"
            f"{Tmin:10.3f}{Tmax:10.3f}{Tmid:10.3f}"
        )
        body = (body + " " * 80)[:79] + "1"

        def five(vals, lineno):
            s = "".join(f"{v:15.8E}" for v in vals)
            return f"{s:<75}{lineno:5d}\n"

        lines += [
            body + "\n",
            five(high[0:5], 2),
            five(high[5:7] + low[0:3], 3),
            five(low[3:7] + [0.0], 4),
        ]
    lines.append("END\n")
    path.write_text("".join(lines))


def fix_chem_inp(path: Path) -> None:
    text = path.read_text()
    text = re.sub(
        r"ELEM\n.*?\nEND",
        "ELEMENTS\nC\nH\nN\nO\nAR\nHE\nEND",
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(r"^REACTIONS CAL/MOLE MOLE\s*$", "REACTIONS CAL/MOLE", text, flags=re.M)
    text = re.sub(r"^REACTIONS CAL/MOLE MOLES\s*$", "REACTIONS CAL/MOLE", text, flags=re.M)
    path.write_text(text)


def ensure_transport(out_dir: Path) -> None:
    """Minimal OF transportProperties (copied from GRI if present later)."""
    tp = out_dir / "transportProperties"
    if tp.is_file():
        return
    tp.write_text(
        """/*--------------------------------*- C++ -*----------------------------------*\\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      transportProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

".*"
{
    transport
    {
        As  1.67212e-06;
        Ts  170.672;
    }
}

// ************************************************************************* //
"""
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", type=Path, default=DEFAULT_YAML)
    args = ap.parse_args()
    if not args.yaml.is_file():
        print(f"Missing {args.yaml}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gas = ct.Solution(str(args.yaml))
    gas.write_chemkin(
        mechanism_path=str(OUT_DIR / "chem.inp"),
        thermo_path=str(OUT_DIR / "therm.dat"),
        transport_path=str(OUT_DIR / "tran.dat"),
        overwrite=True,
        quiet=True,
    )
    fix_chem_inp(OUT_DIR / "chem.inp")
    write_therm_of(gas, OUT_DIR / "therm_of.dat")
    ensure_transport(OUT_DIR)

    digest = sha256(args.yaml)
    (ROOT / "mechanisms" / "CONVERSION.md").write_text(
        f"""# Mechanism conversion log

## Source
- `{args.yaml.relative_to(ROOT)}`
- SHA256: `{digest}`
- Species: {gas.n_species}, Reactions: {gas.n_reactions}

## Host steps (automated by `tools/convert_mechanism.py`)
1. `Solution.write_chemkin` → `chemkin/chem.inp`, `therm.dat`, `tran.dat`
2. Fix `ELEMENTS` block + `REACTIONS CAL/MOLE` for ESI chemkinReader
3. Rewrite NASA7 headers to 80-col CHEMKIN-II → `therm_of.dat`
4. Provide OpenFOAM-format `transportProperties` (GRI-style `".*"` defaults)

## Container import
```bash
./container/of_shell.sh
# or non-interactive:
docker run --rm --platform=linux/amd64 --entrypoint /bin/bash \\
  -v \"$PWD:/work\" -w /work opencfd/openfoam-default:2312 \\
  /work/tools/run_chemkinToFoam.sh
```
Produces `mechanisms/foam/reactions` and `mechanisms/foam/thermo`.

## Status
- Host write_chemkin + patches: **OK**
- chemkinToFoam: see `tools/run_chemkinToFoam.sh` (verified ESI 2312)
"""
    )
    print(f"SHA256={digest}")
    print(f"species={gas.n_species} reactions={gas.n_reactions}")
    print("write_chemkin=ok therm_of=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
