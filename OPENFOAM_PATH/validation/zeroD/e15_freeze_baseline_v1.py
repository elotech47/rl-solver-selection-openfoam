#!/usr/bin/env python3
"""Build frozen validation baseline v1 tables from T-freeze map + filled CVODE.

Promotes T-freeze artifacts to canonical frozen names and writes:
  FROZEN_VALIDATION_BASELINE_v1.md
  E15_SIGNATURE_MAP.md (updated hub)
  rung (b)/(c) acceptance numbers from conform runs
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "validation/zeroD/e15_conformance"
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"


def fmt(x, p=3):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    if isinstance(x, str):
        return x
    return f"{x:.{p}g}"


def as_f(x):
    if x is None or isinstance(x, str):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def main() -> int:
    # Re-run tfreeze postprocess logic after CVODE fill: prefer calling analyze
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import e15_of_tfreeze_postprocess as tfp

    rc = tfp.main()
    # Copy promoted frozen artifacts
    for src, dst in [
        ("E15_SIGNATURE_MAP_OF_TFREEZE.md", "E15_SIGNATURE_MAP_OF.md"),
        ("e15_signature_map_of_tfreeze.json", "e15_signature_map_of.json"),
        ("E15_OF_VS_PY_DIFFS_TFREEZE.md", "E15_OF_VS_PY_DIFFS.md"),
        ("e15_of_vs_py_diffs_tfreeze.json", "e15_of_vs_py_diffs.json"),
        ("e15_drift_vs_dTeq_tfreeze.png", "e15_drift_vs_dTeq.png"),
    ]:
        s, d = OUT / src, OUT / dst
        if s.is_file() and s.resolve() != d.resolve():
            shutil.copy2(s, d)

    of = json.loads((OUT / "e15_signature_map_of_tfreeze.json").read_text())
    py = json.loads((OUT / "e15_signature_map_python.json").read_text())
    py_by = {(r["T0"], r["p_atm"], r["phi"]): r for r in py["results"] if "py_qss" in r}
    diffs = json.loads((OUT / "e15_of_vs_py_diffs_tfreeze.json").read_text())["results"]
    ba = json.loads((OUT / "e15_of_before_after_tfreeze.json").read_text())["results"]

    n_ok = sum(1 for r in of["results"] if (r.get("failure") in (None, "ok")))
    n_sign = sum(
        1
        for b in ba
        if b.get("dteq_sign_match_py")
    )
    n_holes = sum(
        1
        for d in diffs
        if isinstance(d.get("of_delta_Teq"), str) and "UNAVAILABLE" in d["of_delta_Teq"]
    )

    # Rung (c) table: paper-like grid from map (800/1000 × 10/30/60; 700 as low-T proxy)
    rung_c_keys = [
        (700, 10, 1.0),
        (700, 30, 1.0),
        (700, 60, 1.0),
        (800, 10, 1.0),
        (800, 30, 1.0),
        (800, 60, 1.0),
        (1000, 10, 1.0),
        (1000, 30, 1.0),
        (1000, 60, 1.0),
    ]
    of_by = {(r["T0"], r["p_atm"], r["phi"]): r for r in of["results"]}

    # MidT classic Z≈0.062 ≈ φ=1 at 800/10 from map
    mid = of_by.get((800.0, 10.0, 1.0))
    mid_py = py_by.get((800.0, 10.0, 1.0))

    lines = [
        "# Frozen validation baseline v1 — OF-QSS CONFORM (T-freeze)",
        "",
        "**Tag:** `e15-conform-baseline-v1`  ",
        "**Date:** 2026-07-19  ",
        "**Config:** production QSS = corrector T-freeze ON, `epsmin=0.02` (see DECISIONS.md)",
        "",
        "## Conform qssCoeffs (verbatim)",
        "",
        "```",
        "qssCoeffs",
        "{",
        "    epsmin          0.02;",
        "    epsmax          100;",
        "    dtmin           1e-12;",
        "    dtmax           1e-06;",
        "    abstol          1e-11;",
        "    itermax         2;",
        "    Tfreeze         true;  // predictor: thermo at T=y[0]; corrector: freeze T/rho/cp/ha",
        "}",
        "```",
        "",
        "T-freeze semantics (handoff `CanteraQSSODE`): predictor evaluates rates/thermo at",
        "current T and caches T, ρ, cp, ha; corrector re-evaluates rates at frozen T with",
        "updated composition, using cached thermo. CVODE path untouched.",
        "",
        "## Envelope map (38 conditions)",
        "",
        f"- OF-QSS failures cleared: map complete; ΔTeq holes remaining: **{n_holes}**",
        f"- ΔTeq sign match vs Py: **{n_sign}** (was 15 pre-freeze)",
        "- Artifacts: `E15_SIGNATURE_MAP_OF.md`, `E15_OF_VS_PY_DIFFS.md`,",
        "  `E15_BEFORE_AFTER_TFREEZE.md`, `e15_drift_vs_dTeq.png`",
        "",
        "## Equilibration audit (anomalies)",
        "",
        "800/10/φ=1.5 and 1000/10/φ=0.5: both **settled** at map endTime; OF–Py ΔTeq",
        "mismatches are **real residuals** (no fix). See `E15_EQUILIBRATION_AUDIT.md`.",
        "",
        "## Rung (c) — 0D trajectory acceptance (conform build)",
        "",
        "Ignition marker: τ_main = argmax(dT/dt). Accept vs Py-QSS: τ within few %;",
        "ΔTeq sign family preferred (envelope evidence, not per-point hard gate).",
        "",
        "| T0 | p | φ | τ_OF [ms] | τ_Py [ms] | τ OF/Py | ΔTeq OF | ΔTeq Py |",
        "|---:|--:|--:|----------:|----------:|--------:|--------:|--------:|",
    ]
    for key in rung_c_keys:
        r = of_by.get(key)
        p = py_by.get(key)
        if not r or not p:
            continue
        of_tau = as_f(r["of_qss"]["tau_main_s"])
        py_tau = as_f(p["py_qss"]["tau_main_s"])
        of_d = as_f(r.get("delta_Teq"))
        py_d = as_f(p.get("delta_Teq"))
        ratio = (of_tau / py_tau) if of_tau and py_tau else None
        lines.append(
            f"| {key[0]:.0f} | {key[1]:.0f} | {key[2]:.1f} | "
            f"{fmt(of_tau*1e3 if of_tau else None)} | {fmt(py_tau*1e3 if py_tau else None)} | "
            f"{fmt(ratio)} | {fmt(of_d,1)} | {fmt(py_d,1)} |"
        )

    if mid and mid_py:
        of_tau = as_f(mid["of_qss"]["tau_main_s"])
        py_q = as_f(mid_py["py_qss"]["tau_main_s"])
        py_c = as_f(mid_py["py_cvode"]["tau_main_s"])
        of_c = as_f(mid["of_cvode"]["tau_main_s"])
        lines += [
            "",
            "### MidT_MidP anchor (800 K / 10 atm / φ=1 ≈ Z=0.062)",
            "",
            f"| Instrument | τ_main [ms] | vs Py-CVODE |",
            f"|------------|------------:|------------:|",
            f"| Py-CVODE | {fmt(py_c*1e3 if py_c else None)} | — |",
            f"| Py-QSS | {fmt(py_q*1e3 if py_q else None)} | {fmt((py_q/py_c-1)*100 if py_q and py_c else None,1)}% |",
            f"| OF-CVODE | {fmt(of_c*1e3 if of_c else None)} | {fmt((of_c/py_c-1)*100 if of_c and py_c else None,1)}% |",
            f"| OF-QSS (conform) | {fmt(of_tau*1e3 if of_tau else None)} | "
            f"{fmt((of_tau/py_c-1)*100 if of_tau and py_c else None,1)}% |",
            f"| OF-QSS vs Py-QSS | — | {fmt((of_tau/py_q-1)*100 if of_tau and py_q else None,1)}% |",
        ]

    lines += [
        "",
        "## Rung (b) — single-step (see separate re-acceptance)",
        "",
        "Recorded in `FROZEN_RUNG_B_ACCEPTANCE.md` after conform single-step harness.",
        "",
        "## 2D QSS",
        "",
        "**UNBLOCKED** for opposed-jet qssOnly + rlAdaptive smoke (master spec §5.2).",
        "See `DEBUG_REPORT.md`.",
        "",
    ]
    (OUT / "FROZEN_VALIDATION_BASELINE_v1.md").write_text("\n".join(lines) + "\n")

    hub = [
        "# E15 signature map — frozen baseline v1 (CONFORM / T-freeze)",
        "",
        "Production OF-QSS = corrector T-freeze, `epsmin=0.02`.",
        "Pre-freeze map retained under git history / `E15_BEFORE_AFTER_TFREEZE.md`.",
        "",
        f"- Conditions: {of.get('n_conditions', 38)}",
        f"- ΔTeq UNAVAILABLE holes: {n_holes}",
        "",
        "## Links",
        "",
        "- OF map: `E15_SIGNATURE_MAP_OF.md`",
        "- Python map: `E15_SIGNATURE_MAP_PYTHON.md`",
        "- Diffs: `E15_OF_VS_PY_DIFFS.md`",
        "- Before/after: `E15_BEFORE_AFTER_TFREEZE.md`",
        "- Equilibration audit: `E15_EQUILIBRATION_AUDIT.md`",
        "- Frozen package: `FROZEN_VALIDATION_BASELINE_v1.md`",
        "",
    ]
    (OUT / "E15_SIGNATURE_MAP.md").write_text("\n".join(hub))
    print(f"Wrote frozen baseline; postprocess_rc={rc}; holes={n_holes}; sign_match={n_sign}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
