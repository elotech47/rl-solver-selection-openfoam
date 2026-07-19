#!/usr/bin/env python3
"""E15 — Cantera pre-size T0×p×φ grid; skip τ_ign > 50 ms.

Grid (Campaign 4 reshape):
  T0 ∈ {600,700,800,900,1000} K
  p  ∈ {1,10,30,60} atm
  φ  ∈ {0.5, 1.0, 1.5}  (fuel/air; nc12h26 / air)

Writes e15_presize.json used by the signature-map runner.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
OUT = ROOT / "validation/zeroD/e15_conformance"
T0S = [600.0, 700.0, 800.0, 900.0, 1000.0]
PS_ATM = [1.0, 10.0, 30.0, 60.0]
PHIS = [0.5, 1.0, 1.5]
TAU_SKIP = 50e-3  # s


def phi_to_Z(gas, phi: float) -> float:
    """Mixture fraction for C12H26 + air at equivalence ratio phi."""
    # Stoich: C12H26 + 18.5 O2 → ... ; air O2:N2 = 1:3.76
    # fuel mass fraction Z for phi
    gas.set_equivalence_ratio(phi, "nc12h26:1.0", "o2:1.0, n2:3.76")
    # Cantera mixture fraction with fuel/oxidizer streams
    return float(
        gas.mixture_fraction("nc12h26:1.0", "o2:1.0, n2:3.76", element="C")
    )


def ign_delay(gas, T, P, phi, t_end=0.1, dT=400.0) -> float:
    import cantera as ct

    gas.set_equivalence_ratio(phi, "nc12h26:1.0", "o2:1.0, n2:3.76")
    gas.TP = T, P
    r = ct.IdealGasConstPressureReactor(gas)
    sim = ct.ReactorNet([r])
    sim.rtol, sim.atol = 1e-8, 1e-12
    T0 = T
    try:
        while sim.time < t_end:
            sim.advance(min(sim.time + 1e-5, t_end))
            if r.T >= T0 + dT:
                return float(sim.time)
    except Exception:
        return float("nan")
    return float("nan")


def main() -> int:
    import cantera as ct

    OUT.mkdir(parents=True, exist_ok=True)
    gas = ct.Solution(str(YAML))
    rows = []
    for T0 in T0S:
        for p_atm in PS_ATM:
            for phi in PHIS:
                P = p_atm * ct.one_atm
                Z = phi_to_Z(gas, phi)
                tau = ign_delay(gas, T0, P, phi)
                skip = (not np.isfinite(tau)) or (tau > TAU_SKIP)
                row = dict(
                    T0=T0,
                    p_atm=p_atm,
                    phi=phi,
                    Z=Z,
                    tau_s=None if not np.isfinite(tau) else float(tau),
                    skip=bool(skip),
                    skip_reason=(
                        "no_ignition_in_0.1s"
                        if not np.isfinite(tau)
                        else ("tau_gt_50ms" if tau > TAU_SKIP else None)
                    ),
                )
                rows.append(row)
                status = "SKIP" if skip else "RUN"
                tau_ms = tau * 1e3 if np.isfinite(tau) else float("nan")
                print(
                    f"{status} T={T0:.0f} p={p_atm:.0f} φ={phi:.1f} "
                    f"Z={Z:.4f} τ={tau_ms:.2f} ms"
                )

    n_run = sum(1 for r in rows if not r["skip"])
    report = dict(
        campaign="E15_presize",
        tau_skip_s=TAU_SKIP,
        n_total=len(rows),
        n_run=n_run,
        n_skip=len(rows) - n_run,
        rows=rows,
    )
    (OUT / "e15_presize.json").write_text(json.dumps(report, indent=2))
    print(f"\nRUN {n_run}/{len(rows)} → {OUT/'e15_presize.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
