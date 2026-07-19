# E12.1-redo — Cantera sizing + CVODE opposed-jet @ T_air=1250 K

## Sizing (`e12_size_ignition.py`)

At **10 atm**, fuel 300 K / air `T_air`, Z∈[0.03,0.10]:

| T_air | Z | Tmix | τ_ign |
|------:|--:|-----:|------:|
| 1200 | 0.05 | 1093 K | **1.50 ms** (best in 1–2 ms band) |
| 1250 | 0.08 | 1079 K | 1.50 ms |
| 1100 | (prior E12.1) | — | 2D: **no ignition** (max T≈1048 K) |

JSON: `../e12_size/e12_size_ignition.json`. Cantera curve archived there.

## Case update

Air BC **1100 → 1250 K** (`T_air1250`; prior in `../e12_opposedJet_T1100_archive/`).
cvode, `endTime=0.005` (≈3×τ_0D). **Did not extend** past 3×τ.

## Run result — **NO IGNITION**

| Metric | Value |
|--------|------:|
| wall | 12111 s (~3.4 h) |
| FATAL | none |
| End | yes |
| max\|T\| field | **1250 K** (air BC only) |
| max internal T (propSanity) | **1164 K** |
| propSanity blend | ~1.9e-14 |
| ΣY / physical | no crash; fields written through 0.005 |

Same qualitative outcome as T_air=1100: mixing-layer heating without thermal runaway under this strain / domain. 0D-sized τ does **not** guarantee 2D opposed-jet ignition.

## Artifacts

- `log.reactingFoam`, `log.blockMesh`, `wall.txt`, `e12_prop_sanity.csv`
- `chemistryProperties`, `controlDict` copies
- Case time dirs under `cases/opposedJet_2D/` through `0.005/`

## Next (advisor)

Raise strain-aware T_air further (e.g. 1300–1350 from size table) **or** reduce strain / enlarge residence — not unilateral endTime stretch.
