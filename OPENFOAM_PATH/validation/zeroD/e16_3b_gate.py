#!/usr/bin/env python3
"""E16.3b gate — teacher-forced ≥99% + extended free-run progress-space usage."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "validation/e16_parity/e16_3b_runs"
GATE = ROOT / "validation/e16_parity/E16_3B_GATE.md"


def phase_usage(T: np.ndarray, flags: np.ndarray, T0: float, T_ign: float):
    """Split into pre-ignition (T < T0+0.5*(T_ign-T0)) and post; return CVODE %."""
    if len(T) == 0:
        return {}
    mid = T0 + 0.5 * max(T_ign - T0, 1.0)
    pre = flags[T < mid]
    post = flags[T >= mid]
    def frac(a):
        if len(a) == 0:
            return None
        return 100.0 * float(np.mean(a == 0))
    return {
        "pre_cvode_pct": frac(pre),
        "post_cvode_pct": frac(post),
        "all_cvode_pct": 100.0 * float(np.mean(flags == 0)),
        "T_mid": mid,
        "n_pre": int(len(pre)),
        "n_post": int(len(post)),
    }


def usage_band_ok(of_pct, py_pct) -> bool | None:
    if of_pct is None or py_pct is None:
        return None
    if py_pct <= 0:
        return of_pct <= 5.0  # both near-zero OK
    lo, hi = 0.5 * py_pct, 2.0 * py_pct
    return lo <= of_pct <= hi


def main() -> int:
    lines = [
        "# E16.3b — Teacher-forced parity + extended free-run",
        "",
        "**Date:** 2026-07-19",
        "**Gate redesign:** see `DECISIONS.md` (E16.3b).",
        "- **Parity** = teacher-forced in-process ≥99% decision agreement",
        "- **Free-run** = phase-consistency in T-space + usage within 0.5–2× per phase",
        "  + final-state vs cvodeOnly (≤ paper 0D envelope, |ΔT|≲50 K)",
        "- Retired: ±5-point scalar CVODE-usage gate (single-flip fork sensitivity)",
        "",
        "## Teacher-forced (true in-loop parity)",
        "",
    ]

    tf_path = RUNS / "teacher_forced_summary.json"
    teacher_ok = False
    if tf_path.is_file():
        tf = json.loads(tf_path.read_text())
        teacher_ok = bool(tf.get("pass", False))
        lines.append(
            f"- Overall: **{'PASS' if teacher_ok else 'FAIL'}** "
            f"({tf.get('agree_pct', '?')}% agree, n={tf.get('n_total', '?')})"
        )
        for lab, block in tf.get("by_label", {}).items():
            lines.append(
                f"  - {lab}: {block.get('agree_pct')}% "
                f"(mismatches={block.get('n_mismatch')})"
            )
            mism = block.get("mismatches", [])[:10]
            for m in mism:
                lines.append(
                    f"    - step={m.get('step')} T={m.get('T'):.1f} "
                    f"OF={m.get('of_flag')} Py={m.get('py_flag')} "
                    f"|p−0.5|={m.get('margin'):.4f} of_p={m.get('of_p'):.4f} py_p={m.get('py_p'):.4f}"
                )
        lines.append("")
    else:
        lines.append("- **MISSING** `teacher_forced_summary.json`")
        lines.append("")

    lines.append("## Extended free-run (progress-space)")
    lines.append("")

    free_ok = True
    routing = "unknown"

    for label, T0, t_end in (("MidT", 800.0, 3.4e-3), ("NTC", 700.0, 8.0e-3)):
        lines.append(f"### {label} (t_end={t_end})")
        lines.append("")
        py_sum = RUNS / f"{label}_python" / "summary.json"
        of_dec = RUNS / f"{label}_rlAdaptive" / "rl_decisions.csv"
        of_T = RUNS / f"{label}_rlAdaptive" / "fields" / "T"
        cv_T = RUNS / f"{label}_cvodeOnly" / "fields" / "T"

        if not py_sum.is_file() or not of_dec.is_file():
            lines.append("- **MISSING** artifacts")
            free_ok = False
            lines.append("")
            continue

        pys = json.loads(py_sum.read_text())
        of_rows = np.genfromtxt(of_dec, delimiter=",", names=True, dtype=None, encoding=None)
        py_rows = np.genfromtxt(
            RUNS / f"{label}_python" / "decisions.csv",
            delimiter=",",
            names=True,
            dtype=None,
            encoding=None,
        )

        T_ign_py = float(pys.get("T_final_rl", T0))
        of_ph = phase_usage(of_rows["T"], of_rows["flag"].astype(int), T0, T_ign_py)
        py_ph = phase_usage(py_rows["T"], py_rows["executed_action"].astype(int), T0, T_ign_py)

        pre_ok = usage_band_ok(of_ph["pre_cvode_pct"], py_ph["pre_cvode_pct"])
        post_ok = usage_band_ok(of_ph["post_cvode_pct"], py_ph["post_cvode_pct"])
        lines.append(
            f"- CVODE% all: OF={of_ph['all_cvode_pct']:.1f} Py={py_ph['all_cvode_pct']:.1f}"
        )
        lines.append(
            f"- CVODE% pre (T<{of_ph['T_mid']:.0f}): "
            f"OF={of_ph['pre_cvode_pct']} Py={py_ph['pre_cvode_pct']} "
            f"→ {pre_ok}"
        )
        lines.append(
            f"- CVODE% post: OF={of_ph['post_cvode_pct']} Py={py_ph['post_cvode_pct']} "
            f"→ {post_ok}"
        )
        if pre_ok is False or post_ok is False:
            free_ok = False

        # final T
        def read_T(path: Path):
            if not path.is_file():
                return None
            for line in path.read_text().splitlines():
                if "internalField" in line and "uniform" in line:
                    return float(line.split()[-1].rstrip(";"))
            return None

        Tr = read_T(of_T)
        Tc = read_T(cv_T)
        if Tr is not None and Tc is not None:
            dT = abs(Tr - Tc)
            tok = dT <= 50.0
            lines.append(f"- Final T: rl={Tr:.2f} cvode={Tc:.2f} |ΔT|={dT:.2f} → {tok}")
            if not tok:
                free_ok = False
        else:
            lines.append(f"- Final T: rl={Tr} cvode={Tc} (check fields)")
            # Python envelope
            lines.append(
                f"- Py |ΔT| vs CVODE: {pys.get('dT_vs_cvode')}"
            )

        plot = RUNS / f"{label}_decisions_vs_T.png"
        lines.append(f"- Progress plot: `{plot.name if plot.is_file() else 'MISSING'}`")
        lines.append("")

    lines.append("## Outcome routing")
    lines.append("")
    if teacher_ok and free_ok:
        routing = "E16 CLOSED GREEN → proceed to E17 rlAdaptive smoke"
        verdict = "PASS"
    elif teacher_ok and not free_ok:
        routing = (
            "Teacher-forced green but free-run usage diverges — "
            "**human review** (inspect fork decision features/probs) before E17"
        )
        verdict = "CONDITIONAL"
    elif not teacher_ok:
        routing = (
            "Teacher-forced <99% → **in-process feature bug**; "
            "fix builder-side only (never exported constants); rerun E16.3b"
        )
        verdict = "FAIL"
    else:
        routing = "incomplete artifacts"
        verdict = "INCOMPLETE"

    lines.append(f"- Routing: {routing}")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"**{verdict}**")
    lines.append("")

    GATE.write_text("\n".join(lines) + "\n")
    print(GATE.read_text())
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
