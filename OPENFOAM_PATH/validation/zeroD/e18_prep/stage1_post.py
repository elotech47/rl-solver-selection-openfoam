#!/usr/bin/env python3
"""E18 Stage 1 post: steady check, ignition-readiness, alphaEff confirmation."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
CASE = ROOT / "cases" / "opposedJet_E18"
OUT = ROOT / "validation" / "zeroD" / "e18_prep" / "stage1_cold"
Z_STAR = 0.12
T_MIX_STAR = 830.0
T_AIR = 1000.0
L = 0.008


def read_foam_scalar(path: Path) -> np.ndarray:
    text = path.read_text()
    m = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*\n(\d+)\s*\((.*?)\n\)\s*;",
        text,
        re.S,
    )
    if not m:
        m2 = re.search(r"internalField\s+uniform\s+([^;]+);", text)
        if not m2:
            raise SystemExit(f"cannot parse scalar {path}")
        return np.array([float(m2.group(1))])
    n = int(m.group(1))
    vals = np.fromstring(m.group(2).replace("\n", " "), sep=" ")
    if vals.size != n:
        raise SystemExit(f"{path}: expected {n} got {vals.size}")
    return vals


def read_foam_vector(path: Path) -> np.ndarray:
    text = path.read_text()
    m = re.search(
        r"internalField\s+nonuniform\s+List<vector>\s*\n(\d+)\s*\n?\(",
        text,
    )
    if not m:
        m2 = re.search(r"internalField\s+uniform\s+\(([^)]+)\);", text)
        if not m2:
            raise SystemExit(f"cannot parse vector {path}")
        return np.array([[float(x) for x in m2.group(1).split()]])
    n = int(m.group(1))
    triples = re.findall(r"\(([^)]+)\)", text[m.end() - 1 :])
    # first match is the opening of the list body; take first n vector triples
    # After `(` of list, each cell is (x y z)
    vecs = []
    for t in triples:
        parts = t.split()
        if len(parts) == 3:
            try:
                vecs.append([float(parts[0]), float(parts[1]), float(parts[2])])
            except ValueError:
                continue
        if len(vecs) >= n:
            break
    if len(vecs) != n:
        raise SystemExit(f"{path}: expected {n} vectors got {len(vecs)}")
    return np.array(vecs)


def latest_time(case: Path) -> Path:
    times = []
    for p in case.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name in ("0", "constant", "system") or name.startswith("processor"):
            continue
        try:
            times.append((float(name), p))
        except ValueError:
            continue
    if not times:
        raise SystemExit("no reconstructed time dirs")
    times.sort()
    return times[-1][1]


def centerline_mask(C: np.ndarray, tol: float = 2e-4) -> np.ndarray:
    # cells nearest y=0
    y = C[:, 1]
    return np.abs(y) <= tol


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tdir = latest_time(CASE)
    t_val = float(tdir.name)
    print(f"latest time dir: {tdir} (t={t_val})")

    C = read_foam_vector(CASE / "constant" / "C") if (CASE / "constant" / "C").is_file() else None
    # Prefer 0/C or postProcessing — write cell centres via postProcess if missing
    if C is None:
        # Try time dir
        for cand in (tdir / "C", CASE / "0" / "C"):
            if cand.is_file():
                C = read_foam_vector(cand)
                break
    if C is None:
        raise SystemExit("Need cell centres field C — run postProcess -func writeCellCentres")

    T = read_foam_scalar(tdir / "T")
    U = read_foam_vector(tdir / "U")
    Z = read_foam_scalar(tdir / "nc12h26")  # fuel mass fraction ≈ mixture fraction

    Tmax = float(T.max())
    Tmin = float(T.min())
    chem_off_ok = Tmax <= T_AIR + 0.05  # allow tiny numerics

    # Stagnation: Ux≈0 on centerline
    cl = centerline_mask(C, tol=max(1e-4, 0.5 * np.ptp(C[:, 1]) / 100))
    if cl.sum() < 5:
        # fallback: strip |y| smallest 2%
        yabs = np.abs(C[:, 1])
        cl = yabs <= np.quantile(yabs, 0.02)

    x_cl = C[cl, 0]
    Ux_cl = U[cl, 0]
    T_cl = T[cl]
    Z_cl = Z[cl]
    order = np.argsort(x_cl)
    x_cl, Ux_cl, T_cl, Z_cl = x_cl[order], Ux_cl[order], T_cl[order], Z_cl[order]

    # Find stagnation by Ux zero-crossing
    stag_x = float("nan")
    for i in range(len(Ux_cl) - 1):
        if Ux_cl[i] * Ux_cl[i + 1] <= 0:
            # linear interp
            if abs(Ux_cl[i + 1] - Ux_cl[i]) > 0:
                w = -Ux_cl[i] / (Ux_cl[i + 1] - Ux_cl[i])
                stag_x = float(x_cl[i] + w * (x_cl[i + 1] - x_cl[i]))
            else:
                stag_x = float(x_cl[i])
            break

    # Ignition readiness: cells near (Z*, Tmix*)
    dZ = np.abs(Z - Z_STAR)
    dT = np.abs(T - T_MIX_STAR)
    # primary: Z≈Z* and T within mixing envelope
    ready_mask = (dZ < 0.02) & (T > 500) & (T < 1000)
    n_ready = int(ready_mask.sum())
    if n_ready:
        # closest to (Z*, T*)
        score = (dZ / 0.02) ** 2 + ((T - T_MIX_STAR) / 50.0) ** 2
        score = np.where(ready_mask, score, np.inf)
        i_best = int(np.argmin(score))
        best = {
            "x": float(C[i_best, 0]),
            "y": float(C[i_best, 1]),
            "Z": float(Z[i_best]),
            "T": float(T[i_best]),
            "Ux": float(U[i_best, 0]),
        }
    else:
        # report nearest Z* cell in mixing layer
        mix = (Z > 0.02) & (Z < 0.5)
        if mix.any():
            i_best = int(np.argmin(np.where(mix, dZ, np.inf)))
            best = {
                "x": float(C[i_best, 0]),
                "y": float(C[i_best, 1]),
                "Z": float(Z[i_best]),
                "T": float(T[i_best]),
                "Ux": float(U[i_best, 0]),
                "note": "no cell within ΔZ<0.02 of Z*; nearest mix-layer Z*",
            }
        else:
            best = None
            i_best = -1

    # Peak T in mixing layer (Z∈[0.02,0.5]) — for chem-off should be ≤1000
    mix = (Z > 0.02) & (Z < 0.5)
    if mix.any():
        i_peak = int(np.argmax(np.where(mix, T, -np.inf)))
        peak_mix = {"T": float(T[i_peak]), "Z": float(Z[i_peak]), "x": float(C[i_peak, 0])}
    else:
        peak_mix = None

    # alphaEff from propSanity CSV / log
    alpha = {"status": "missing"}
    csv_path = CASE / "e12_prop_sanity.csv"
    # after reconstruct may be in OUT
    for cand in (OUT / "e12_prop_sanity.csv", CASE / "e12_prop_sanity.csv", OUT / "log.coldMix"):
        if not cand.is_file():
            continue
        if cand.suffix == ".csv":
            rows = list(csv.DictReader(filter(lambda r: not r.startswith("#"), cand.open())))
            # header may be comment-only — parse manually
            text = cand.read_text().strip().splitlines()
            if text:
                hdr = text[0].lstrip("#").split(",")
                last = text[-1].split(",")
                d = dict(zip(hdr, last))
                alpha = {
                    "source": str(cand),
                    "t": d.get("t"),
                    "alphaEffMin": d.get("alphaEffMin"),
                    "alphaEffMax": d.get("alphaEffMax"),
                    "muMin": d.get("muMin"),
                    "muMax": d.get("muMax"),
                    "nAlphaEffPos": d.get("nAlphaEffPos"),
                    "Tmax": d.get("Tmax"),
                }
            break
        else:
            # grep log
            lines = [ln for ln in cand.read_text().splitlines() if ln.startswith("propSanity:")]
            if lines:
                last = lines[-1]
                alpha = {"source": str(cand), "last_line": last}
                m = re.search(r"nAlphaEff>1e-20\s+(\d+)/(\d+)", last)
                if m:
                    alpha["nPos"] = int(m.group(1))
                    alpha["nCells"] = int(m.group(2))
                m = re.search(r"alphaEff\(turb=alphahe\)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)", last)
                if m:
                    alpha["alphaEffMin"] = float(m.group(1))
                    alpha["alphaEffMax"] = float(m.group(2))
                m = re.search(r"\bmu\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)", last)
                if m:
                    alpha["muMin"] = float(m.group(1))
                    alpha["muMax"] = float(m.group(2))
            break

    # Centerline profiles dump
    prof_path = OUT / "centerline_profiles.csv"
    with prof_path.open("w") as f:
        f.write("x,Ux,T,Z\n")
        for i in range(len(x_cl)):
            f.write(f"{x_cl[i]},{Ux_cl[i]},{T_cl[i]},{Z_cl[i]}\n")

    report = {
        "t_freeze": t_val,
        "L_m": L,
        "Tmin": Tmin,
        "Tmax": Tmax,
        "chem_off_ok": chem_off_ok,
        "stagnation_x_m": stag_x,
        "geometric_midplane_m": L / 2,
        "n_cells": int(T.size),
        "n_ready_Zstar": n_ready,
        "best_near_Zstar_Tmix": best,
        "peak_mixing_layer": peak_mix,
        "alphaEff": alpha,
        "profiles": str(prof_path),
    }
    (OUT / "STAGE1_REPORT.json").write_text(json.dumps(report, indent=2))

    # Markdown
    alpha_ok = False
    try:
        amax = float(alpha.get("alphaEffMax") or 0)
        npos = int(float(alpha.get("nAlphaEffPos") or alpha.get("nPos") or 0))
        alpha_ok = amax > 1e-20 and npos > 0
    except (TypeError, ValueError):
        alpha_ok = "alphaEffMax" in str(alpha) and "0 0" not in str(alpha.get("last_line", ""))

    md = f"""# E18 Stage 1 — cold mixing report

