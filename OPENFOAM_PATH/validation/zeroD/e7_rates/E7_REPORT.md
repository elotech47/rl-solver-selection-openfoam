# E7 — per-reaction rate dump vs Cantera-refit

## Verdict

**FAIL** primary ROP/Kc gate (≤0.1% char) — driven by **falloff outliers**, not a
systematic OF↔Cantera bias.

| Pin | qf char | qr char | Kc_rev char | kf char | species_net |
|-----|---------|---------|-------------|---------|-------------|
| T1301 | 0.049% | 1.302% | 1.332% | 0.595% | 0.283% |
| T1500 | 0.035% | 1.301% | 1.323% | 0.219% | 0.347% |
| T1701 | 0.027% | 1.301% | 1.316% | 0.099% | 0.228% |
| T2001 | 0.023% | 1.383% | 1.321% | 0.039% | 0.097% |

## Localization

At T1701 (representative):

- Median `kr_OF/kr_CT` (reversible) ≈ **1.0002**; p10–p90 ≈ 0.987–1.014
- Median `Kc` / `qf` / `qr` ratios ≈ **1.000**
- Worst `qr` char contributor: **`c2h4 + h (+M) <=> c2h5 (+M)`** (falloff),
  |Δ|/|CT| ≈ 1.3% — same scale as the char metric

Irreversible reactions (565/678): OF `kr=0`; Kc gate restricted to reversible
subset (113).

## Species-net (E13.2 continuity)

0.23–0.35% char at T1301–T1701 is **not exonerated**. Per-reaction dump shows
forward ROP is green; reverse/falloff definitions carry the residual into
species-net. Not a single-species kinetic bug in Arrhenius A/n/Ea for simple
reactions.

## Dump

`OFRL_DUMP_RATES=1` now writes `kf`, `kr`, `Kc`, `qf`, `qr` alongside `of_net`
(`solveChemistry.H`). JSON: `e13_qss/e13_2_of_rates/T*.json`.

## Artifacts

- `E7_REPORT.json` — machine-readable
- Compare script: `validation/zeroD/e7_compare.py`
