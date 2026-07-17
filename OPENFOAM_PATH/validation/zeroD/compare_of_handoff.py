#!/usr/bin/env python3
"""Compare chemFoam MidT_MidP ignition delay vs handoff (Python) refs.

Ignition: first time T >= T0 + dT (default dT=400 K), matching run_zeroD_refs.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_chemfoam_out(path: Path):
    t, T, p = [], [], []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            t.append(float(parts[0]))
            T.append(float(parts[1]))
            p.append(float(parts[2]))
    return t, T, p


def ignition_delay(t, T, T0: float, dT: float = 400.0):
    target = T0 + dT
    for ti, Ti in zip(t, T):
        if Ti >= target:
            return float(ti)
    return float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", type=Path, required=True)
    ap.add_argument("--cvode-out", type=Path, required=True)
    ap.add_argument("--qss-out", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--T0", type=float, default=800.0)
    ap.add_argument("--dT", type=float, default=400.0)
    ap.add_argument("--tol", type=float, default=0.01, help="relative tol gate (default 1%)")
    args = ap.parse_args()

    refs = json.loads(args.refs.read_text())
    # Support either single-IC object or list from run_zeroD_refs
    if isinstance(refs, list):
        mid = next(r for r in refs if r.get("ic", {}).get("label") == "MidT_MidP")
    else:
        mid = refs

    rows = []
    for name, out_path, ref_key in (
        ("cvode", args.cvode_out, "cvode"),
        ("qss", args.qss_out, "qss"),
    ):
        t, T, p = load_chemfoam_out(out_path)
        ign = ignition_delay(t, T, args.T0, args.dT)
        ref_ign = float(mid[ref_key]["ign"])
        rel = abs(ign - ref_ign) / abs(ref_ign) if ref_ign else float("nan")
        row = {
            "solver": name,
            "of_ign_s": ign,
            "handoff_ign_s": ref_ign,
            "rel_err": rel,
            "pass_1pct": bool(rel <= args.tol),
            "T0": args.T0,
            "T_end": T[-1] if T else float("nan"),
            "p0": p[0] if p else float("nan"),
            "n_samples": len(t),
            "of_out": str(out_path),
        }
        rows.append(row)
        print(
            f"{name:5s}  OF ign={ign:.6e}s  handoff={ref_ign:.6e}s  "
            f"rel={rel*100:.3f}%  {'PASS' if row['pass_1pct'] else 'FAIL'}"
        )

    report = {
        "ic": mid.get("ic", {"label": "MidT_MidP", "T": args.T0}),
        "tol": args.tol,
        "results": rows,
        "all_pass": all(r["pass_1pct"] for r in rows),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {args.report}")
    print(f"all_pass={report['all_pass']}")
    return 0 if report["all_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