## Geometry
| | |
|--|--|
| Gap L | **{L} m** (Ember `example_diffusion` match) |
| V_inlet | ±0.4 m/s (= a·L/2, a=100) |
| Freeze time | **{t_val} s** |
| Cells | {T.size} |
| Geometric midplane | {L/2} m |
| Stagnation (Ux=0 on CL) | **{stag_x:.5f} m** |

## Chemistry OFF check
| | |
|--|--|
| Tmin / Tmax | {Tmin:.4f} / {Tmax:.4f} K |
| Gate Tmax ≤ 1000.05 K | **{"PASS" if chem_off_ok else "FAIL"}** |

## Ignition readiness (Z*≈{Z_STAR}, Tmix*≈{T_MIX_STAR} K)
| | |
|--|--|
| Cells with |Z-Z*|<0.02 in mix layer | {n_ready} |
| Best cell | {json.dumps(best)} |
| Peak mix-layer T / Z | {json.dumps(peak_mix)} |

## alphaEff
| | |
|--|--|
| Status | **{"PASS nonzero" if alpha_ok else "CHECK"}** |
| Detail | `{json.dumps(alpha)}` |

Root cause fix: Sutherland As/Ts were 0 → patched to air-like 1.67212e−6 / 170.672.
"""
    (OUT / "STAGE1_REPORT.md").write_text(md)
    print(md)
    print("Wrote", OUT / "STAGE1_REPORT.md")


if __name__ == "__main__":
    main()
