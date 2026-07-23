#!/usr/bin/env python3
"""E17.2 minimal repro — dump chemFoam ICs from near-front cells + Y_n2 poison.

chemFoam requires:
  constantProperty pressure;
  fractionBasis   mass;
  fractions { ... }

Usage:
  python3 e17_2_write_ics.py
  bash e17_2_minimal_repro.sh
"""
from __future__ import annotations

import json
from pathlib import Path

# OPENFOAM_PATH/validation/zeroD/e17_2/ → parents[3] = OPENFOAM_PATH
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CELLS = json.loads((HERE / "near_front_cells.json").read_text())["cells"]


def write_ic(path: Path, T: float, p: float, Y: dict[str, float], note: str) -> None:
    # Ensure ΣY ≈ 1 for mass basis (chemFoam checks this)
    s = sum(Y.values())
    if abs(s) > 1e-30:
        Y = {k: v / s for k, v in Y.items()}

    lines = [
        "/*--------------------------------*- C++ -*----------------------------------*\\",
        f"| E17.2 minimal repro IC — {note}",
        "\\*---------------------------------------------------------------------------*/",
        "FoamFile",
        "{",
        "    version     2.0;",
        "    format      ascii;",
        "    class       dictionary;",
        "    object      initialConditions;",
        "}",
        "",
        "constantProperty pressure;",
        "fractionBasis   mass;",
        "",
        "fractions",
        "{",
    ]
    for sp, val in sorted(Y.items()):
        lines.append(f"    {sp:<16s}{val:.16g};")
    lines += [
        "}",
        f"p               {p};",
        f"T               {T};",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def poison_n2(Y: dict[str, float], yn2: float = -1e-4) -> dict[str, float]:
    """Inject Y_n2 = -1e-4; keep other species proportions for ΣY=1 after chemFoam read.

    chemFoam will see negative n2 in fractions. Layer-1 guards (or CVODE) must handle it.
    We do NOT renorm away the negative — that would erase the poison. Instead set n2
    negative and scale the rest so Σ(others)+yn2 = 1.
    """
    out = {k: float(v) for k, v in Y.items()}
    others = [k for k in out if k != "n2"]
    s = sum(max(out[k], 0.0) for k in others)
    target = 1.0 - yn2  # > 1 when yn2 negative
    if s > 0:
        for k in others:
            out[k] = max(out[k], 0.0) / s * target
    out["n2"] = yn2
    return out


def main() -> None:
    p = 10.0 * 101325.0
    meta = ROOT / "cases" / "opposedJet_2D" / "0" / "e17_kernel_meta.txt"
    if not meta.is_file():
        meta = (
            ROOT
            / "validation/zeroD/e17_remote_runs/smoke_20260719_211924/rlAdaptive/e17_kernel_meta.txt"
        )
    if meta.is_file():
        import ast

        d = ast.literal_eval(meta.read_text().strip())
        p = float(d.get("p_atm", 10.0)) * 101325.0

    for cell in CELLS[:5]:
        cid = cell["global_celli"]
        Y = {k: float(v) for k, v in cell["Y"].items()}
        T = float(cell["T"])
        write_ic(
            HERE / "ics" / f"cell_{cid}" / "initialConditions",
            T,
            p,
            Y,
            f"celli={cid} T={T:.2f} (as dumped)",
        )
        Yp = poison_n2(Y)
        write_ic(
            HERE / "ics" / f"cell_{cid}_Yn2neg" / "initialConditions",
            T,
            p,
            Yp,
            f"celli={cid} Y_n2=-1e-4 (transport-poison probe)",
        )
        print(
            f"cell {cid}: T={T:.1f} Yn2={Y.get('n2', float('nan')):.4e} "
            f"-> poison Yn2={Yp['n2']:.4e} sumY={sum(Yp.values()):.6f}"
        )


if __name__ == "__main__":
    main()
