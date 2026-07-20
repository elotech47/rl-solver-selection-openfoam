#!/usr/bin/env python3
"""E17 preflight: C2 MidT OF modes vs frozen E16.4 table (x86_64 sanity)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNS = ROOT / "validation/e16_parity/e16_4_runs"

FROZEN = {
    "cvodeOnly": {"tau_ms": 2.281, "T_final": 2607.2},
    "qssOnly": {"tau_ms": 2.436, "T_final": 2587.8},
    "rlAdaptive": {"tau_ms": 2.429, "T_final": 2589.8},
}


def ignition_delay_ms(out: Path) -> float | None:
    chem = out / "chemFoam.out"
    if not chem.is_file():
        return None
    t, T = [], []
    for line in chem.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                t.append(float(parts[0]))
                T.append(float(parts[1]))
            except ValueError:
                continue
    if len(t) < 2:
        return None
    dT = [(T[i + 1] - T[i]) / max(t[i + 1] - t[i], 1e-30) for i in range(len(t) - 1)]
    idx = max(range(len(dT)), key=lambda i: dT[i])
    return t[idx] * 1000.0


def final_T(out: Path) -> float | None:
    chem = out / "chemFoam.out"
    if chem.is_file():
        lines = [ln for ln in chem.read_text().splitlines() if ln.strip()]
        if lines:
            parts = lines[-1].split()
            if len(parts) >= 2:
                try:
                    return float(parts[1])
                except ValueError:
                    pass
    tf = out / "fields" / "T"
    if tf.is_file():
        m = re.search(r"internalField\s+uniform\s+([^\s;]+)", tf.read_text())
        if m:
            return float(m.group(1))
    return None


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "validation/zeroD/e17_remote_runs/preflight_latest"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    ok = True
    for mode, ref in FROZEN.items():
        run = RUNS / f"C2_{mode}"
        tau = ignition_delay_ms(run)
        tf = final_T(run)
        tau_pct = None if tau is None else 100.0 * (tau - ref["tau_ms"]) / ref["tau_ms"]
        dT = None if tf is None else tf - ref["T_final"]
        pass_tau = tau_pct is not None and (
            (mode == "cvodeOnly" and abs(tau_pct) <= 0.1)
            or (mode == "qssOnly" and abs(tau_pct) <= 5.0)
            or (mode == "rlAdaptive" and abs(tau_pct) <= 10.0)
        )
        pass_tf = dT is not None and abs(dT) <= 50.0
        row = {
            "mode": mode,
            "tau_ms": tau,
            "tau_ref_ms": ref["tau_ms"],
            "tau_pct_vs_frozen": tau_pct,
            "T_final": tf,
            "T_ref": ref["T_final"],
            "dT_vs_frozen": dT,
            "PASS_tau": pass_tau,
            "PASS_T": pass_tf,
        }
        rows.append(row)
        if not (pass_tau and pass_tf):
            ok = False
    summary = {"PASS": ok, "rows": rows}
    (out_dir / "preflight_c2_check.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
