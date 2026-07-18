#!/usr/bin/env python3
"""E11.1 add-ons before Option R ship:
  (1) Equilibrium-invariance: original vs refit HP equilibrate on Z×p grid
  (2) Effect-size of the 4 gate-miss species along MidT trajectory
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cantera as ct
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RR = 8314.462618
MISS = ("c8h17coch2", "c3h4-a", "oh", "c2h6")
MAJOR = ("n2", "co2", "h2o", "co", "o2", "h2", "oh")  # burnt majors + OH


def air_fuel_Y(gas: ct.Solution, Z: float) -> np.ndarray:
    names = {n.lower(): n for n in gas.species_names}
    y = np.zeros(gas.n_species)
    y[gas.species_index(names["o2"])] = (1.0 - Z) * 0.233
    y[gas.species_index(names["n2"])] = (1.0 - Z) * 0.767
    y[gas.species_index(names["nc12h26"])] = Z
    y /= y.sum()
    return y


def midt_moles(gas: ct.Solution) -> dict:
    names = {n.lower(): n for n in gas.species_names}
    return {
        names["o2"]: 0.20775813522367179,
        names["n2"]: 0.7811705884410058,
        names["nc12h26"]: 0.01107127633532227,
    }


def equilibrium_invariance(yaml0: Path, yaml1: Path) -> dict:
    g0 = ct.Solution(str(yaml0))
    g1 = ct.Solution(str(yaml1))
    Zs = np.linspace(0.02, 0.12, 6)  # inclusive endpoints + interior
    ps = (10.0, 30.0, 60.0)
    rows = []
    max_dT = 0.0
    max_dY = 0.0
    worst = None
    for Z in Zs:
        for p_atm in ps:
            P = p_atm * ct.one_atm
            Y = air_fuel_Y(g0, float(Z))
            g0.TPY = 800.0, P, Y
            g1.TPY = 800.0, P, Y
            g0.equilibrate("HP")
            g1.equilibrate("HP")
            dT = float(g1.T - g0.T)
            dY_major = {}
            dY_max = 0.0
            for sp in MAJOR:
                names0 = {n.lower(): n for n in g0.species_names}
                if sp not in names0:
                    continue
                i0 = g0.species_index(names0[sp])
                i1 = g1.species_index(names0[sp])
                dy = float(g1.Y[i1] - g0.Y[i0])
                dY_major[sp] = dy
                dY_max = max(dY_max, abs(dy))
            rows.append(
                dict(
                    Z=float(Z),
                    p_atm=p_atm,
                    T0=float(g0.T),
                    T1=float(g1.T),
                    dT=dT,
                    dY_major=dY_major,
                    max_abs_dY=dY_max,
                )
            )
            if abs(dT) > abs(max_dT):
                max_dT = dT
            if dY_max > max_dY:
                max_dY = dY_max
                worst = dict(Z=float(Z), p_atm=p_atm, dT=dT, dY_major=dY_major)

    gate_T = abs(max_dT) <= 1.0
    gate_Y = max_dY <= 1e-5
    return dict(
        rows=rows,
        max_abs_dT=abs(max_dT),
        max_abs_dY_major=max_dY,
        gate_T=gate_T,
        gate_Y=gate_Y,
        pass_all=gate_T and gate_Y,
        worst=worst,
    )


def nasa7_cp_mass(a, W, T):
    return (a[0] + a[1] * T + a[2] * T**2 + a[3] * T**3 + a[4] * T**4) * RR / W


def nasa7_hs_mass(a, a_low, W, T, Tref=298.15):
    def hRT(aa, TT):
        return (
            aa[0]
            + aa[1] * TT / 2
            + aa[2] * TT**2 / 3
            + aa[3] * TT**3 / 4
            + aa[4] * TT**4 / 5
            + aa[5] / TT
        )

    return (hRT(a, T) * RR * T - hRT(a_low, Tref) * RR * Tref) / W


def species_coeffs(gas: ct.Solution, name: str):
    sp = gas.species(name)
    th = sp.thermo
    c = th.coeffs
    Tmid = float(c[0])
    high = np.array(c[1:8])
    low = np.array(c[8:15])
    return sp.molecular_weight, Tmid, low, high


def pick(Tmid, low, high, T):
    return low if T < Tmid else high


def effect_size_table(yaml0: Path, yaml1: Path) -> dict:
    """Peak Yi along MidT × per-species property error → mixture contribution."""
    g0 = ct.Solution(str(yaml0))
    g1 = ct.Solution(str(yaml1))
    g0.TPX = 800.0, 10 * ct.one_atm, midt_moles(g0)
    r = ct.IdealGasConstPressureReactor(g0)
    sim = ct.ReactorNet([r])

    names = {n.lower(): i for i, n in enumerate(g0.species_names)}
    peak_Y = {sp: 0.0 for sp in MISS}
    # Also sample property error on a T grid using fixed peak-time states later
    traj_T = []
    traj_Y = {sp: [] for sp in MISS}
    t_end = 3.5e-3
    while sim.time < t_end:
        sim.step()
        traj_T.append(float(r.T))
        for sp in MISS:
            yi = float(r.thermo.Y[names[sp]])
            traj_Y[sp].append(yi)
            peak_Y[sp] = max(peak_Y[sp], yi)

    # Property errors vs T on dense grid (species-local, independent of Y)
    T_grid = np.linspace(300.0, 3000.0, 271)
    rows = []
    for sp in MISS:
        W0, Tm0, low0, high0 = species_coeffs(g0, sp)
        W1, Tm1, low1, high1 = species_coeffs(g1, sp)
        assert abs(W0 - W1) < 1e-9
        max_rel_cp = 0.0
        max_abs_hs = 0.0
        max_contrib_cp = 0.0
        max_contrib_hs = 0.0
        # At each traj point: contribution = Yi * Δprop / mix_prop
        # Approximate mix cp ~ 1400 J/kg/K, mix hs scale ~ 1e6 J/kg near burnt
        for T, Yi in zip(traj_T, traj_Y[sp]):
            a0 = pick(Tm0, low0, high0, T)
            a1 = pick(Tm1, low1, high1, T)
            cp0 = nasa7_cp_mass(a0, W0, T)
            cp1 = nasa7_cp_mass(a1, W1, T)
            hs0 = nasa7_hs_mass(a0, low0, W0, T)
            hs1 = nasa7_hs_mass(a1, low1, W1, T)
            dcp = cp1 - cp0
            dhs = hs1 - hs0
            rel_cp = abs(dcp) / max(abs(cp0), 1e-12)
            max_rel_cp = max(max_rel_cp, rel_cp)
            max_abs_hs = max(max_abs_hs, abs(dhs))
            # Mixture-relative contribution using instantaneous mix cp/hs from reactor
            # (recompute cheaply from stored T only — use nominal scales + Yi*dprop)
            # Better: use Yi*|dcp| / cp_mix_nom with cp_mix from typical 1300-1500
            cp_mix_nom = 1400.0
            hs_mix_nom = max(abs(hs0), 1e5)  # avoid tiny early-time hs
            max_contrib_cp = max(max_contrib_cp, abs(Yi * dcp) / cp_mix_nom)
            max_contrib_hs = max(max_contrib_hs, abs(Yi * dhs) / hs_mix_nom)

        # Also report at peak-Y temperature
        i_peak = int(np.argmax(traj_Y[sp]))
        T_peak = traj_T[i_peak]
        a0 = pick(Tm0, low0, high0, T_peak)
        a1 = pick(Tm1, low1, high1, T_peak)
        dcp_pk = nasa7_cp_mass(a1, W1, T_peak) - nasa7_cp_mass(a0, W0, T_peak)
        dhs_pk = nasa7_hs_mass(a1, low1, W1, T_peak) - nasa7_hs_mass(
            a0, low0, W0, T_peak
        )
        rows.append(
            dict(
                species=sp,
                peak_Y=peak_Y[sp],
                T_at_peak_Y=T_peak,
                max_rel_cp_species=max_rel_cp,
                max_abs_hs_species=max_abs_hs,
                dcp_at_peakY=dcp_pk,
                dhs_at_peakY=dhs_pk,
                max_mix_rel_cp_contrib=max_contrib_cp,
                max_mix_rel_hs_contrib=max_contrib_hs,
                gate_contrib_le_1e_4=max(max_contrib_cp, max_contrib_hs) <= 1e-4,
            )
        )

    return dict(
        rows=rows,
        pass_all=all(r["gate_contrib_le_1e_4"] for r in rows),
        expected_max_contrib=1e-4,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", type=Path, default=ROOT / "mechanisms/n-dodecane.yaml")
    ap.add_argument(
        "--refit", type=Path, default=ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
    )
    ap.add_argument(
        "--out", type=Path, default=ROOT / "mechanisms/refit/e11_1_addons"
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    print("=== Equilibrium invariance ===")
    eq = equilibrium_invariance(args.orig, args.refit)
    print(
        f"max|ΔT|={eq['max_abs_dT']:.4f} K  gate≤1K: {eq['gate_T']}\n"
        f"max|ΔY_major|={eq['max_abs_dY_major']:.3e}  gate≤1e-5: {eq['gate_Y']}"
    )

    print("=== Effect-size (4 miss species) ===")
    eff = effect_size_table(args.orig, args.refit)
    for r in eff["rows"]:
        print(
            f"  {r['species']}: peakY={r['peak_Y']:.3e}  "
            f"mix_rel_cp≤{r['max_mix_rel_cp_contrib']:.3e}  "
            f"mix_rel_hs≤{r['max_mix_rel_hs_contrib']:.3e}  "
            f"gate={r['gate_contrib_le_1e_4']}"
        )

    report = dict(equilibrium=eq, effect_size=eff)
    # JSON-safe
    def js(o):
        if isinstance(o, dict):
            return {k: js(v) for k, v in o.items()}
        if isinstance(o, list):
            return [js(v) for v in o]
        if isinstance(o, (np.floating, float)):
            return float(o)
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        if isinstance(o, (np.integer, int)):
            return int(o)
        return o

    (args.out / "summary.json").write_text(json.dumps(js(report), indent=2))

    lines = [
        "# E11.1 add-ons — equilibrium invariance & effect-size\n\n",
        "## (1) Equilibrium invariance (HP, Z∈[0.02,0.12] × p∈{10,30,60} atm)\n\n",
        f"- max\\|ΔT_equil\\| = **{eq['max_abs_dT']:.4f} K** "
        f"(gate ≤1 K: **{'PASS' if eq['gate_T'] else 'FAIL'}**)\n",
        f"- max\\|ΔY_major\\| = **{eq['max_abs_dY_major']:.3e}** "
        f"(gate ≤1e-5: **{'PASS' if eq['gate_Y'] else 'FAIL'}**)\n\n",
        "| Z | p [atm] | T_orig [K] | T_refit [K] | ΔT [K] | max\\|ΔY\\| |\n",
        "|--:|--------:|-----------:|------------:|-------:|---------:|\n",
    ]
    for r in eq["rows"]:
        lines.append(
            f"| {r['Z']:.3f} | {r['p_atm']:g} | {r['T0']:.2f} | {r['T1']:.2f} | "
            f"{r['dT']:+.4f} | {r['max_abs_dY']:.2e} |\n"
        )

    lines += [
        "\n## (2) Effect-size — 4 strict-gate misses\n\n",
        "Peak Yi along MidT (800 K, 10 atm) × species property error → "
        "nominal mixture-relative contribution (cp_mix≈1400 J/kg/K).\n"
        f"Expected ≤ **{eff['expected_max_contrib']:.0e}**. "
        f"Overall: **{'PASS' if eff['pass_all'] else 'FAIL'}**\n\n",
        "| species | peak Y | T@peak | max\\|Δcp\\|/cp | max\\|Δhs\\| [kJ/kg] | "
        "max mix-rel cp | max mix-rel hs | ≤1e-4 |\n",
        "|---------|-------:|-------:|---------------:|-------------------:|"
        "---------------:|---------------:|:-----:|\n",
    ]
    for r in eff["rows"]:
        lines.append(
            f"| {r['species']} | {r['peak_Y']:.3e} | {r['T_at_peak_Y']:.0f} | "
            f"{100*r['max_rel_cp_species']:.3f}% | {r['max_abs_hs_species']/1000:.3f} | "
            f"{r['max_mix_rel_cp_contrib']:.2e} | {r['max_mix_rel_hs_contrib']:.2e} | "
            f"{'Y' if r['gate_contrib_le_1e_4'] else 'N'} |\n"
        )

    (args.out / "SUMMARY.md").write_text("".join(lines))
    print("".join(lines))
    ok = eq["pass_all"] and eff["pass_all"]
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
