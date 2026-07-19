#!/usr/bin/env python3
"""E14.3 — QSS-path ha/cp vs Cantera-refit NASA polys at 5 T pins × 10 species.

Documents ESI janafThermo::coeffs(T) selection (Tlow/Tcommon/Thigh) and that
QssCellOde evaluates per-species ha/cp at the instantaneous T with no
cross-window coeff cache.

Compares mole-basis ha [J/kmol] and cp [J/kmol/K] from Cantera (refit YAML)
against NASA7 evaluation of the foam/refit coefficients for the same species.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
THERMO = ROOT / "mechanisms/foam/thermo"
OUT = ROOT / "validation/zeroD/e14_thermo_range"
PINS = [900.0, 1200.0, 1500.0, 2000.0, 2600.0]
SPECIES = ["nc12h26", "O2", "N2", "CO2", "H2O", "CO", "OH", "H", "O", "CH4"]
R_u = 8314.462618  # J/kmol/K (OF / Cantera molar gas constant)


def parse_foam_nasa(path: Path) -> dict:
    """Parse OpenFOAM thermo file NASA coeffs (low/high, Tcommon)."""
    text = path.read_text()
    species = {}

    def coeffs(s: str):
        nums = re.findall(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?", s)
        return [float(x) for x in nums[:7]]

    # Top-level species dicts: name\n{\n ... nested braces ... \n}
    i = 0
    n = len(text)
    while i < n:
        m = re.match(r"\s*([A-Za-z_][\w-]*)\s*\{", text[i:])
        if not m:
            i += 1
            continue
        name = m.group(1)
        i += m.end()
        depth = 1
        start = i
        while i < n and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[start : i - 1]
        tm = re.search(r"thermodynamics\s*\{", body)
        if not tm:
            continue
        j = tm.end()
        depth = 1
        t0 = j
        while j < len(body) and depth:
            if body[j] == "{":
                depth += 1
            elif body[j] == "}":
                depth -= 1
            j += 1
        thermo = body[t0 : j - 1]

        def grab(key):
            mm = re.search(rf"{key}\s+([^\n;]+)", thermo)
            return mm.group(1).strip() if mm else None

        high = grab("highCpCoeffs")
        low = grab("lowCpCoeffs")
        if not high or not low:
            continue
        species[name] = dict(
            Tlow=float(grab("Tlow") or "200"),
            Thigh=float(grab("Thigh") or "5000"),
            Tcommon=float(grab("Tcommon") or "1000"),
            high=coeffs(high),
            low=coeffs(low),
        )
    return species

def nasa_cp_ha(a, T):
    """NASA-7 mole cp and ha (J/kmol, J/kmol/K) matching OF janafThermo."""
    # cp/R = a0 + a1 T + a2 T^2 + a3 T^3 + a4 T^4
    # ha/R = a0 T + a1 T^2/2 + a2 T^3/3 + a3 T^4/4 + a4 T^5/5 + a5
    a0, a1, a2, a3, a4, a5, a6 = a
    cp = R_u * (a0 + a1 * T + a2 * T**2 + a3 * T**3 + a4 * T**4)
    ha = R_u * (
        a0 * T
        + a1 * T**2 / 2
        + a2 * T**3 / 3
        + a3 * T**4 / 4
        + a4 * T**5 / 5
        + a5
    )
    return cp, ha


def foam_cp_ha(entry, T):
    a = entry["high"] if T >= entry["Tcommon"] else entry["low"]
    return nasa_cp_ha(a, T)


def main() -> int:
    import cantera as ct

    OUT.mkdir(parents=True, exist_ok=True)
    foam = parse_foam_nasa(THERMO)
    gas = ct.Solution(str(YAML))

    # ESI janafThermo::coeffs(T) documentation (verbatim behaviour)
    doc = {
        "esi_janafThermo_coeffs_T": (
            "If T < Tcommon use lowCpCoeffs; else use highCpCoeffs. "
            "No blending across Tcommon. Per-species Tcommon from thermo file. "
            "QssCellOde calls specieThermo[i].ha(p,T) / .cp(p,T) each odefun "
            "evaluation — no cross-window coeff cache."
        ),
        "option_R_note": "Production foam has harmonized Tcommon (typically 1000 K).",
    }

    rows = []
    max_rel_cp = 0.0
    max_rel_ha = 0.0
    worst = None
    for sp in SPECIES:
        if sp not in foam:
            # try case variants
            cand = [k for k in foam if k.lower() == sp.lower()]
            if not cand:
                rows.append(dict(species=sp, error="missing_in_foam"))
                continue
            sp_f = cand[0]
        else:
            sp_f = sp
        try:
            j = gas.species_index(sp if sp in gas.species_names else sp_f)
        except Exception:
            # Cantera names may differ (n-C12H26 vs nc12h26)
            alias = {
                "nc12h26": "n-C12H26",
                "CH4": "CH4",
            }.get(sp, sp)
            if alias not in gas.species_names:
                rows.append(dict(species=sp, error="missing_in_cantera"))
                continue
            j = gas.species_index(alias)

        for T in PINS:
            gas.TPX = T, ct.one_atm, {gas.species_name(j): 1.0}
            # Cantera partial molar: enthalpy_mole [J/kmol], cp_mole
            cp_ct = float(gas.partial_molar_cp[j])
            ha_ct = float(gas.partial_molar_enthalpies[j])
            cp_f, ha_f = foam_cp_ha(foam[sp_f], T)
            rel_cp = abs(cp_f - cp_ct) / max(abs(cp_ct), 1.0)
            rel_ha = abs(ha_f - ha_ct) / max(abs(ha_ct), 1.0)
            max_rel_cp = max(max_rel_cp, rel_cp)
            max_rel_ha = max(max_rel_ha, rel_ha)
            row = dict(
                species=sp,
                foam_name=sp_f,
                T=T,
                Tcommon=foam[sp_f]["Tcommon"],
                branch="high" if T >= foam[sp_f]["Tcommon"] else "low",
                cp_foam=cp_f,
                cp_cantera=cp_ct,
                rel_cp=rel_cp,
                ha_foam=ha_f,
                ha_cantera=ha_ct,
                rel_ha=rel_ha,
            )
            rows.append(row)
            if worst is None or rel_ha > worst["rel_ha"]:
                worst = row

    report = dict(
        campaign="E14.3",
        documentation=doc,
        n_rows=len(rows),
        max_rel_cp=max_rel_cp,
        max_rel_ha=max_rel_ha,
        worst=worst,
        PASS_cp=max_rel_cp < 1e-3,
        PASS_ha=max_rel_ha < 1e-3,
        rows=rows,
    )
    out = OUT / "e14_3_thermo_range.json"
    out.write_text(json.dumps(report, indent=2))
    md = OUT / "E14_3_THERMO_RANGE.md"
    md.write_text(
        f"""# E14.3 — QSS-path ha/cp thermo-range audit

## ESI `janafThermo::coeffs(T)` (behaviour used by QSS)

{doc['esi_janafThermo_coeffs_T']}

{doc['option_R_note']}

## Numerical check (5 pins × 10 species)

| Metric | Value | Gate |
|--------|-------|------|
| max rel \|cp\| | {100*max_rel_cp:.4e}% | <0.1% |
| max rel \|ha\| | {100*max_rel_ha:.4e}% | <0.1% |
| PASS_cp | {report['PASS_cp']} | |
| PASS_ha | {report['PASS_ha']} | |

Worst: `{worst}`

If PASS → focus stays on RR/ledger (E14.2/4). Mismatch → in-scope E14 thermo fix.
"""
    )
    print(f"max_rel_cp={max_rel_cp:.3e} max_rel_ha={max_rel_ha:.3e}")
    print("Wrote", out)
    return 0 if report["PASS_cp"] and report["PASS_ha"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
