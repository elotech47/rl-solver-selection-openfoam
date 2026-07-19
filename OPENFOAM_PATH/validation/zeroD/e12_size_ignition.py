#!/usr/bin/env python3
"""E12.1-redo — Cantera-size opposed-jet air temperature for τ_ign ≈ 1–2 ms.

At 10 atm, scan Z ∈ [0.03, 0.10] and T_air to find mixture ignition delays.
Expect T_air ~ 1250–1300 K for τ ~ 1–2 ms on Luo/refit n-dodecane.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
OUT = ROOT / "validation/zeroD/e12_size"
P = 10.0 * 101325.0
T_FUEL = 300.0
TARGET_TAU = (1e-3, 2e-3)


def ign_delay(gas, T, P, X, n_steps=400):
    import cantera as ct

    gas.TPX = T, P, X
    r = ct.IdealGasConstPressureReactor(gas)
    sim = ct.ReactorNet([r])
    t_end = 0.05
    times = np.linspace(0, t_end, n_steps)
    T0 = T
    for t in times:
        sim.advance(t)
        if r.T > T0 + 400:
            # refine
            return float(t)
    return float("nan")


def mix_X(gas, Z, T_air):
    """Fuel nc12h26 at 300 K vs air at T_air; mix at Z (fuel mass fraction)."""
    import cantera as ct

    i_fuel = gas.species_index("n-C12H26") if "n-C12H26" in gas.species_names else gas.species_index("nc12h26")
    fuel_name = gas.species_name(i_fuel)
    gas.TPX = T_FUEL, P, {fuel_name: 1.0}
    Yf = gas.Y.copy()
    hf = gas.enthalpy_mass
    gas.TPX = T_air, P, {"O2": 0.21, "N2": 0.79}
    Ya = gas.Y.copy()
    ha = gas.enthalpy_mass
    Y = Z * Yf + (1 - Z) * Ya
    h = Z * hf + (1 - Z) * ha
    gas.HPY = h, P, Y
    return gas.T, gas.X


def main() -> int:
    import cantera as ct

    OUT.mkdir(parents=True, exist_ok=True)
    gas = ct.Solution(str(YAML))
    Zs = np.linspace(0.03, 0.10, 8)
    T_airs = np.arange(1200.0, 1400.0, 25.0)
    table = []
    best = None
    for T_air in T_airs:
        for Z in Zs:
            Tmix, X = mix_X(gas, float(Z), float(T_air))
            tau = ign_delay(gas, Tmix, P, X)
            row = dict(T_air=float(T_air), Z=float(Z), Tmix=float(Tmix), tau_s=tau)
            table.append(row)
            print(f"T_air={T_air:.0f} Z={Z:.3f} Tmix={Tmix:.1f} tau={tau*1e3:.3f} ms")
            if np.isfinite(tau) and TARGET_TAU[0] <= tau <= TARGET_TAU[1]:
                if best is None or abs(tau - 1.5e-3) < abs(best["tau_s"] - 1.5e-3):
                    best = row

    # If none in band, pick closest to 1.5 ms with tau>0
    if best is None:
        finite = [r for r in table if np.isfinite(r["tau_s"]) and r["tau_s"] > 0]
        if finite:
            best = min(finite, key=lambda r: abs(r["tau_s"] - 1.5e-3))

    report = dict(
        campaign="E12.1-redo-size",
        P_Pa=P,
        target_tau_s=TARGET_TAU,
        best=best,
        table=table,
    )
    (OUT / "e12_size_ignition.json").write_text(json.dumps(report, indent=2))
    print("BEST:", best)
    print("Wrote", OUT / "e12_size_ignition.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
