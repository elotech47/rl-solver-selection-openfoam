# E12.1-redo — Cantera sizing + STATUS

## Sizing (`e12_size_ignition.py`)

At **10 atm**, fuel 300 K / air `T_air`, Z∈[0.03,0.10]:

| T_air | Z | Tmix | τ_ign |
|------:|--:|-----:|------:|
| 1200 | 0.05 | 1093 K | **1.50 ms** (best in 1–2 ms band) |
| 1250 | 0.08 | 1079 K | 1.50 ms |
| 1100 | (prior E12.1) | — | 2D: **no ignition** (max T≈1048 K) |

JSON: `e12_size/e12_size_ignition.json`.

## Case update

`cases/opposedJet_2D/0/T` air BC: **1100 → 1250 K** (margin for strain vs pure 0D;
still within sized band). Prior T archived under `e12_opposedJet_T1100_archive/`.

Keep cvode, `endTime=0.005` (≈3×τ). Do not extend beyond 3×τ if no ignition.

## Run

Output dir: `validation/zeroD/e12_opposedJet_redo/`

Acceptance: no FATAL through runaway; physical T/Y; ΣY tight; archive T/OH maps.
