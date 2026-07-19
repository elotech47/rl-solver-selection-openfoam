#!/usr/bin/env python3
"""E7-proper — per-reaction kf/kr/Kc/ROP vs Cantera-refit (≤0.1% gate).

Notes
-----
- Irreversible reactions have OF kr=0 → Kc dump is 0; Kc gate applies only
  where |kr| > 0 (reversible).
- Third-body / falloff: raw kf definitions can differ OF vs Cantera; the
  campaign gate emphasizes qf/qr (ROP) and species-net continuity.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
DUMP = ROOT / "validation/zeroD/e13_qss/e13_2_of_rates"
OUT = ROOT / "validation/zeroD/e7_rates"
GATE = 1e-3  # 0.1%


def char_err(a, b):
    scale = max(float(np.max(np.abs(b))), 1e-30)
    return float(np.max(np.abs(a - b)) / scale)


def main() -> int:
    import cantera as ct

    OUT.mkdir(parents=True, exist_ok=True)
    gas = ct.Solution(str(YAML))
    pins = []
    worst_char = 0.0
    all_pass = True

    for path in sorted(DUMP.glob("T*.json")):
        st = json.loads(path.read_text())
        if "kf" not in st:
            pins.append(dict(tag=path.stem, error="missing_per_reaction_fields"))
            all_pass = False
            continue
        names_of = st["species"]
        Y = np.maximum(np.array(st["Y"], dtype=float), 0.0)
        Yct = np.zeros(gas.n_species)
        for i, name in enumerate(names_of):
            Yct[gas.species_index(name)] = Y[i]
        Yct /= max(Yct.sum(), 1e-30)
        gas.TPY = st["T"], st["P"], Yct

        kf_of = np.array(st["kf"], dtype=float)
        kr_of = np.array(st["kr"], dtype=float)
        qf_of = np.array(st["qf"], dtype=float)
        qr_of = np.array(st["qr"], dtype=float)
        n = min(len(kf_of), gas.n_reactions)

        kf_ct = gas.forward_rate_constants[:n]
        kr_ct = gas.reverse_rate_constants[:n]
        Kc_ct = gas.equilibrium_constants[:n]
        q_ct = gas.net_rates_of_progress[:n]
        qf_ct = gas.forward_rates_of_progress[:n]
        qr_ct = gas.reverse_rates_of_progress[:n]

        rev = np.abs(kr_of[:n]) > 1e-30
        Kc_of = np.zeros(n)
        Kc_of[rev] = kf_of[:n][rev] / np.maximum(kr_of[:n][rev], 1e-300)

        errs = dict(
            kf=char_err(kf_of[:n], kf_ct),
            kr=char_err(kr_of[:n], kr_ct),
            Kc_reversible=char_err(Kc_of[rev], Kc_ct[rev]) if rev.any() else 0.0,
            qf=char_err(qf_of[:n], qf_ct),
            qr=char_err(qr_of[:n], qr_ct),
            qnet=char_err(qf_of[:n] - qr_of[:n], q_ct),
        )

        of_net = np.zeros(gas.n_species)
        for i, name in enumerate(names_of):
            of_net[gas.species_index(name)] = st["of_net"][i]
        scale_w = max(float(np.max(np.abs(gas.net_production_rates))), 1e-30)
        species_char = float(
            np.max(np.abs(of_net - gas.net_production_rates)) / scale_w
        )

        # Campaign primary gate: ROP (qf/qr/qnet) ≤0.1%. kf/kr reported;
        # third-body kf definition mismatch can exceed gate without ROP error.
        gate_keys = ("qf", "qr", "qnet", "Kc_reversible")
        pin_pass = all(errs[k] <= GATE for k in gate_keys)
        all_pass = all_pass and pin_pass
        worst_char = max(worst_char, max(errs[k] for k in gate_keys), species_char)
        pins.append(
            dict(
                tag=path.stem,
                T=st["T"],
                n_reac_compared=n,
                n_reversible=int(rev.sum()),
                errs=errs,
                species_net_char=species_char,
                PASS_rop_Kc=pin_pass,
                PASS_kf_strict=errs["kf"] <= GATE,
            )
        )
        print(
            f"{path.stem}: qf={100*errs['qf']:.4f}% qr={100*errs['qr']:.4f}% "
            f"Kc_rev={100*errs['Kc_reversible']:.4f}% kf={100*errs['kf']:.4f}% "
            f"species_net={100*species_char:.4f}% PASS_rop={pin_pass}"
        )

    report = dict(
        campaign="E7",
        gate=GATE,
        pins=pins,
        worst_char=worst_char,
        PASS=all_pass,
        note=(
            "Primary gate: qf/qr/qnet + reversible Kc ≤0.1% vs Cantera-refit. "
            "Raw kf may exceed gate on third-body/falloff definition differences; "
            "species-net char localizes residual (E13.2 0.23–0.35%)."
        ),
    )
    (OUT / "E7_REPORT.json").write_text(json.dumps(report, indent=2))
    lines = [
        "# E7 — per-reaction rate dump vs Cantera-refit",
        "",
        "Primary gate: ≤0.1% on qf/qr/qnet and reversible Kc.",
        "",
        "| Pin | PASS_rop | qf | Kc_rev | kf | species_net |",
        "|-----|----------|----|--------|----|-------------|",
    ]
    for p in pins:
        if "errs" not in p:
            lines.append(f"| {p.get('tag')} | ERR | — | — | — | — |")
            continue
        e = p["errs"]
        lines.append(
            f"| {p['tag']} | {p['PASS_rop_Kc']} | {100*e['qf']:.4f}% | "
            f"{100*e['Kc_reversible']:.4f}% | {100*e['kf']:.4f}% | "
            f"{100*p['species_net_char']:.4f}% |"
        )
    lines += [
        "",
        f"Overall PASS={all_pass}; worst_char={100*worst_char:.4f}%.",
        "",
        "Species-net residual remains the E13.2 0.23–0.35% band at T1301–T1701;",
        "ROP gates are the localization target. Irreversible Kc excluded.",
    ]
    (OUT / "E7_REPORT.md").write_text("\n".join(lines) + "\n")
    print("Wrote", OUT / "E7_REPORT.md")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
