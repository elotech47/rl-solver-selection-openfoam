#!/usr/bin/env python3
"""Unit test: CHEMEQ2 integrated time equals Δt_chem (ground rule 4)."""
from __future__ import annotations

import sys


def main() -> int:
    try:
        from solver_selection_handoff.utils import create_qss_solver
        import cantera as ct
        import numpy as np
    except ImportError as e:
        print(f"SKIP: {e}")
        return 0

    mech = (
        __file__.replace("tests/test_qss_time.py", "mechanisms/n-dodecane.yaml")
    )
    from pathlib import Path

    mech = Path(__file__).resolve().parents[1] / "mechanisms" / "n-dodecane.yaml"
    gas = ct.Solution(str(mech))
    gas.set_mixture_fraction(0.062, "nc12h26:1.0", "o2:1.0, n2:3.76")
    gas.TP = 800.0, 10 * ct.one_atm
    integ = create_qss_solver(
        gas,
        gas.P,
        dict(epsmin=0.02, epsmax=100, dtmin=1e-12, dtmax=1e-6, itermax=2, abstol=1e-11),
    )
    dt = 1e-6
    y = np.concatenate([[gas.T], gas.Y]).tolist()
    integ.setState(y, 0.0)
    ret = integ.integrateToTime(dt)
    assert ret == 0 or ret is None or ret == 0
    t_attr = float(integ.tn)
    err = abs(t_attr - dt)
    print(f"integrated_time={t_attr} requested={dt} abs_err={err}")
    assert err <= 1e-12 * max(dt, 1.0) or err < 1e-14
    assert np.all(np.isfinite(np.asarray(integ.y)))
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
