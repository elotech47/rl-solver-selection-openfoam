#!/usr/bin/env python3
"""E11.1 — Harmonize NASA-7 breakpoints to shared [Tlow, Tc, Thigh].

Refits every species' low/high polynomials to match the *original* cp(T) on a
dense grid, with:
  - C0/C1 continuity of cp at Tc
  - exact h(298.15) and s(298.15) vs original (Hf / S0 preserved)
  - h/s continuity at Tc (a5_high, a6_high)

Trade study: Tc ∈ {1000, 1400} K with shared window [300, Tc, 3500].
ch3o (original Thigh=3000): high-range poly extrapolated to 3500 (documented).
Single-range h (cp = 5/2 R): machine-precision unit test.

Gates (per species, mass basis, vs original on [300, 3000]):
  max |Δcp|/cp ≤ 0.2%
  max |Δhs| ≤ 2 kJ/kg
  cp > 0 everywhere
  |cp_high − cp_low| at Tc ≤ 0.1 J/(kg·K)
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import cantera as ct
import numpy as np
from numpy.linalg import lstsq

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YAML = ROOT / "mechanisms" / "n-dodecane.yaml"
OUT_DIR = ROOT / "mechanisms" / "refit"
RR = 8314.462618  # J/(kmol·K)
TREF = 298.15
TLOW_TGT = 300.0
THIGH_TGT = 3500.0

# Gates
GATE_CP_REL = 0.002  # 0.2%
GATE_HS_ABS = 2000.0  # J/kg = 2 kJ/kg
GATE_CP_CONT = 0.1  # J/(kg·K)


@dataclass
class SpeciesFit:
    name: str
    Tc: float
    original_Trange: tuple[float, float, float]
    extrapolated_high: bool
    single_range_h: bool
    max_rel_cp: float
    max_abs_hs: float  # J/kg
    cp_cont: float  # J/(kg·K)
    cp_min: float
    gate_cp: bool
    gate_hs: bool
    gate_cont: bool
    gate_pos: bool
    pass_all: bool


def nasa7_cp_R(a: np.ndarray, T: float | np.ndarray):
    return a[0] + a[1] * T + a[2] * T**2 + a[3] * T**3 + a[4] * T**4


def nasa7_h_RT(a: np.ndarray, T: float | np.ndarray):
    return (
        a[0]
        + a[1] * T / 2.0
        + a[2] * T**2 / 3.0
        + a[3] * T**3 / 4.0
        + a[4] * T**4 / 5.0
        + a[5] / T
    )


def nasa7_s_R(a: np.ndarray, T: float | np.ndarray):
    return (
        a[0] * np.log(T)
        + a[1] * T
        + a[2] * T**2 / 2.0
        + a[3] * T**3 / 3.0
        + a[4] * T**4 / 4.0
        + a[6]
    )


def orig_coeffs(th: ct.NasaPoly2) -> tuple[float, np.ndarray, np.ndarray]:
    c = th.coeffs
    return float(c[0]), np.array(c[1:8], dtype=float), np.array(c[8:15], dtype=float)


def orig_cp_R(th: ct.NasaPoly2, T: np.ndarray) -> np.ndarray:
    """Evaluate original dimensionless cp/R, clamping T into [Tmin, Tmax].

    Above original Tmax (ch3o→3000): use high-range poly (documented extrapolation).
    Below Tmin: use low-range poly.
    """
    Tmid, high, low = orig_coeffs(th)
    Tmin, Tmax = th.min_temp, th.max_temp
    out = np.empty_like(T, dtype=float)
    for i, Ti in enumerate(np.atleast_1d(T).astype(float)):
        # Always evaluate with the poly that *would* apply at clamped T,
        # but for T > Tmax keep using high poly (extrapolation).
        if Ti < Tmid:
            a = low
        else:
            a = high
        # Single-range (Tmid >= Tmax): both identical
        if Tmid >= Tmax - 1e-6:
            a = low
        out[i] = nasa7_cp_R(a, Ti)
    return out


def orig_h_RT(th: ct.NasaPoly2, T: float) -> float:
    Tmid, high, low = orig_coeffs(th)
    a = low if T < Tmid or Tmid >= th.max_temp - 1e-6 else high
    return float(nasa7_h_RT(a, T))


def orig_s_R(th: ct.NasaPoly2, T: float) -> float:
    Tmid, high, low = orig_coeffs(th)
    a = low if T < Tmid or Tmid >= th.max_temp - 1e-6 else high
    return float(nasa7_s_R(a, T))


def vandermonde_cp(T: np.ndarray, Tscale: float = 1000.0) -> np.ndarray:
    """Design matrix in scaled temp x=T/Tscale for numerical stability.

    cp/R = b0 + b1 x + b2 x^2 + b3 x^3 + b4 x^4
    NASA a_k = b_k / Tscale^k
    """
    x = T / Tscale
    return np.column_stack([x**k for k in range(5)])


def b_to_nasa(b: np.ndarray, Tscale: float = 1000.0) -> np.ndarray:
    a = np.zeros(7)
    for k in range(5):
        a[k] = b[k] / (Tscale**k)
    return a


def fit_cp_segments(
    T_low: np.ndarray,
    cpR_low: np.ndarray,
    T_high: np.ndarray,
    cpR_high: np.ndarray,
    Tc: float,
    Tscale: float = 1000.0,
    soft_c1: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Least-squares NASA a0..a4 for low/high with C0/C1 cp continuity at Tc.

    Fit in scaled coordinates, then convert to NASA-7 a coeffs.
    If soft_c1: enforce C0 hard, C1 as a heavy penalty (helps hard Tmid outliers).
    """
    A_l = vandermonde_cp(T_low, Tscale)
    A_h = vandermonde_cp(T_high, Tscale)
    xc = Tc / Tscale
    v = np.array([xc**k for k in range(5)], dtype=float)
    dv_dT = np.array(
        [0.0, 1.0, 2 * xc, 3 * xc**2, 4 * xc**3], dtype=float
    ) / Tscale

    n_l, n_h = len(T_low), len(T_high)
    if not soft_c1:
        C = np.zeros((2, 10))
        C[0, 0:5] = v
        C[0, 5:10] = -v
        C[1, 0:5] = dv_dT
        C[1, 5:10] = -dv_dT
        A = np.zeros((n_l + n_h, 10))
        A[:n_l, 0:5] = A_l
        A[n_l:, 5:10] = A_h
        b = np.concatenate([cpR_low, cpR_high])
        _, s, Vt = np.linalg.svd(C, full_matrices=True)
        rank = int(np.sum(s > 1e-12))
        N = Vt[rank:].T
        z, *_ = lstsq(A @ N, b, rcond=None)
        x = N @ z
    else:
        # Hard C0 only
        C = np.zeros((1, 10))
        C[0, 0:5] = v
        C[0, 5:10] = -v
        # Relative-error weights + heavy C1 penalty row
        w_l = 1.0 / np.maximum(np.abs(cpR_low), 0.1)
        w_h = 1.0 / np.maximum(np.abs(cpR_high), 0.1)
        A = np.zeros((n_l + n_h + 1, 10))
        A[:n_l, 0:5] = A_l * w_l[:, None]
        A[n_l : n_l + n_h, 5:10] = A_h * w_h[:, None]
        # C1 penalty: weight ~ 1e3 on dcp/dT match (dimensionless / K)
        pen = 1.0e3
        A[-1, 0:5] = pen * dv_dT
        A[-1, 5:10] = -pen * dv_dT
        b = np.concatenate([cpR_low * w_l, cpR_high * w_h, [0.0]])
        _, s, Vt = np.linalg.svd(C, full_matrices=True)
        rank = int(np.sum(s > 1e-12))
        N = Vt[rank:].T
        z, *_ = lstsq(A @ N, b, rcond=None)
        x = N @ z

    a_low = b_to_nasa(x[:5], Tscale)
    a_high = b_to_nasa(x[5:], Tscale)
    return a_low, a_high


