#!/usr/bin/env python3
"""E10b — histogram of (Tlow, Tcommon, Thigh) across foam thermo files."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _extract_brace_block(text: str, open_idx: int) -> tuple[str, int]:
    """Given index of '{', return (inner_content, index_after_closing)."""
    assert text[open_idx] == "{"
    depth = 0
    i = open_idx
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i], i + 1
        i += 1
    raise ValueError("unbalanced braces")


def parse_foam_thermo(path: Path):
    """Return list of dicts: name, Tlow, Tcommon, Thigh."""
    text = path.read_text()
    # Drop FoamFile header if present
    species = []
    # Find top-level "name\n{" entries
    for m in re.finditer(r"(?m)^([A-Za-z][A-Za-z0-9_+\-()]*)\s*\n\s*\{", text):
        name = m.group(1)
        if name in ("FoamFile",):
            continue
        open_idx = text.find("{", m.start())
        try:
            body, _ = _extract_brace_block(text, open_idx)
        except ValueError:
            continue
        # Find thermodynamics sub-block
        tm = re.search(r"thermodynamics\s*\{", body)
        if not tm:
            continue
        t_open = body.find("{", tm.start())
        try:
            tbody, _ = _extract_brace_block(body, t_open)
        except ValueError:
            continue

        def grab(key: str):
            mm = re.search(rf"{key}\s+([0-9.eE+\-]+)\s*;", tbody)
            return float(mm.group(1)) if mm else None

        Tlow, Thigh, Tcommon = grab("Tlow"), grab("Thigh"), grab("Tcommon")
        if None in (Tlow, Thigh, Tcommon):
            continue
        species.append(dict(name=name, Tlow=Tlow, Tcommon=Tcommon, Thigh=Thigh))
    return species


def summarize(label: str, species: list):
    tuples = [(s["Tlow"], s["Tcommon"], s["Thigh"]) for s in species]
    counts = Counter(tuples)
    tcommons = Counter(s["Tcommon"] for s in species)
    thighs = Counter(s["Thigh"] for s in species)
    by_tcommon = defaultdict(list)
    for s in species:
        by_tcommon[s["Tcommon"]].append(s["name"])
    return {
        "label": label,
        "n_species": len(species),
        "n_distinct_tuples": len(counts),
        "n_distinct_Tcommon": len(tcommons),
        "n_distinct_Thigh": len(thighs),
        "tuple_histogram": [
            {"Tlow": a, "Tcommon": b, "Thigh": c, "count": n}
            for (a, b, c), n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        ],
        "Tcommon_histogram": [
            {
                "Tcommon": t,
                "count": n,
                "example_species": by_tcommon[t][:8],
            }
            for t, n in sorted(tcommons.items(), key=lambda x: (-x[1], x[0]))
        ],
        "Thigh_histogram": [
            {"Thigh": t, "count": n}
            for t, n in sorted(thighs.items(), key=lambda x: (-x[1], x[0]))
        ],
        "uniform_breakpoints": len(counts) == 1,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "validation/thermo_audit/e10b_tcommon",
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    cases = [
        ("Luo_106", ROOT / "mechanisms/foam/thermo"),
        (
            "skeletal_53",
            ROOT / "validation/zeroD/e3_skeletal_dodecane/case/constant/thermo",
        ),
        ("GRI_tutorial", ROOT / "validation/zeroD/e9_constprop/gri_p/constant/thermo"),
    ]

    report = []
    lines = ["# E10b — Tcommon / breakpoint histogram\n"]
    for label, path in cases:
        if not path.exists():
            lines.append(f"## {label}\nMISSING: `{path}`\n")
            continue
        species = parse_foam_thermo(path)
        summ = summarize(label, species)
        report.append(summ)
        (args.out / f"{label}_species.json").write_text(json.dumps(species, indent=2))
        lines.append(f"## {label}\n")
        lines.append(f"- file: `{path.relative_to(ROOT)}`\n")
        lines.append(f"- n_species: **{summ['n_species']}**\n")
        lines.append(
            f"- distinct (Tlow,Tcommon,Thigh): **{summ['n_distinct_tuples']}**\n"
        )
        lines.append(f"- distinct Tcommon: **{summ['n_distinct_Tcommon']}**\n")
        lines.append(f"- uniform breakpoints: **{summ['uniform_breakpoints']}**\n")
        lines.append("\n### Tuple histogram\n")
        lines.append(
            "| Tlow | Tcommon | Thigh | count |\n|-----:|--------:|------:|------:|\n"
        )
        for row in summ["tuple_histogram"]:
            lines.append(
                f"| {row['Tlow']:g} | {row['Tcommon']:g} | {row['Thigh']:g} | {row['count']} |\n"
            )
        lines.append("\n### Tcommon histogram (examples)\n")
        lines.append(
            "| Tcommon | count | example species |\n|--------:|------:|-----------------|\n"
        )
        for row in summ["Tcommon_histogram"]:
            ex = ", ".join(row["example_species"][:5])
            lines.append(f"| {row['Tcommon']:g} | {row['count']} | {ex} |\n")
        lines.append("\n")

    luo = next((r for r in report if r["label"] == "Luo_106"), None)
    gri = next((r for r in report if r["label"] == "GRI_tutorial"), None)
    sk = next((r for r in report if r["label"] == "skeletal_53"), None)

    lines.append("## Thesis-ready root-cause paragraph\n\n")
    claim_pass = False
    stop_exact_uniform = False
    if luo and gri and luo["n_species"] and gri["n_species"]:
        # Campaign expected: GRI = single tuple *or near*; Luo = many Tcommon.
        gri_dom = gri["Tcommon_histogram"][0]
        gri_dom_frac = gri_dom["count"] / gri["n_species"]
        gri_exact = gri["n_distinct_Tcommon"] == 1
        # "Near": ≥95% of species share one Tcommon, or ≤3 outliers.
        gri_near = gri_exact or gri_dom_frac >= 0.95 or (
            gri["n_species"] - gri_dom["count"]
        ) <= 3
        luo_hetero = luo["n_distinct_Tcommon"] > 1
        claim_pass = gri_near and luo_hetero
        stop_exact_uniform = not gri_exact  # nuance for human gate

        outliers = [
            r for r in gri["Tcommon_histogram"] if r["Tcommon"] != gri_dom["Tcommon"]
        ]
        outlier_names = []
        for r in outliers:
            outlier_names.extend(r["example_species"])

        lines.append(
            "OpenFOAM evaluates mixture sensible enthalpy and heat capacity for "
            "`hePsiThermo::correct()` / `THE` by blending each species' NASA-7 "
            "*coefficient arrays* by mass fraction (`multiComponentMixture::cellMixture`) "
            "and then evaluating the resulting pseudo-species polynomials. That blend "
            "is algebraically identical to a mass-weighted property average "
            "(`Σ Yi·cp_i`, `Σ Yi·hs_i`) *only* when every species shares the same "
            "temperature breakpoints (especially a shared `Tcommon`). "
        )
        lines.append(
            f"In the ESI GRI chemFoam tutorial thermo, "
            f"**{gri_dom['count']}/{gri['n_species']}** species share "
            f"Tcommon = {gri_dom['Tcommon']:g} K"
        )
        if gri_exact:
            lines.append(" (exact uniformity). ")
        else:
            out_tc = ", ".join(f"{r['Tcommon']:g}" for r in outliers)
            lines.append(
                f" (near-uniform; outliers: {', '.join(outlier_names)} with "
                f"Tcommon ∈ {{{out_tc}}}; "
                f"Thigh also varies → {gri['n_distinct_tuples']} distinct full tuples). "
            )
        lines.append(
            f"The Luo n-dodecane foam thermo has **{luo['n_distinct_tuples']}** distinct "
            f"(Tlow,Tcommon,Thigh) tuples and **{luo['n_distinct_Tcommon']}** distinct "
            f"Tcommon values across {luo['n_species']} species"
        )
        if sk and sk["n_species"]:
            lines.append(
                f"; the skeletal foam thermo shows "
                f"**{sk['n_distinct_tuples']}** distinct tuples and "
                f"**{sk['n_distinct_Tcommon']}** distinct Tcommon "
                f"({sk['n_species']} species parsed)"
            )
        lines.append(
            ". Above the lowest Tcommon in a mixed cell, some species are already on "
            "their high-range coefficients while others remain on low-range ones, so the "
            "blended coefficients no longer represent any physical mixture average: "
            "burnt-gas blended cp collapses toward zero and can change sign, while "
            "`Σ Yi·cp_i` stays O(1400) J/(kg·K). The h→T Newton then diverges (E8). "
            "This is **H6**: a representation defect exposed by OpenFOAM's coefficient "
            "blend under mechanism-heterogeneous JANAF breakpoints, not a corruption of "
            "per-species thermo tables (E2).\n"
        )

        lines.append("\n## Claim check\n\n")
        lines.append(
            f"- GRI Tcommon exact-uniform: **{gri_exact}** "
            f"({gri['n_distinct_Tcommon']} distinct; "
            f"dominant {gri_dom['count']}/{gri['n_species']} = {100*gri_dom_frac:.1f}% "
            f"at {gri_dom['Tcommon']:g} K)\n"
        )
        lines.append(f"- GRI Tcommon near-uniform (campaign 'or near'): **{gri_near}**\n")
        lines.append(
            f"- Luo heterogeneous: **{luo_hetero}** "
            f"({luo['n_distinct_Tcommon']} Tcommon, {luo['n_distinct_tuples']} tuples; "
            f"only {luo['Tcommon_histogram'][0]['count']}/{luo['n_species']} at "
            f"{luo['Tcommon_histogram'][0]['Tcommon']:g} K)\n"
        )
        lines.append(
            f"- Expected claim (GRI near-uniform ∧ Luo heterogeneous): "
            f"**{'PASS' if claim_pass else 'FAIL'}**\n"
        )
        if not claim_pass:
            lines.append(
                "- **STOP (hard):** Luo uniform or GRI not near-uniform — "
                "E11 refit premise void.\n"
            )
        elif stop_exact_uniform:
            lines.append(
                "- **STOP (human gate):** GRI is near-uniform, not exact "
                f"(outliers: {', '.join(outlier_names)}). H6 mechanism story still "
                "holds (severity of heterogeneity: Luo ≫ GRI), and E11 refit remains "
                "a valid cure for Luo — but campaign stop condition requires human "
                "ack before E11.\n"
            )
        else:
            lines.append("- Proceed to E11 (Option R refit premise intact).\n")
    else:
        lines.append("Parse failure — insufficient species extracted.\n")

    (args.out / "SUMMARY.md").write_text("".join(lines))
    (args.out / "summary.json").write_text(json.dumps(report, indent=2))
    print("".join(lines))
    print(f"\nWrote {args.out}")
    # exit 0 = claim pass + exact GRI; 1 = claim pass but human gate; 2 = hard fail
    if not claim_pass:
        return 2
    if stop_exact_uniform:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
