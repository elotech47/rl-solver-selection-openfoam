#!/usr/bin/env python3
"""E2: Per-species thermo audit — foam JANAF vs original Cantera YAML.

Evaluates cp and sensible enthalpy on T∈[300,3000] from:
  - cases/.../constant/thermo  (foam dict NASA-7)
  - mechanisms/n-dodecane.yaml (Cantera)
  - mechanisms/chemkin/therm.dat (Chemkin NASA, to localize conversion defects)

Outputs:
  validation/thermo_audit/thermo_audit.csv
  validation/thermo_audit/plots/*.png
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FOAM = ROOT / "cases" / "chemFoam_0D" / "constant" / "thermo"
DEFAULT_YAML = ROOT / "mechanisms" / "n-dodecane.yaml"
DEFAULT_CK = ROOT / "mechanisms" / "chemkin" / "therm.dat"
OUT_DIR = Path(__file__).resolve().parent

# OpenFOAM / Cantera convention: universal gas constant [J/(kmol·K)]
RR = 8314.462618  # CODATA; OF uses ~8314.47


def nasa7_cp_molar(a: np.ndarray, T: float) -> float:
    """cp [J/(kmol·K)] from dimensionless NASA-7 coeffs a[0..6]."""
    return RR * (
        a[0] + a[1] * T + a[2] * T**2 + a[3] * T**3 + a[4] * T**4
    )


def nasa7_h_molar(a: np.ndarray, T: float) -> float:
    """Absolute enthalpy h [J/kmol] from NASA-7."""
    return RR * T * (
        a[0]
        + a[1] * T / 2.0
        + a[2] * T**2 / 3.0
        + a[3] * T**3 / 4.0
        + a[4] * T**4 / 5.0
        + a[5] / T
    )


def nasa7_hs_molar(a: np.ndarray, T: float, Tref: float = 298.15) -> float:
    """Sensible enthalpy hs = h(T) − h(Tref) [J/kmol]."""
    return nasa7_h_molar(a, T) - nasa7_h_molar(a, Tref)


def pick_coeffs(low: np.ndarray, high: np.ndarray, Tcommon: float, T: float):
    return low if T < Tcommon else high


def parse_foam_thermo(path: Path) -> dict:
    """Parse OpenFOAM foamChemistry thermo dictionary."""
    txt = path.read_text()
    entries = re.findall(r"^(\w[\w\-]*)\n\{(.*?)^\}", txt, re.S | re.M)
    out = {}
    for name, body in entries:
        def grab(key, n=None):
            if n is None:
                m = re.search(rf"{key}\s+([\d.eE+\-]+)", body)
                return float(m.group(1)) if m else None
            m = re.search(rf"{key}\s*\(([^)]*)\)", body, re.S)
            vals = [float(x) for x in m.group(1).split()]
            assert len(vals) == n, (name, key, len(vals))
            return np.array(vals, dtype=float)

        out[name.lower()] = dict(
            name=name,
            W=grab("molWeight"),  # kg/kmol
            Tlow=grab("Tlow"),
            Thigh=grab("Thigh"),
            Tcommon=grab("Tcommon"),
            high=grab("highCpCoeffs", 7),
            low=grab("lowCpCoeffs", 7),
            source="foam",
        )
    return out


def parse_chemkin_therm(path: Path) -> dict:
    """Parse Chemkin therm.dat NASA-7 blocks (4-line species cards)."""
    lines = [
        ln.rstrip("\n")
        for ln in path.read_text().splitlines()
        if ln.strip() and not ln.startswith("!")
    ]
    # Skip THERMO / END headers
    i = 0
    while i < len(lines) and not (
        len(lines[i]) >= 80 and lines[i][79:80] == "1"
    ):
        # also accept shorter lines ending with 1
        if re.match(r".+\s+1\s*$", lines[i]) and i + 3 < len(lines):
            break
        i += 1

    out = {}
    while i + 3 < len(lines):
        l1, l2, l3, l4 = lines[i : i + 4]
        # Species card detection: line ends with 1 (col 80) or trailing 1
        if not (l1.rstrip().endswith("1") and l2.rstrip().endswith("2")):
            i += 1
            continue
        name = l1[:18].strip().lower()
        # Temperatures: often after 'G' or in fixed columns 46-73
        nums = re.findall(r"[\d.]+", l1[45:73] if len(l1) >= 73 else l1)
        # Fallback: search whole line for three temps
        if len(nums) < 3:
            nums = re.findall(r"\d+\.\d+", l1)
        if len(nums) < 3:
            i += 4
            continue
        Tlow, Thigh, Tcommon = map(float, nums[:3])

        def coeffs(a, b, c):
            # 5 floats on a, 5 on b (first 2 of next), etc. Chemkin E-format
            def floats(s):
                # Fixed 15-char fields preferred
                vals = []
                s = s[:75]  # ignore trailing line number
                for k in range(0, min(len(s), 75), 15):
                    chunk = s[k : k + 15].strip()
                    if chunk:
                        vals.append(float(chunk))
                return vals

            v = floats(a) + floats(b) + floats(c)
            return np.array(v[:7], dtype=float)

        # Line2: a1..a5 high; Line3: a6,a7 high, a1..a3 low; Line4: a4..a7 low
        def fl(s):
            vals = []
            s = s[:75]
            for k in range(0, min(len(s), 75), 15):
                chunk = s[k : k + 15].strip()
                if chunk:
                    vals.append(float(chunk))
            return vals

        v2, v3, v4 = fl(l2), fl(l3), fl(l4)
        high = np.array(v2[:5] + v3[:2], dtype=float)
        low = np.array(v3[2:5] + v4[:4], dtype=float)
        if len(high) != 7 or len(low) != 7:
            i += 4
            continue
        out[name] = dict(
            name=name,
            W=None,  # filled from foam/yaml later
            Tlow=Tlow,
            Thigh=Thigh,
            Tcommon=Tcommon,
            high=high,
            low=low,
            source="chemkin",
        )
        i += 4
        if l4.rstrip().endswith("END") or name == "end":
            break
    return out


def foam_props(entry, T: float):
    a = pick_coeffs(entry["low"], entry["high"], entry["Tcommon"], T)
    a_ref = pick_coeffs(entry["low"], entry["high"], entry["Tcommon"], 298.15)
    W = entry["W"]  # kg/kmol
    cp_molar = nasa7_cp_molar(a, T)
    hs_molar = nasa7_h_molar(a, T) - nasa7_h_molar(a_ref, 298.15)
    return dict(
        cp_mass=cp_molar / W,  # J/(kg·K)
        hs_mass=hs_molar / W,  # J/kg
        cp_molar=cp_molar,
        hs_molar=hs_molar,
        a=a,
    )


def cantera_species_map(yaml_path: Path):
    import cantera as ct

    gas = ct.Solution(str(yaml_path))
    return gas, {s.lower(): s for s in gas.species_names}


def audit(
    foam: dict,
    yaml_path: Path,
    ck: dict,
    T_grid: np.ndarray,
    out_dir: Path,
):
    import cantera as ct
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gas, name_map = cantera_species_map(yaml_path)
    rows = []

    for sp, ent in sorted(foam.items()):
        if sp not in name_map:
            rows.append(
                dict(
                    species=sp,
                    note="missing_in_yaml",
                    max_rel_cp=np.nan,
                    max_rel_hs=np.nan,
                    max_abs_hs=np.nan,
                    min_cp=np.nan,
                    cp_disc=np.nan,
                    hs_jump_at_Tcommon=np.nan,
                    hs_slope_disc=np.nan,
                    Tcommon=ent["Tcommon"],
                    Tlow=ent["Tlow"],
                    Thigh=ent["Thigh"],
                    ck_max_rel_cp=np.nan,
                )
            )
            continue

        idx = gas.species_index(name_map[sp])
        spec = gas.species(name_map[sp])
        th = spec.thermo
        Mw = gas.molecular_weights[idx]  # kg/kmol

        cp_f, hs_f, cp_c, hs_c = [], [], [], []
        for T in T_grid:
            T_eval = float(np.clip(T, ent["Tlow"], ent["Thigh"]))
            pf = foam_props(ent, T_eval)
            cp_f.append(pf["cp_mass"])
            hs_f.append(pf["hs_mass"])
            cp_c.append(th.cp(T_eval) / Mw)
            hs_c.append((th.h(T_eval) - th.h(298.15)) / Mw)

        cp_f = np.asarray(cp_f)
        hs_f = np.asarray(hs_f)
        cp_c = np.asarray(cp_c)
        hs_c = np.asarray(hs_c)

        # Relative mismatches (avoid /0)
        rel_cp = np.abs(cp_f - cp_c) / np.maximum(np.abs(cp_c), 1e-30)
        rel_hs = np.abs(hs_f - hs_c) / np.maximum(np.abs(hs_c), 1e-30)

        # Discontinuities at Tcommon
        Tc = ent["Tcommon"]
        eps = 1e-4
        cp_hi = nasa7_cp_molar(ent["high"], Tc + eps) / ent["W"]
        cp_lo = nasa7_cp_molar(ent["low"], Tc - eps) / ent["W"]
        cp_disc = abs(cp_hi - cp_lo)

        # Absolute-enthalpy jump at Tcommon (both branches at same T)
        h_lo = nasa7_h_molar(ent["low"], Tc) / ent["W"]
        h_hi = nasa7_h_molar(ent["high"], Tc) / ent["W"]
        hs_jump = abs(h_hi - h_lo)

        # Sensible-enthalpy compare uses consistent ref: h(T)-h(298) with
        # correct branch at each T (already in foam_props / Cantera).
        # Near T≈298, |hs|→0 so use abs error floor in relative metric.
        abs_hs = np.abs(hs_f - hs_c)
        rel_hs = abs_hs / np.maximum(np.abs(hs_c), 1e4)  # floor 10 kJ/kg
        max_abs_hs = float(np.max(abs_hs))
        # Chemkin vs foam coeff identity
        ck_max_rel_cp = np.nan
        if sp in ck:
            ck_ent = ck[sp]
            ck_ent = dict(ck_ent)
            ck_ent["W"] = ent["W"]
            rels = []
            for T in T_grid:
                T_eval = float(
                    np.clip(
                        T,
                        max(ent["Tlow"], ck_ent["Tlow"]),
                        min(ent["Thigh"], ck_ent["Thigh"]),
                    )
                )
                pf = foam_props(ent, T_eval)["cp_mass"]
                pc = foam_props(ck_ent, T_eval)["cp_mass"]
                rels.append(abs(pf - pc) / max(abs(pc), 1e-30))
            ck_max_rel_cp = float(np.max(rels))

        rows.append(
            dict(
                species=sp,
                note="",
                max_rel_cp=float(np.max(rel_cp)),
                max_rel_hs=float(np.max(rel_hs)),
                max_abs_hs=max_abs_hs,
                min_cp=float(np.min(cp_f)),
                cp_disc=float(cp_disc),
                hs_jump_at_Tcommon=float(hs_jump),
                hs_slope_disc=float(cp_disc),
                Tcommon=ent["Tcommon"],
                Tlow=ent["Tlow"],
                Thigh=ent["Thigh"],
                Tcommon_implausible=int(ent["Tcommon"] < 800 or ent["Tcommon"] > 2000),
                ck_max_rel_cp=ck_max_rel_cp,
                # stash for plots
                _cp_f=cp_f,
                _hs_f=hs_f,
                _cp_c=cp_c,
                _hs_c=hs_c,
            )
        )

    # Write CSV (without arrays)
    csv_path = out_dir / "thermo_audit.csv"
    fieldnames = [
        "species",
        "max_rel_cp",
        "max_rel_hs",
        "max_abs_hs",
        "min_cp",
        "cp_disc",
        "hs_jump_at_Tcommon",
        "hs_slope_disc",
        "Tlow",
        "Tcommon",
        "Thigh",
        "Tcommon_implausible",
        "ck_max_rel_cp",
        "note",
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: -(x["max_rel_cp"] or 0)):
            w.writerow(r)

    # Ranked summary print
    print(f"Wrote {csv_path}")
    print("\nTop 15 by max_rel_cp (foam vs Cantera):")
    ranked = sorted(
        [r for r in rows if not math.isnan(r["max_rel_cp"] or math.nan)],
        key=lambda x: -x["max_rel_cp"],
    )
    for r in ranked[:15]:
        print(
            f"  {r['species']:12s}  rel_cp={r['max_rel_cp']:.3e}  "
            f"rel_hs={r['max_rel_hs']:.3e}  abs_hs={r['max_abs_hs']:.4g}  "
            f"min_cp={r['min_cp']:.4g}  "
            f"cp_disc={r['cp_disc']:.4g}  h_jump={r['hs_jump_at_Tcommon']:.4g}  "
            f"Tcommon={r['Tcommon']}  ck_vs_foam={r['ck_max_rel_cp']}"
        )

    neg = [r for r in rows if (r["min_cp"] or 0) <= 0]
    print(f"\nSpecies with cp<=0 in range: {len(neg)}")
    for r in neg[:20]:
        print(f"  {r['species']} min_cp={r['min_cp']}")

    impl = [r for r in rows if r.get("Tcommon_implausible")]
    print(f"Implausible Tcommon (<800 or >2000): {len(impl)}")
    for r in impl:
        print(f"  {r['species']} Tcommon={r['Tcommon']}")

    # Plots
    plot_dir = out_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    majors = ["n2", "h2o", "co2", "co", "oh", "o2", "h", "o"]
    worst = [r["species"] for r in ranked[:10]]
    to_plot = []
    for s in worst + majors:
        if s not in to_plot:
            to_plot.append(s)

    by_name = {r["species"]: r for r in rows}
    for sp in to_plot:
        r = by_name.get(sp)
        if not r or "_cp_f" not in r:
            continue
        fig, ax = plt.subplots(1, 2, figsize=(10, 4))
        ax[0].plot(T_grid, r["_cp_f"], label="foam")
        ax[0].plot(T_grid, r["_cp_c"], "--", label="cantera")
        ax[0].axvline(r["Tcommon"], color="k", ls=":", lw=0.8)
        ax[0].set_title(f"{sp} cp [J/kg/K]")
        ax[0].legend()
        ax[1].plot(T_grid, r["_hs_f"], label="foam")
        ax[1].plot(T_grid, r["_hs_c"], "--", label="cantera")
        ax[1].axvline(r["Tcommon"], color="k", ls=":", lw=0.8)
        ax[1].set_title(f"{sp} hs [J/kg]")
        ax[1].legend()
        fig.tight_layout()
        fig.savefig(plot_dir / f"{sp}.png", dpi=120)
        plt.close(fig)

    print(f"Plots in {plot_dir}")

    # Material-failure flags
    bad = [
        r
        for r in rows
        if (r.get("max_rel_cp") or 0) > 1e-3
        or (r.get("max_rel_hs") or 0) > 1e-3
        or (r.get("max_abs_hs") or 0) > 1e3  # >1 kJ/kg abs hs error
        or (r.get("min_cp") or 1) <= 0
        or (r.get("cp_disc") or 0) > 50.0  # J/kg/K
        or (r.get("hs_jump_at_Tcommon") or 0) > 100.0  # J/kg absolute-h jump
    ]
    print(f"\nMaterial flag count (thresholds above): {len(bad)}")
    return rows, bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--foam", type=Path, default=DEFAULT_FOAM)
    ap.add_argument("--yaml", type=Path, default=DEFAULT_YAML)
    ap.add_argument("--chemkin", type=Path, default=DEFAULT_CK)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    foam = parse_foam_thermo(args.foam)
    print(f"Parsed foam thermo: {len(foam)} species from {args.foam}")
    ck = parse_chemkin_therm(args.chemkin)
    print(f"Parsed Chemkin therm: {len(ck)} species from {args.chemkin}")

    T_grid = np.linspace(300.0, 3000.0, 271)
    rows, bad = audit(foam, args.yaml, ck, T_grid, args.out)

    summary = args.out / "SUMMARY.txt"
    with summary.open("w") as f:
        f.write(f"foam_species={len(foam)}\nchemkin_species={len(ck)}\n")
        f.write(f"material_flags={len(bad)}\n")
        for r in bad:
            f.write(
                f"FLAG {r['species']} rel_cp={r['max_rel_cp']:.3e} "
                f"rel_hs={r['max_rel_hs']:.3e} min_cp={r['min_cp']:.4g} "
                f"cp_disc={r['cp_disc']:.4g} hs_jump={r['hs_jump_at_Tcommon']:.4g}\n"
            )
    print(f"Wrote {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
