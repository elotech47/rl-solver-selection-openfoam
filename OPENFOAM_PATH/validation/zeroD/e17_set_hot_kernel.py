#!/usr/bin/env python3
"""Set opposedJet_2D internalField to hot premixed (Z,T) for E17 ignition smoke."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "cases/opposedJet_2D"
MECH = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"

# Oxidizer "o2:1.0, n2:3.76" (mole) → mass fractions (MW O2=32, N2=28)
_Y_O2_OX = 32.0 / (32.0 + 3.76 * 28.0)
_Y_N2_OX = 1.0 - _Y_O2_OX


def set_internal(path: Path, value: float) -> None:
    text = path.read_text()
    text2, n = re.subn(
        r"internalField\s+uniform\s+[^;]+;",
        f"internalField   uniform {value:.8g};",
        text,
        count=1,
    )
    if n != 1:
        raise RuntimeError(f"internalField not found in {path}")
    path.write_text(text2)


def mixture_Y(Z: float, T: float, p_atm: float) -> tuple[dict[str, float], str]:
    """Y at mixture fraction Z for pure fuel vs air."""
    try:
        import cantera as ct

        gas = ct.Solution(str(MECH))
        gas.set_mixture_fraction(Z, "nc12h26:1.0", "o2:1.0, n2:3.76")
        gas.TP = T, p_atm * ct.one_atm
        return {n: float(y) for n, y in zip(gas.species_names, gas.Y)}, "cantera"
    except ImportError:
        # Fuel stream pure nc12h26; Z is fuel-stream mass fraction.
        return {
            "nc12h26": Z,
            "o2": (1.0 - Z) * _Y_O2_OX,
            "n2": (1.0 - Z) * _Y_N2_OX,
        }, "fallback_no_cantera"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--Z", type=float, default=0.05)
    ap.add_argument("--T", type=float, default=1300.0)
    ap.add_argument("--p-atm", type=float, default=10.0)
    args = ap.parse_args()

    Y, src = mixture_Y(args.Z, args.T, args.p_atm)

    set_internal(CASE / "0/T", args.T)
    for sp in ("nc12h26", "o2", "n2"):
        set_internal(CASE / "0" / sp, Y[sp])
    if (CASE / "0/Ydefault").is_file():
        set_internal(CASE / "0/Ydefault", 0.0)

    meta = {
        "Z": args.Z,
        "T": args.T,
        "p_atm": args.p_atm,
        "Y_nc12h26": Y["nc12h26"],
        "Y_o2": Y["o2"],
        "Y_n2": Y["n2"],
        "source": src,
    }
    (CASE / "0/e17_kernel_meta.txt").write_text(str(meta) + "\n")
    print(meta)


if __name__ == "__main__":
    main()
