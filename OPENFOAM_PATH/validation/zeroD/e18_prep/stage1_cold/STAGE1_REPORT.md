# E18 Stage 1 — cold mixing report

## Geometry
| | |
|--|--|
| Gap L | **0.008 m** (Ember `example_diffusion` match) |
| V_inlet | ±0.4 m/s (= a·L/2, a=100) |
| Freeze time | **0.05 s** |
| Cells | 20000 |
| Geometric midplane | 0.004 m |
| Stagnation (Ux=0 on CL) | **0.00622 m** |

## Chemistry OFF check
| | |
|--|--|
| Tmin / Tmax | 300.0000 / 1000.0000 K |
| Gate Tmax ≤ 1000.05 K | **PASS** |

## Ignition readiness (Z*≈0.12, Tmix*≈830.0 K)
| | |
|--|--|
| Cells with \|Z−Z*\|<0.02 in mix layer | 37 |
| Best cell | {"x": 0.00689843, "y": 0.00126, "Z": 0.118331, "T": 811.475, "Ux": -0.142165} |
| Peak mix-layer T / Z | {"T": 952.16, "Z": 0.0203138, "x": 0.00712851} |

## alphaEff
| | |
|--|--|
| Status | **PASS nonzero** |
| Detail | `{"source": "/home/elo/elo_research/rl-solver-selection-openfoam/OPENFOAM_PATH/validation/zeroD/e18_prep/stage1_cold/e12_prop_sanity.csv", "t": "0.05", "alphaEffMin": "2.46127e-05", "alphaEffMax": "6.47094e-05", "muMin": "1.846e-05", "muMax": "4.51681e-05", "nAlphaEffPos": "20000", "Tmax": "1000"}` |

Root cause fix: Sutherland As/Ts were 0 → patched to air-like 1.67212e−6 / 170.672.
