#!/usr/bin/env python3
"""Compare OpenFOAM rate dump JSON against Cantera oracle on the same states."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MECH = ROOT / "mechanisms" / "n-dodecane.yaml"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--of-json", type=Path, required=True, help="OF dump with net/qf/qr")
    ap.add_argument("--mech", type=Path, default=MECH)
    ap.add_argument("--tol", type=float, default=1e-3)
    args = ap.parse_args()

    import cantera as ct

    data = json.loads(args.of_json.read_text())
    gas = ct.Solution(str(args.mech))
    max_err = 0.0
    bad = 0
    for st in data.get("states", data if isinstance(data, list) else []):
        T, P, Y = st["T"], st["P"], np.array(st["Y"])
        gas.TPY = T, P, Y
        ct_net = gas.net_production_rates
        of_net = np.array(st["of_net"])
        # Align species if needed by name
        err = np.abs(of_net - ct_net) / (np.maximum(np.abs(ct_net), 1e-30))
        mask = np.abs(ct_net) > 1e-12
        if mask.any():
            m = float(err[mask].max())
            max_err = max(max_err, m)
            if m > args.tol:
                bad += 1
    ok = max_err <= args.tol
    print(f"max_rel_err={max_err:.3e} bad_states={bad} PASS={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