def set_integration_constants(
    a_low: np.ndarray,
    a_high: np.ndarray,
    Tc: float,
    h_RT_ref: float,
    s_R_ref: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Fix a5,a6 from h/s at TREF (low) and continuity at Tc (high)."""
    a_low = a_low.copy()
    a_high = a_high.copy()
    # h/RT = … + a5/T  → a5 = T * (h/RT − poly_without_a5)
    poly_h_low = (
        a_low[0]
        + a_low[1] * TREF / 2.0
        + a_low[2] * TREF**2 / 3.0
        + a_low[3] * TREF**3 / 4.0
        + a_low[4] * TREF**4 / 5.0
    )
    a_low[5] = TREF * (h_RT_ref - poly_h_low)
    poly_s_low = (
        a_low[0] * math.log(TREF)
        + a_low[1] * TREF
        + a_low[2] * TREF**2 / 2.0
        + a_low[3] * TREF**3 / 3.0
        + a_low[4] * TREF**4 / 4.0
    )
    a_low[6] = s_R_ref - poly_s_low

    # Continuity h(Tc), s(Tc)
    h_low = nasa7_h_RT(a_low, Tc)
    s_low = nasa7_s_R(a_low, Tc)
    poly_h_high = (
        a_high[0]
        + a_high[1] * Tc / 2.0
        + a_high[2] * Tc**2 / 3.0
        + a_high[3] * Tc**3 / 4.0
        + a_high[4] * Tc**4 / 5.0
    )
    a_high[5] = Tc * (h_low - poly_h_high)
    poly_s_high = (
        a_high[0] * math.log(Tc)
        + a_high[1] * Tc
        + a_high[2] * Tc**2 / 2.0
        + a_high[3] * Tc**3 / 3.0
        + a_high[4] * Tc**4 / 4.0
    )
    a_high[6] = s_low - poly_s_high
    return a_low, a_high


def evaluate_gates(
    name: str,
    W: float,
    th_orig: ct.NasaPoly2,
    a_low: np.ndarray,
    a_high: np.ndarray,
    Tc: float,
    T_grid: np.ndarray,
    extrapolated: bool,
    single_h: bool,
) -> SpeciesFit:
    Tmid0, _, _ = orig_coeffs(th_orig)
    cp_ref = orig_cp_R(th_orig, T_grid) * RR / W  # J/kg/K
    hs_ref = np.array(
        [
            (orig_h_RT(th_orig, float(T)) * RR * T - orig_h_RT(th_orig, TREF) * RR * TREF)
            / W
            for T in T_grid
        ]
    )

    def cp_new(T):
        a = a_low if T < Tc else a_high
        return nasa7_cp_R(a, T) * RR / W

    def hs_new(T):
        a = a_low if T < Tc else a_high
        return (nasa7_h_RT(a, T) * RR * T - nasa7_h_RT(a_low, TREF) * RR * TREF) / W

    cp_n = np.array([cp_new(float(T)) for T in T_grid])
    hs_n = np.array([hs_new(float(T)) for T in T_grid])

    # Compare only where original is not wildly extrapolated for reporting,
    # but gate on [300, 3000] as specified (includes ch3o extrapolation zone).
    mask = (T_grid >= 300.0) & (T_grid <= 3000.0)
    rel = np.abs(cp_n[mask] - cp_ref[mask]) / np.maximum(np.abs(cp_ref[mask]), 1e-12)
    max_rel = float(np.max(rel))
    max_hs = float(np.max(np.abs(hs_n[mask] - hs_ref[mask])))
    cp_cont = abs(cp_new(Tc) - (nasa7_cp_R(a_low, Tc) * RR / W))  # should be ~0
    # Explicit low vs high at Tc
    cp_cont = abs(
        nasa7_cp_R(a_low, Tc) * RR / W - nasa7_cp_R(a_high, Tc) * RR / W
    )
    cp_min = float(np.min(cp_n[mask]))

    g_cp = max_rel <= GATE_CP_REL
    g_hs = max_hs <= GATE_HS_ABS
    g_cont = cp_cont <= GATE_CP_CONT
    g_pos = cp_min > 0.0
    # Single-range H: require machine-precision identity on cp
    if single_h:
        g_cp = g_cp and max_rel < 1e-10
        g_hs = g_hs and max_hs < 1e-6

    return SpeciesFit(
        name=name,
        Tc=Tc,
        original_Trange=(th_orig.min_temp, Tmid0, th_orig.max_temp),
        extrapolated_high=extrapolated,
        single_range_h=single_h,
        max_rel_cp=max_rel,
        max_abs_hs=max_hs,
        cp_cont=cp_cont,
        cp_min=cp_min,
        gate_cp=g_cp,
        gate_hs=g_hs,
        gate_cont=g_cont,
        gate_pos=g_pos,
        pass_all=g_cp and g_hs and g_cont and g_pos,
    )


def refit_species(
    sp: ct.Species, Tc: float, n_grid: int = 400
) -> tuple[np.ndarray, np.ndarray, SpeciesFit]:
    th = sp.thermo
    assert isinstance(th, ct.NasaPoly2)
    W = sp.molecular_weight
    Tmid0, high0, low0 = orig_coeffs(th)
    single_h = abs(Tmid0 - th.max_temp) < 1e-6 and np.allclose(low0[:5], high0[:5])
    extrapolated = th.max_temp < THIGH_TGT - 1e-6

    if single_h:
        a_low = low0.copy()
        a_high = low0.copy()
        fit = evaluate_gates(
            sp.name,
            W,
            th,
            a_low,
            a_high,
            Tc,
            np.linspace(300.0, 3000.0, 100),
            extrapolated=False,
            single_h=True,
        )
        return a_low, a_high, fit

    # Already on target breakpoint: keep polys; only the shared window changes.
    # Gates vs original on [300,3000] are then exact (aside from Thigh clip).
    if abs(Tmid0 - Tc) < 0.5:
        a_low, a_high = low0.copy(), high0.copy()
        fit = evaluate_gates(
            sp.name,
            W,
            th,
            a_low,
            a_high,
            Tc,
            np.linspace(300.0, 3000.0, 250),
            extrapolated,
            single_h=False,
        )
        return a_low, a_high, fit

    # Dense grids — denser near Tc and near original Tmid (kink)
    def densify(Ta, Tb, n):
        u = np.linspace(0, 1, n)
        # cosine clustering at ends
        u = 0.5 * (1 - np.cos(np.pi * u))
        return Ta + (Tb - Ta) * u

    T_low = densify(TLOW_TGT, Tc, n_grid // 2)
    T_high = densify(Tc, THIGH_TGT, n_grid // 2)
    cpR_low = orig_cp_R(th, T_low)
    cpR_high = orig_cp_R(th, T_high)

    a_low, a_high = fit_cp_segments(T_low, cpR_low, T_high, cpR_high, Tc)
    h_ref = orig_h_RT(th, TREF)
    s_ref = orig_s_R(th, TREF)
    a_low, a_high = set_integration_constants(a_low, a_high, Tc, h_ref, s_ref)

    T_gate = np.linspace(300.0, 3000.0, 250)
    fit = evaluate_gates(
        sp.name, W, th, a_low, a_high, Tc, T_gate, extrapolated, single_h=False
    )
    # Retry with soft C1 + relative weights if hard-C1 miss gates (outlier Tmids)
    if not fit.pass_all:
        a2_l, a2_h = fit_cp_segments(
            T_low, cpR_low, T_high, cpR_high, Tc, soft_c1=True
        )
        a2_l, a2_h = set_integration_constants(a2_l, a2_h, Tc, h_ref, s_ref)
        fit2 = evaluate_gates(
            sp.name, W, th, a2_l, a2_h, Tc, T_gate, extrapolated, single_h=False
        )
        if fit2.max_rel_cp < fit.max_rel_cp and fit2.cp_cont <= GATE_CP_CONT:
            a_low, a_high, fit = a2_l, a2_h, fit2
    return a_low, a_high, fit


def build_solution(
    gas0: ct.Solution, fits_coeff: dict[str, tuple[np.ndarray, np.ndarray]], Tc: float
) -> ct.Solution:
    new_species = []
    for sp0 in gas0.species():
        a_low, a_high = fits_coeff[sp0.name]
        data = dict(sp0.input_data)
        data["thermo"] = {
            "model": "NASA7",
            "temperature-ranges": [TLOW_TGT, float(Tc), THIGH_TGT],
            "data": [a_low.tolist(), a_high.tolist()],
        }
        sp = ct.Species.from_dict(data)
        new_species.append(sp)
    return ct.Solution(
        thermo="ideal-gas",
        kinetics="gas",
        species=new_species,
        reactions=gas0.reactions(),
    )


def run_trade(yaml_path: Path, out_dir: Path) -> dict:
    gas0 = ct.Solution(str(yaml_path))
    trade = {}
    for Tc in (1000.0, 1400.0):
        coeffs = {}
        reports: list[SpeciesFit] = []
        for sp in gas0.species():
            a_low, a_high, fit = refit_species(sp, Tc)
            coeffs[sp.name] = (a_low, a_high)
            reports.append(fit)

        worst = max(reports, key=lambda r: r.max_rel_cp)
        n_fail = sum(1 for r in reports if not r.pass_all)
        trade[f"Tc_{int(Tc)}"] = dict(
            Tc=Tc,
            n_species=len(reports),
            n_fail=n_fail,
            worst_species=worst.name,
            worst_rel_cp=worst.max_rel_cp,
            worst_abs_hs=worst.max_abs_hs,
            all_pass=n_fail == 0,
            species=[asdict(r) for r in reports],
            coeffs={
                n: {"low": low.tolist(), "high": high.tolist()}
                for n, (low, high) in coeffs.items()
            },
        )
        print(
            f"Tc={Tc:g}: worst {worst.name} max|Δcp|/cp="
            f"{100*worst.max_rel_cp:.4f}%  fails={n_fail}/{len(reports)}"
        )

    # Select by worst-species cp error
    c1000 = trade["Tc_1000"]
    c1400 = trade["Tc_1400"]
    if c1000["worst_rel_cp"] <= c1400["worst_rel_cp"]:
        selected = "Tc_1000"
    else:
        selected = "Tc_1400"
    trade["selected"] = selected
    trade["selection_rule"] = "minimize worst-species max|Δcp|/cp on [300,3000]"
    print(f"SELECTED {selected} (worst_rel "
          f"{trade[selected]['worst_rel_cp']:.6e} vs alternative "
          f"{trade['Tc_1400' if selected=='Tc_1000' else 'Tc_1000']['worst_rel_cp']:.6e})")

    def _jsonable(obj):
        if isinstance(obj, dict):
            return {k: _jsonable(v) for k, v in obj.items() if k != "coeffs"}
        if isinstance(obj, list):
            return [_jsonable(v) for v in obj]
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        return obj

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "trade_study.json").write_text(
        json.dumps(_jsonable(trade), indent=2)
    )

    sel = trade[selected]
    Tc = sel["Tc"]
    coeffs = {
        n: (np.array(d["low"], dtype=float), np.array(d["high"], dtype=float))
        for n, d in sel["coeffs"].items()
    }

    gas_new = build_solution(gas0, coeffs, Tc)
    yaml_out = out_dir / f"n-dodecane_refit_Tc{int(Tc)}.yaml"
    gas_new.write_yaml(str(yaml_out))
    # Also write selected pointer
    shutil.copy(yaml_out, out_dir / "n-dodecane_refit.yaml")

    # Chemkin + therm_of via convert helpers
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from convert_mechanism import fix_chem_inp, write_therm_of, ensure_transport

    ck = out_dir / "chemkin"
    ck.mkdir(parents=True, exist_ok=True)
    gas_new.write_chemkin(
        mechanism_path=str(ck / "chem.inp"),
        thermo_path=str(ck / "therm.dat"),
        overwrite=True,
        quiet=True,
    )
    # Transport: copy from original conversion (species transport dropped in rebuild)
    src_tran = ROOT / "mechanisms" / "chemkin" / "tran.dat"
    if src_tran.is_file():
        shutil.copy(src_tran, ck / "tran.dat")
    fix_chem_inp(ck / "chem.inp")
    write_therm_of(gas_new, ck / "therm_of.dat")
    ensure_transport(ck)

    # Summary markdown
    lines = [
        f"# E11.1 thermo refit trade study\n\n",
        f"Source: `{yaml_path}`\n",
        f"Target window: **[{TLOW_TGT:g}, Tc, {THIGH_TGT:g}]** K\n",
        f"Selected: **{selected}** (Tc={Tc:g} K)\n\n",
        "## Trade\n\n",
        "| Tc | worst species | max\\|Δcp\\|/cp | max\\|Δhs\\| [kJ/kg] | fails |\n",
        "|---:|---------------|---------------:|-------------------:|------:|\n",
    ]
    for key in ("Tc_1000", "Tc_1400"):
        t = trade[key]
        mark = " ← selected" if key == selected else ""
        lines.append(
            f"| {t['Tc']:g} | {t['worst_species']} | "
            f"{100*t['worst_rel_cp']:.4f}% | {t['worst_abs_hs']/1000:.4f} | "
            f"{t['n_fail']}/{t['n_species']}{mark} |\n"
        )
    lines.append("\n## Notes\n\n")
    lines.append(
        "- `ch3o` original Thigh=3000 K: high-range NASA poly **extrapolated** to "
        f"{THIGH_TGT:g} K as cp targets above 3000 K; gate still applied on [300,3000].\n"
        "- `h` single-range (cp=5/2·R): both low/high identical; unit-tested to "
        "machine precision.\n"
        f"- Gates: max\\|Δcp\\|/cp≤{100*GATE_CP_REL}%, max\\|Δhs\\|≤{GATE_HS_ABS/1000} kJ/kg, "
        f"cp continuity≤{GATE_CP_CONT} J/(kg·K), cp>0.\n"
    )
    fails = [r for r in sel["species"] if not r["pass_all"]]
    if fails:
        lines.append("\n## Gate failures\n\n")
        for r in sorted(fails, key=lambda x: -x["max_rel_cp"])[:20]:
            lines.append(
                f"- {r['name']}: rel_cp={100*r['max_rel_cp']:.4f}% "
                f"hs={r['max_abs_hs']/1000:.4f} kJ/kg cont={r['cp_cont']:.3e} "
                f"cp_min={r['cp_min']:.1f} "
                f"gates(cp/hs/cont/pos)="
                f"{r['gate_cp']}/{r['gate_hs']}/{r['gate_cont']}/{r['gate_pos']}\n"
            )
    else:
        lines.append("\nAll species passed gates.\n")

    (out_dir / "E11_1_SUMMARY.md").write_text("".join(lines))
    # Persist full trade with coeffs for reproducibility
    (out_dir / "trade_study_full.json").write_text(
        json.dumps(
            {
                "selected": selected,
                "Tc": Tc,
                "Tc_1000_worst": c1000["worst_rel_cp"],
                "Tc_1400_worst": c1400["worst_rel_cp"],
                "all_pass": sel["all_pass"],
                "n_fail": sel["n_fail"],
            },
            indent=2,
        )
    )
    print("".join(lines))
    return trade


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", type=Path, default=DEFAULT_YAML)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    trade = run_trade(args.yaml, args.out)
    sel = trade[trade["selected"]]
    return 0 if sel["all_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
