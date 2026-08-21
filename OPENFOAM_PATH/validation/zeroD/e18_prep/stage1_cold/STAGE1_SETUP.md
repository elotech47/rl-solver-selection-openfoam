# E18 Stage 1 — cold mixing setup

| Quantity | Value | Rationale |
|----------|-------|-----------|
| Gap L | **0.008 m (8 mm)** | Ember `example_diffusion.py`: `xLeft=-0.004`, `xRight=0.004` → width 8 mm |
| Strain a | 100 s⁻¹ | Stage 0 pick |
| V_inlet | **±0.4 m/s** | `a·L/2` to preserve a=100 with matched gap |
| p | 10 atm | Stage 0 pick |
| T_fuel / T_air | 300 / 1000 K | Stage 0 pick |
| Mesh | 200×100 = 20k, mid-plane refined | Stage 1 target 15–30k |
| Chemistry | **OFF** | inert transport |
| Geometric midplane | x = L/2 = 0.004 m | stagnation shifts toward air (ρ_fuel ≫ ρ_air) |

**Rejected:** E17 gap L=0.02 m → V=1.0 m/s — not Ember-matched.
