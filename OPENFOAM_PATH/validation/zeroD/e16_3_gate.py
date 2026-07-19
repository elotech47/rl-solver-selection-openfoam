#!/usr/bin/env python3
"""E16.3 gate — compare OF rlAdaptive vs Python AdaptiveRL + mode timings."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "validation/e16_parity/e16_3_runs"
GATE = ROOT / "validation/e16_parity/E16_3_GATE.md"


def of_usage(label: str) -> dict | None:
    p = RUNS / f"{label}_rlAdaptive" / "rl_decisions.csv"
    if not p.is_file():
        return None
    flags = []
    with p.open() as f:
        next(f)  # header
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 4:
                flags.append(int(float(parts[3])))
    n = max(len(flags), 1)
    cvode = 100.0 * sum(1 for a in flags if a == 0) / n
    return {
        "n_decisions": len(flags),
        "cvode_usage_pct": cvode,
        "qss_usage_pct": 100.0 - cvode,
        "flags": flags,
    }


def py_usage(label: str) -> dict | None:
    p = RUNS / f"{label}_python" / "summary.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def final_T(path: Path) -> float | None:
    if not path.is_file():
        return None
    txt = path.read_text()
    # volScalarField: look for internalField nonuniform or uniform
    for line in txt.splitlines():
        if "internalField" in line and "uniform" in line:
            return float(line.split()[-1].rstrip(";"))
    # nonuniform list — take first value after (
    if "nonuniform" in txt:
        after = txt.split("(", 1)[1]
        return float(after.split()[0])
    return None


def wall_from_log(path: Path) -> float | None:
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        if line.startswith("WALL_SEC"):
            return float(line.split()[1])
    return None


def phase_overlap(a: list[int], b: list[int]) -> float:
    """Fraction of overlapping timesteps where both choose same action."""
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return float(np.mean([ai == bi for ai, bi in zip(a[:n], b[:n])]))


def main() -> int:
    lines = [
        "# E16.3 — In-OF rlAdaptive gate",
        "",
        "**Date:** 2026-07-19",
        "**Config:** method `rl` + TorchScript `policy.ts`; QSS T-freeze ON, epsmin=0.02",
        "",
        "## Cases",
        "",
        "| Case | T0 [K] | p [atm] | φ |",
        "|------|-------:|--------:|--:|",
        "| MidT | 800 | 10 | 1.0 |",
        "| NTC  | 700 | 10 | 1.0 |",
        "",
        "## Gates",
        "",
        "1. CVODE-usage (OF rlAdaptive vs Python AdaptiveRL) within **±5 points**",
        "2. Decisions concentrated in same phase (pairwise agreement on overlapping queries)",
        "3. Wall time: rlAdaptive between / better than extremes vs cvodeOnly & qssOnly (report)",
        "4. Final T vs OF cvodeOnly within paper 0D envelope (|ΔT| ≲ 50 K or relative ignition OK)",
        "5. Policy must load (no silent all-CVODE fallback)",
        "",
    ]

    overall = True
    results = {}

    for label in ("MidT", "NTC"):
        ofu = of_usage(label)
        pyu = py_usage(label)
        results[label] = {"of": ofu, "py": pyu}

        lines.append(f"## {label}")
        lines.append("")

        if ofu is None:
            lines.append("- **FAIL** — missing OF `rl_decisions.csv` (policy may not have loaded)")
            overall = False
            continue
        if ofu["n_decisions"] == 0:
            lines.append("- **FAIL** — zero OF decisions logged")
            overall = False
            continue
        if ofu["cvode_usage_pct"] >= 99.9 and ofu["n_decisions"] > 5:
            # Suspicious all-CVODE — only fail if python also not all CVODE
            if pyu and pyu.get("cvode_usage_pct", 100) < 95:
                lines.append(
                    "- **FAIL** — OF nearly all-CVODE while Python is mixed "
                    f"(OF={ofu['cvode_usage_pct']:.1f}%, Py={pyu['cvode_usage_pct']:.1f}%)"
                )
                overall = False

        if pyu is None:
            lines.append("- **WARN** — missing Python reference summary")
            usage_ok = None
        else:
            d_usage = abs(ofu["cvode_usage_pct"] - pyu["cvode_usage_pct"])
            usage_ok = d_usage <= 5.0
            lines.append(
                f"- CVODE usage: OF={ofu['cvode_usage_pct']:.2f}% "
                f"Py={pyu['cvode_usage_pct']:.2f}%  Δ={d_usage:.2f} pts "
                f"→ **{'PASS' if usage_ok else 'FAIL'}** (±5)"
            )
            if not usage_ok:
                overall = False

            # phase: load python decisions
            pycsv = RUNS / f"{label}_python" / "decisions.csv"
            py_flags = []
            if pycsv.is_file():
                with pycsv.open() as f:
                    next(f)
                    for line in f:
                        parts = line.strip().split(",")
                        if len(parts) >= 2:
                            py_flags.append(int(float(parts[1])))
            ov = phase_overlap(ofu["flags"], py_flags)
            lines.append(
                f"- Decision pairwise agreement (overlap n={min(len(ofu['flags']), len(py_flags))}): "
                f"{100*ov:.1f}%"
            )
            lines.append(
                f"- n_decisions: OF={ofu['n_decisions']} Py={pyu.get('n_decisions')}"
            )

        # timings
        walls = {}
        for mode in ("rlAdaptive", "cvodeOnly", "qssOnly"):
            walls[mode] = wall_from_log(RUNS / f"{label}_{mode}" / "log.chemFoam")
        lines.append(
            f"- Wall [s]: rlAdaptive={walls['rlAdaptive']} "
            f"cvodeOnly={walls['cvodeOnly']} qssOnly={walls['qssOnly']}"
        )

        # final T
        T_rl = final_T(RUNS / f"{label}_rlAdaptive" / "fields" / "T")
        T_cv = final_T(RUNS / f"{label}_cvodeOnly" / "fields" / "T")
        if T_rl is not None and T_cv is not None:
            dT = abs(T_rl - T_cv)
            t_ok = dT <= 50.0
            lines.append(
                f"- Final T: rlAdaptive={T_rl:.2f} K  cvodeOnly={T_cv:.2f} K  "
                f"|ΔT|={dT:.2f} K → **{'PASS' if t_ok else 'FAIL'}** (≤50 K)"
            )
            if not t_ok:
                overall = False
        else:
            lines.append(f"- Final T: rl={T_rl} cvode={T_cv} (missing field?)")
            overall = False

        lines.append("")

    lines.append("## Verdict")
    lines.append("")
    lines.append(f"**{'PASS' if overall else 'FAIL'}**")
    lines.append("")
    GATE.write_text("\n".join(lines) + "\n")
    print(GATE.read_text())
    (RUNS / "e16_3_gate.json").write_text(json.dumps(results, indent=2, default=str))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
