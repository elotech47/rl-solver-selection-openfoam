#!/usr/bin/env python3
"""Preprocess an E17 remote run directory into ignition gate + T(t) plot + report."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--t-air", type=float, default=1350.0)
    ap.add_argument("--t-kernel", type=float, default=1300.0)
    ap.add_argument("--ignite-T", type=float, default=1600.0, help="internal T gate for ignition")
    args = ap.parse_args()
    run = args.run_dir
    out = args.out_dir or (run / "preprocess")
    out.mkdir(parents=True, exist_ok=True)

    summary_path = run / "extract" / "summary.json"
    if not summary_path.is_file():
        # try to build minimal from log
        summary_path = run / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}

    # prefer extract summary fields
    tmax_int = summary.get("max_internal_T_propSanity")
    tmax_field = summary.get("max_field_Tmax")
    last_t = summary.get("last_Time")
    fatal = bool(summary.get("FOAM_FATAL"))
    ended = bool(summary.get("End"))
    wall = summary.get("wall_s")

    ignite = (
        (tmax_int is not None and tmax_int >= args.ignite_T)
        or (tmax_field is not None and tmax_field >= args.ignite_T)
    )
    # field max often equals T_air BC — require internal or field > max(T_air, T_kernel)+50
    bc_ref = max(args.t_air, args.t_kernel)
    strong = (
        (tmax_int is not None and tmax_int > bc_ref + 50)
        or (tmax_field is not None and tmax_field > bc_ref + 50)
    )
    gate = {
        "ignition_T_threshold_K": args.ignite_T,
        "T_air": args.t_air,
        "T_kernel": args.t_kernel,
        "max_internal_T": tmax_int,
        "max_field_T": tmax_field,
        "last_Time": last_t,
        "wall_s": wall,
        "FOAM_FATAL": fatal,
        "End": ended,
        "PASS_no_fatal": not fatal,
        "PASS_ignition": bool(ignite and strong and not fatal),
        "note": (
            "PASS_ignition requires no FATAL and T above threshold and above BC/kernel+50 K"
        ),
    }
    (out / "ignition_gate.json").write_text(json.dumps(gate, indent=2))

    # plot if matplotlib + csv available
    trace = run / "extract" / "T_trace.csv"
    try:
        import matplotlib.pyplot as plt
        import numpy as np

        times, fmax, pmax = [], [], []
        if trace.is_file():
            with trace.open() as f:
                r = csv.DictReader(f)
                for row in r:
                    if not row.get("time"):
                        continue
                    times.append(float(row["time"]))
                    fmax.append(float(row["field_Tmax"]) if row.get("field_Tmax") else np.nan)
                    pmax.append(float(row["prop_Tmax"]) if row.get("prop_Tmax") else np.nan)
        if times:
            fig, ax = plt.subplots(figsize=(7, 4))
            ax.plot(np.asarray(times) * 1e3, fmax, label="field max T")
            ax.plot(np.asarray(times) * 1e3, pmax, label="propSanity max T (internal)")
            ax.axhline(args.ignite_T, color="r", ls="--", label=f"gate {args.ignite_T:g} K")
            ax.axhline(args.t_air, color="gray", ls=":", label=f"T_air {args.t_air:g} K")
            ax.set_xlabel("t [ms]")
            ax.set_ylabel("T [K]")
            ax.set_title("E17 opposed-jet temperature trace")
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            fig.savefig(out / "T_vs_time.png", dpi=150)
            fig.savefig(out / "T_vs_time.pdf")
            plt.close(fig)
    except Exception as e:
        (out / "plot_error.txt").write_text(str(e))

    report = f"""# E17 preprocess report

**Run:** `{run}`

| Metric | Value |
|--------|------:|
| last Time [s] | {last_t} |
| wall [s] | {wall} |
| max field T [K] | {tmax_field} |
| max internal T [K] | {tmax_int} |
| FATAL | {fatal} |
| End | {ended} |
| **Ignition gate** | **{"PASS" if gate["PASS_ignition"] else "FAIL"}** |

See `ignition_gate.json` and `T_vs_time.png`.
"""
    (out / "report.md").write_text(report)
    print(report)
    print(json.dumps(gate, indent=2))


if __name__ == "__main__":
    main()
